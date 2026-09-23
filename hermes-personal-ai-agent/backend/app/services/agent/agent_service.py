"""AI Agent core: LangChain agent with function calling + short-term memory.

Responsibilities:
  * Scrub inbound/outbound text (never let secrets reach the model or DB).
  * Load the last N messages as short-term memory.
  * Run the tool-calling agent loop.
  * Persist encrypted logs and apply notification directives.

Kept transport-agnostic so it is reusable from webhooks, the REST API, and
tests.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import ChatSession
from app.middleware.scrubbing import scrub_text_detailed
from app.repositories.chat import ChatLogRepository, ChatSessionRepository
from app.repositories.templates import NotificationRepository
from app.services.agent.llm import build_chat_model, llm_is_configured
from app.services.agent.tool_registry import build_agent_tools, set_credential_resolver

log = get_logger(__name__)

SYSTEM_PROMPT = """\
Kamu adalah Hermes, asisten pribadi AI yang berjalan 24/7 untuk satu pengguna.

Aturan:
- Jawab ringkas, jelas, dan dalam bahasa yang digunakan pengguna (default Bahasa Indonesia).
- Kamu boleh memanggil tool: web_search, schedule_notification, manage_github,
  manage_vercel, dan execute_ssh (jika tersedia).
- Untuk tindakan berisiko (deploy, SSH, mengubah repository), jelaskan apa yang
  akan kamu lakukan dan minta konfirmasi bila ragu.
- Jangan pernah mencetak ulang kata sandi, token, nomor kartu, atau NIK; data
  sensitif sudah disensor sebelum sampai ke kamu.
- Transparan: bila diminta, ingatkan pengguna bahwa kamu adalah AI.
"""


class SessionNotFoundError(ValueError):
    """Raised when a requested chat session does not belong to the user."""


@dataclass
class AgentResult:
    reply: str
    scrubbed_input: bool = False
    detections: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    directives: list[dict] = field(default_factory=list)


class AgentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.sessions = ChatSessionRepository(session)
        self.logs = ChatLogRepository(session)
        self.notifications = NotificationRepository(session)

    async def handle_message(
        self,
        *,
        user_id: uuid.UUID,
        platform: str,
        platform_chat_id: str,
        message: str,
        session_id: uuid.UUID | None = None,
        credential_resolver=None,
    ) -> tuple[uuid.UUID, AgentResult]:
        """Process one inbound message end-to-end; returns (session_id, result)."""
        session_row: ChatSession | None = None
        if session_id is not None:
            session_row = await self.sessions.get_owned(session_id, user_id)
            if session_row is None:
                raise SessionNotFoundError(str(session_id))
        if session_row is None:
            session_row = await self.sessions.get_or_create(
                user_id=user_id, platform=platform, platform_chat_id=platform_chat_id
            )

        scrub = scrub_text_detailed(message)
        await self.logs.append(
            session_row.id,
            "user",
            scrub.scrubbed,
            meta=json.dumps({"detections": scrub.detections}) if scrub.detections else None,
        )

        history = await self.logs.recent(
            session_row.id, limit=settings.short_term_memory_size
        )

        if credential_resolver is not None:
            set_credential_resolver(credential_resolver)
        try:
            if not llm_is_configured():
                result = AgentResult(
                    reply=(
                        "Asisten belum dikonfigurasi: API key model belum diisi. "
                        "Set OPENAI_API_KEY atau ANTHROPIC_API_KEY di file .env."
                    ),
                    scrubbed_input=scrub.changed,
                    detections=scrub.detections,
                )
            else:
                result = await self._run_agent(history)
        finally:
            set_credential_resolver(None)

        await self.logs.append(session_row.id, "assistant", result.reply)

        for directive in result.directives:
            await self._persist_directive(user_id, directive)

        await self.session.commit()
        return session_row.id, result

    async def _run_agent(self, history: list[dict[str, str]]) -> AgentResult:
        tools = build_agent_tools()
        model = build_chat_model()
        model_with_tools = model.bind_tools(tools) if tools else model
        tool_map = {t.name: t for t in tools}

        messages: list[BaseMessage] = [SystemMessage(content=SYSTEM_PROMPT)]
        for h in history:
            if h["role"] == "user":
                messages.append(HumanMessage(content=h["content"]))
            else:
                messages.append(AIMessage(content=h["content"]))

        tool_calls: list[str] = []
        directives: list[dict] = []

        # Bounded agent loop (max 4 tool rounds).
        for _ in range(4):
            ai: AIMessage = await model_with_tools.ainvoke(messages)
            messages.append(ai)

            calls = getattr(ai, "tool_calls", None) or []
            if not calls:
                break

            for call in calls:
                name = call.get("name")
                args = call.get("args", {}) or {}
                tool_calls.append(name)
                tool = tool_map.get(name)
                if tool is None:
                    output = f"Tool '{name}' tidak tersedia."
                else:
                    try:
                        output = await tool.ainvoke(args)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("tool_failed", tool=name, error=str(exc))
                        output = f"Tool '{name}' gagal: {exc}"
                if isinstance(output, str) and '"__directive"' in output:
                    try:
                        directives.append(json.loads(output))
                    except json.JSONDecodeError:
                        pass
                messages.append(
                    ToolMessage(content=str(output), tool_call_id=call.get("id", name))
                )

        final = messages[-1]
        reply = final.content if isinstance(final.content, str) else str(final.content)
        return AgentResult(reply=reply, tool_calls=tool_calls, directives=directives)

    async def _persist_directive(self, user_id: uuid.UUID, directive: dict) -> None:
        from app.db.models import ScheduledNotification
        from app.services.agent.tools.notifications import (
            next_run_from_cron,
            parse_run_at,
        )

        cron = directive.get("cron")
        run_at_raw = directive.get("run_at")
        next_run = None
        run_at = None
        if cron:
            next_run = next_run_from_cron(cron)
        elif run_at_raw:
            run_at = parse_run_at(run_at_raw)
            next_run = run_at

        entity = ScheduledNotification(
            user_id=user_id,
            message=directive["message"],
            schedule_cron=cron,
            run_at=run_at,
            platform=directive.get("platform", "telegram"),
            next_run=next_run,
            active=True,
        )
        await self.notifications.add(entity)
        log.info("notification_scheduled", user_id=str(user_id), cron=cron)

    @staticmethod
    def now() -> datetime:
        return datetime.now(tz=timezone.utc)
