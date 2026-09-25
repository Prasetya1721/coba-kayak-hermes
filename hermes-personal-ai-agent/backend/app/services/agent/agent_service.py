"""AI Agent core: LangChain agent with function calling + two-tier memory.

Responsibilities:
  * Scrub inbound/outbound text (never let secrets reach the model or DB).
  * Load the last N messages as short-term memory (per session).
  * Load permanent facts via MemoryService and inject them into the prompt.
  * Honour explicit "ingat/lupakan" commands; auto-extract durable facts.
  * Run the tool-calling agent loop (incl. remember/recall_memory tools).
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
from app.services.agent.tool_registry import (
    build_agent_tools,
    set_credential_resolver,
    set_memory_service,
)
from app.services.memory_service import MemoryService

log = get_logger(__name__)

SYSTEM_PROMPT = """\
Kamu Stella — asisten pribadi yang udah kenal deket sama penggunamu. Ngobrol
kayak temen yang pinter dan perhatian, bukan kayak mesin penjawab atau CS.

GAYA NGOBROL (ini yang paling penting):
- Pakai bahasa sehari-hari yang natural: "aku/kamu", kontraksi ("nggak", "udah",
  "gimana", "kenapa"), kalimat pendek yang mengalir.
- JANGAN pakai pola kaku: "Baik, saya akan...", "Sebagai AI...", "Berikut adalah...",
  bullet-point formal untuk hal sepele, atau sapaan berlebihan tiap pesan.
- Variasikan kalimatmu. Jangan mulai tiap jawaban dengan pola yang sama.
- Emoji sesekali aja (maks 1 per pesan, kadang nol juga nggak apa). Jangan tiap kalimat.
- Humor ringan boleh kalau pas, tapi jangan maksa lucu.
- Kalau topiknya serius/teknis: tetap hangat tapi langsung ke inti, efisien.
- Panggil nama pengguna kalau kamu sudah ingat namanya — itu bikin hangat.
- Tunjukkan kamu nyimak: referensikan hal yang dia pernah cerita ("oh iya, kan
  kamu suka kopi tubruk...").

KEPRIBADIAN:
- Hangat, ceria, energik tapi nggak berlebihan. Percaya diri, rendah hati.
- Curious: kalau ada hal menarik, gali dikit atau tawarin bantuan lanjutan —
  tapi cukup sekali, jangan nge-push.
- Jujur dan langsung: kalau dia salah atau idenya kurang oke, bilang baik-baik.
  Jangan asal ngiyain.
- Kalau nggak tahu: ngaku aja, tawarin buat cari tahu (pakai web_search) atau
  tanya balik.

INGATAN:
- Di bawah riwayat chat ada daftar hal yang kamu ingat tentang dia. Pakai secara
  natural — JANGAN pernah nampilin daftarnya mentah-mentah atau bilang "menurut
  memoriku...".
- Kalau dia cerita fakta diri baru yang penting (nama, ulang tahun, kota, kerja,
  kesukaan, perangkat), simpan pakai tool remember — diam-diam aja, nggak usah
  diumumin, kecuali dia explicitly minta ("ingat ya ...") maka konfirmasi singkat.
- Kalau dia minta dilupakan, turuti tanpa drama.

ATURAN OPERASIONAL (wajib, tapi sampaikan dengan bahasa manusia):
- Jawab dalam bahasa yang dipakai pengguna (default Bahasa Indonesia).
- Tool yang bisa kamu pakai: web_search, remember, recall_memory,
  schedule_notification, manage_github, manage_vercel, execute_ssh (kalau ada),
  read_file, list_dir, search_code, repo_tree, run_code (kalau diaktifkan).
- Kalau mau search web, jangan ngomong "saya akan melakukan pencarian..." —
  langsung cari aja, terus sampaikan hasilnya kayak cerita.
- INGATAN PROYEK & KODE: kalau dia nyebut proyek ("PMS", "repo X") atau bahas
  kode, ingat konteksnya diam-diam pakai remember (key proyek/kode). Di
  obrolan berikutnya soal proyek yang sama, pakai konteks itu biar nggak
  ngulang nanya. Jangan campur konteks antar proyek.
- BACA REPO: kalau diminta review/debug kode di repo, mulai dari repo_tree buat
  orientasi, terus read_file/search_code buat baca bagian yang relevan. Tool ini
  read-only — kalau belum diaktifkan (REPO_ROOTS kosong), minta dia set dulu
  dengan bahasa santai, jangan ngarang isi file.
- JALANKAN KODE: cuma buat testing/debugging kecil (potongan python/node murni:
  hitung, parsing, unit test tanpa I/O). Selalu jelasin dulu mau jalanin apa
  + risikonya dengan jujur, dan JANGAN pernah jalanin kalau tool-nya mati —
  minta dia nyalakan CODE_EXEC_ENABLED dulu. Tolak perintah destruktif
  (hapus file, network, dsb) dengan baik-baik.
- Tindakan berisiko lain (deploy, SSH, ubah repo): jelasin dulu mau ngapain
  dengan bahasa santai, minta oke-nya dia kalau kamu ragu.
- Jangan pernah nampilin ulang kata sandi, token, nomor kartu, atau NIK.
- Kalau ditanya, ingatkan bahwa kamu adalah AI.
- Stella itu karakter orisinal — jangan ngaku-ngaku jadi tokoh nyata.

CONTOH GAYA (rasakan nadanya, jangan dihafal mentah):
- Sapaan: "Hai! Stella di sini 😊 ada yang bisa dibantu?"
- Selesai tugas: "Udah aku beresin! Kalau ada yang mau disesuaikan, bilang aja ya."
- Ragu: "Hmm, yang ini aku kurang yakin — mau aku cariin dulu?"
- Pakai ingatan: "Siap! Eh, ngomong-ngomong kopimu masih yang tubruk kan?"
- Salah user: "Hmm, jujur ya, cara itu kayaknya bakal error deh. Mending gini..."
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
        self.memory = MemoryService(session)

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

        # Project-aware recall: detect "PMS"/"proyek X" in this message, or
        # reuse the project mentioned earlier in this session.
        from app.services.memory_service import MemoryService as _MS

        project_scope = _MS.detect_project_scope(scrub.scrubbed)
        if project_scope is None:
            for h in history:
                if h["role"] == "user":
                    project_scope = _MS.detect_project_scope(h["content"])
                    if project_scope:
                        break

        memory_block = await self.memory.recall_block(
            user_id, project_scope=project_scope
        )

        # Long-term bridge: session summary (this session) + recent summaries
        # from OTHER sessions, so she stays coherent across sessions/weeks.
        summary_block = await self._build_summary_block(user_id, session_row.id)

        # Explicit memory commands ("ingat ya ..."/"lupakan ...") are honoured
        # deterministically and confirmed without an LLM round-trip.
        memory_note: str | None = None
        cmd = self.memory.parse_explicit_command(scrub.scrubbed)
        if cmd and cmd["action"] == "remember":
            # Split long sentences into facts (nama, kota, ...) when possible;
            # fall back to a raw note for everything else. Dedupe identical
            # (key, value) pairs — one sentence can match several patterns.
            facts = self.memory.extract_facts(cmd["value"])
            seen: set[tuple[str, str]] = set()
            saved_labels: list[str] = []
            for key, value in facts:
                if (key, value.lower()) in seen:
                    continue
                seen.add((key, value.lower()))
                saved = await self.memory.save(user_id, key, value)
                saved_labels.append(f"{saved['key']} ({saved['value']})")
            if saved_labels:
                memory_note = (
                    "Siap, udah aku ingat-ingat: "
                    + ", ".join(saved_labels)
                    + " 👍"
                )
            else:
                saved = await self.memory.save(user_id, "catatan", cmd["value"])
                memory_note = f"Siap, udah aku ingat-ingat: {saved['value']} 👍"
        elif cmd and cmd["action"] == "forget":
            removed = await self._handle_forget(user_id, cmd["value"])
            memory_note = removed

        if credential_resolver is not None:
            set_credential_resolver(credential_resolver)
        set_memory_service(self.memory, user_id)
        try:
            if memory_note is not None:
                result = AgentResult(reply=memory_note)
            elif not llm_is_configured():
                result = AgentResult(
                    reply=(
                        "Asisten belum dikonfigurasi: API key model belum diisi. "
                        "Set OPENAI_API_KEY atau ANTHROPIC_API_KEY di file .env."
                    ),
                    scrubbed_input=scrub.changed,
                    detections=scrub.detections,
                )
            else:
                result = await self._run_agent(history, memory_block, summary_block)
        finally:
            set_credential_resolver(None)
            set_memory_service(None)

        await self.logs.append(session_row.id, "assistant", result.reply)

        # Auto-extract durable facts from this turn (quiet, best-effort).
        # Skipped when an explicit ingat/lupakan command already handled it.
        if memory_note is None:
            seen_auto: set[tuple[str, str]] = set()
            for key, value in self.memory.extract_facts(scrub.scrubbed):
                if (key, value.lower()) in seen_auto:
                    continue
                seen_auto.add((key, value.lower()))
                try:
                    await self.memory.save(user_id, key, value, source="extracted")
                except Exception as exc:  # noqa: BLE001
                    log.warning("memory_extract_save_failed", error=str(exc))

        for directive in result.directives:
            await self._persist_directive(user_id, directive)

        await self.session.commit()

        # Best-effort rolling summary (never blocks the reply).
        try:
            await self._maybe_roll_summary(user_id, session_row.id)
            await self.session.commit()
        except Exception as exc:  # noqa: BLE001
            log.warning("roll_summary_failed", error=str(exc))

        return session_row.id, result

    async def _handle_forget(self, user_id: uuid.UUID, value: str) -> str:
        """Forget by key label ("nama", "ulang tahun"...) or wipe everything."""
        if not value:
            return (
                "Hmm, lupakan yang mana nih? Coba sebutin, misal "
                "'lupakan ulang tahunku' — atau 'lupakan semuanya'."
            )
        lowered = value.lower()
        if any(w in lowered for w in ("semua", "semuanya", "all", "everything")):
            n = await self.memory.delete_by_user(user_id)
            return f"Oke, {n} ingatanku udah aku hapus semua. Kita mulai fresh ya 🌱"
        key_map = {
            "nama": "nama",
            "name": "nama",
            "ulang tahun": "ulang_tahun",
            "birthday": "ulang_tahun",
            "kota": "kota",
            "tinggal": "kota",
            "kerja": "pekerjaan",
            "pekerjaan": "pekerjaan",
            "suka": "preferensi",
            "preferensi": "preferensi",
            "server": "perangkat",
            "perangkat": "perangkat",
            "proyek": "proyek",
            "project": "proyek",
            "repo": "proyek",
            "kode": "kode",
            "coding": "kode",
            "catatan": "catatan",
        }
        # "lupakan proyek PMS" wipes the whole project scope.
        scope = self.memory.detect_project_scope(value)
        if scope and any(w in lowered for w in ("proyek", "project", "repo")):
            n = await self.memory.delete_by_scope(user_id, scope)
            if n:
                return f"Beres, semua ingatan soal {scope.split(':', 1)[1]} udah aku lupain 👍"
        for label, key in key_map.items():
            if label in lowered:
                if key == "proyek":
                    # No specific project named: wipe every proyek:* scope.
                    scopes = await self.memory.scopes(user_id)
                    total = 0
                    for s in scopes:
                        if s.startswith("proyek:"):
                            total += await self.memory.delete_by_scope(user_id, s)
                    if total:
                        return f"Beres, {total} ingatan proyek udah aku lupain 👍"
                if key == "kode":
                    n = await self.memory.delete_by_scope(user_id, "kode")
                else:
                    n = await self.memory.delete_by_key(user_id, key)
                if n:
                    return f"Beres, soal {label} udah aku lupain 👍"
                return f"Hmm, aku nggak nemu ingatan soal {label}. Mungkin belum pernah dicatat?"
        n = await self.memory.delete_by_key(user_id, "catatan")
        if n:
            return "Oke, catatan terakhir udah aku hapus 👍"
        return (
            "Aku nggak nemu yang cocok. Coba cek halaman Memory di dashboard "
            "buat lihat & hapus satu-satu ya."
        )

    async def _build_summary_block(
        self, user_id: uuid.UUID, session_id: uuid.UUID
    ) -> str:
        """Compose the long-term context block from session summaries."""
        parts: list[str] = []
        current = await self.memory.get_summary(session_id)
        if current:
            parts.append(
                f"RINGKASAN SESSI INI (bacaan cepat biar nyambung):\n{current['summary']}"
            )
        others = await self.memory.recent_summaries(user_id, limit=5)
        others = [s for s in others if s["session_id"] != str(session_id)][:3]
        if others:
            lines = [
                f"- ({s['created_at'][:10] if s['created_at'] else 'dulu'}): {s['summary'][:300]}"
                for s in others
            ]
            parts.append(
                "INGATAN SESSI-SESI SEBELUMNYA (konteks lintas sesi, pakai kalau relevan):\n"
                + "\n".join(lines)
            )
        return "\n\n".join(parts)

    async def _maybe_roll_summary(self, user_id: uuid.UUID, session_id: uuid.UUID) -> None:
        """Compress old history into a rolling summary once the log grows long."""
        from app.services.memory_service import (
            SUMMARIZE_AFTER_MESSAGES,
            SUMMARY_KEEP_RECENT,
        )

        try:
            total = await self.logs.count_by_session(session_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("summary_count_failed", error=str(exc))
            return
        if total < SUMMARIZE_AFTER_MESSAGES:
            return
        existing = await self.memory.get_summary(session_id)
        covered = existing["messages_covered"] if existing else 0
        # Only re-summarize when at least 20 new messages arrived.
        if total - covered < SUMMARY_KEEP_RECENT + 20:
            return
        try:
            old = await self.logs.list_by_session(
                session_id, limit=total - SUMMARY_KEEP_RECENT, offset=0
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("summary_fetch_failed", error=str(exc))
            return
        if not old:
            return
        prompt = self.memory.build_summary_prompt(old)
        try:
            model = build_chat_model()
            summary_msg = await model.ainvoke([HumanMessage(content=prompt)])
            summary = (
                summary_msg.content
                if isinstance(summary_msg.content, str)
                else str(summary_msg.content)
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("summary_llm_failed", error=str(exc))
            return
        if existing:
            prev = existing["summary"]
            summary = f"{prev}\n---\n{summary}"[-4000:]
        try:
            await self.memory.save_summary(user_id, session_id, summary, total)
            log.info("session_summarized", covered=total)
        except Exception as exc:  # noqa: BLE001
            log.warning("summary_save_failed", error=str(exc))

    async def _run_agent(
        self,
        history: list[dict[str, str]],
        memory_block: str = "",
        summary_block: str = "",
    ) -> AgentResult:
        tools = build_agent_tools()
        model = build_chat_model()
        model_with_tools = model.bind_tools(tools) if tools else model
        tool_map = {t.name: t for t in tools}

        system = SYSTEM_PROMPT
        if memory_block:
            system += "\n\n" + memory_block
        if summary_block:
            system += "\n\n" + summary_block
        messages: list[BaseMessage] = [SystemMessage(content=system)]
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
