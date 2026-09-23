"""LangChain tool definitions exposed to the AI agent.

Tools are thin wrappers: they validate inputs, call a pure function in
`tools/*`, and return compact string results suitable for an LLM. Dangerous
actions (SSH, deploy) return clear refusal messages instead of raising, so the
model can recover gracefully.

Notification scheduling does NOT write to the DB here; it returns a structured
directive that `AgentService` persists after the turn (keeps tools stateless
and testable).
"""

from __future__ import annotations

import json

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.agent.tools import device, web_management, web_search
from app.services.agent.tools.notifications import (
    ScheduleError,
    next_run_from_cron,
    parse_run_at,
    validate_cron,
)

# --- Input schemas ------------------------------------------------------------


class WebSearchInput(BaseModel):
    query: str = Field(description="Kata kunci pencarian web.")


class SSHInput(BaseModel):
    host: str = Field(description="Hostname atau IP perangkat.")
    username: str = Field(description="Username SSH.")
    command: str = Field(description="Perintah yang akan dijalankan (harus di whitelist).")
    port: int = Field(default=22, description="Port SSH.")


class GithubInput(BaseModel):
    action: str = Field(description="Salah satu: get_repo | push_file | list_workflows")
    owner: str
    repo: str
    path: str | None = Field(default=None, description="Untuk push_file.")
    content: str | None = Field(default=None, description="Isi file untuk push_file.")
    message: str | None = Field(default=None, description="Pesan commit untuk push_file.")
    branch: str | None = None


class VercelInput(BaseModel):
    action: str = Field(description="Salah satu: list_deployments | trigger_deploy")
    project: str
    ref: str | None = Field(default="main", description="Git ref untuk deploy.")


class ScheduleNotificationInput(BaseModel):
    message: str = Field(description="Isi pengingat/notifikasi.")
    platform: str = Field(default="telegram", description="telegram atau whatsapp.")
    cron: str | None = Field(default=None, description="Ekspresi cron untuk berulang.")
    run_at: str | None = Field(
        default=None, description="Waktu ISO 8601 untuk sekali jalan."
    )


# --- Tool implementations -----------------------------------------------------


async def _web_search_impl(query: str) -> str:
    try:
        results = await web_search.web_search(query, limit=5)
    except web_search.WebSearchError as exc:
        return f"Pencarian gagal: {exc}"
    return web_search.format_results(results)


async def _ssh_impl(host: str, username: str, command: str, port: int = 22) -> str:
    return await device.execute_ssh(host=host, username=username, command=command, port=port)


async def _github_impl(
    action: str,
    owner: str,
    repo: str,
    path: str | None = None,
    content: str | None = None,
    message: str | None = None,
    branch: str | None = None,
) -> str:
    try:
        if action == "get_repo":
            data = await web_management.github_get_repo(owner, repo)
        elif action == "list_workflows":
            data = await web_management.github_list_workflows(owner, repo)
        elif action == "push_file":
            if not (path and content and message):
                return "push_file membutuhkan path, content, dan message."
            data = await web_management.github_push_file(
                owner=owner,
                repo=repo,
                path=path,
                content=content,
                message=message,
                branch=branch,
            )
        else:
            return f"Aksi tidak dikenal: {action}"
    except web_management.WebManagementError as exc:
        return f"GitHub error: {exc}"
    return json.dumps(data, ensure_ascii=False)


async def _vercel_impl(action: str, project: str, ref: str | None = "main") -> str:
    try:
        if action == "list_deployments":
            data = await web_management.vercel_list_deployments(project)
        elif action == "trigger_deploy":
            data = await web_management.vercel_trigger_deploy(project, ref=ref or "main")
        else:
            return f"Aksi tidak dikenal: {action}"
    except web_management.WebManagementError as exc:
        return f"Vercel error: {exc}"
    return json.dumps(data, ensure_ascii=False)


async def _schedule_impl(
    message: str,
    platform: str = "telegram",
    cron: str | None = None,
    run_at: str | None = None,
) -> str:
    if platform not in ("telegram", "whatsapp"):
        return "Platform harus 'telegram' atau 'whatsapp'."
    if not cron and not run_at:
        return "Sertakan 'cron' (berulang) atau 'run_at' (sekali jalan)."
    try:
        if cron:
            cron = validate_cron(cron)
            nxt = next_run_from_cron(cron).isoformat()
        else:
            nxt = (parse_run_at(run_at) or parse_run_at_required(run_at)).isoformat()
    except ScheduleError as exc:
        return f"Jadwal tidak valid: {exc}"

    directive = {
        "__directive": "schedule_notification",
        "message": message,
        "platform": platform,
        "cron": cron,
        "run_at": run_at,
        "next_run": nxt,
    }
    return json.dumps(directive, ensure_ascii=False)


def parse_run_at_required(value: str | None):
    dt = parse_run_at(value)
    if dt is None:
        raise ScheduleError("run_at wajib diisi")
    return dt


# --- Registry -----------------------------------------------------------------


def build_agent_tools() -> list[StructuredTool]:
    """Create the tool set available to the LLM."""
    tools: list[StructuredTool] = [
        StructuredTool.from_function(
            coroutine=_web_search_impl,
            name="web_search",
            description="Cari informasi terbaru di web dan kembalikan ringkasan hasil.",
            args_schema=WebSearchInput,
        ),
        StructuredTool.from_function(
            coroutine=_schedule_impl,
            name="schedule_notification",
            description=(
                "Jadwalkan pengingat/notifikasi ke Telegram atau WhatsApp. "
                "Gunakan 'cron' untuk berulang atau 'run_at' (ISO 8601) sekali jalan."
            ),
            args_schema=ScheduleNotificationInput,
        ),
    ]

    if settings.github_token:
        tools.append(
            StructuredTool.from_function(
                coroutine=_github_impl,
                name="manage_github",
                description="Kelola repository GitHub: get_repo, list_workflows, push_file.",
                args_schema=GithubInput,
            )
        )

    if settings.vercel_token:
        tools.append(
            StructuredTool.from_function(
                coroutine=_vercel_impl,
                name="manage_vercel",
                description="Kelola deployment Vercel: list_deployments, trigger_deploy.",
                args_schema=VercelInput,
            )
        )

    # SSH is only exposed when a whitelist is configured.
    if settings.ssh_whitelist_list:
        tools.append(
            StructuredTool.from_function(
                coroutine=_ssh_impl,
                name="execute_ssh",
                description=(
                    "Jalankan perintah TERBATAS pada perangkat/server via SSH. "
                    "Perintah harus ada di whitelist; karakter berbahaya ditolak."
                ),
                args_schema=SSHInput,
            )
        )

    return tools


DANGEROUS_TOOLS = {"execute_ssh", "manage_vercel", "manage_github"}
