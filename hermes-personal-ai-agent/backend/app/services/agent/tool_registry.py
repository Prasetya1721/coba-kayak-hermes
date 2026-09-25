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
from app.services.agent.tools import code_exec, device, repo, web_management, web_search
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
    credential_ref: str | None = Field(
        default=None,
        description=(
            "Nama kredensial SSH tersimpan (mis. 'ssh_rumah') bila password/private "
            "key tidak diberikan inline."
        ),
    )


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


class RememberInput(BaseModel):
    key: str = Field(
        description="Label singkat: nama, ulang_tahun, kota, pekerjaan, preferensi, perangkat, catatan."
    )
    value: str = Field(description="Fakta yang mau disimpan tentang pengguna.")


class RecallMemoryInput(BaseModel):
    query: str | None = Field(
        default=None,
        description="Opsional: filter kata kunci untuk mencari ingatan tertentu.",
    )


class ReadFileInput(BaseModel):
    path: str = Field(
        description="Path file di dalam repo yang diizinkan (relatif thd REPO_ROOTS atau absolut di dalamnya)."
    )


class ListDirInput(BaseModel):
    path: str = Field(default=".", description="Folder di dalam repo yang diizinkan.")


class SearchCodeInput(BaseModel):
    pattern: str = Field(description="Regex (case-insensitive) yang dicari di kode.")
    root: str = Field(default=".", description="Folder awal pencarian.")
    ext: str = Field(
        default="",
        description="Filter ekstensi koma-dipisah, mis. '.py,.js'. Kosong = semua file teks.",
    )


class RepoTreeInput(BaseModel):
    root: str = Field(default=".", description="Folder awal.")
    depth: int = Field(default=2, ge=1, le=4, description="Kedalaman tree.")


class RunCodeInput(BaseModel):
    language: str = Field(
        description="Bahasa: python (atau node kalau diizinkan). Sandbox, tanpa shell."
    )
    code: str = Field(description="Kode lengkap yang ditulis ke file temp lalu dijalankan.")


# --- Tool implementations -----------------------------------------------------


async def _web_search_impl(query: str) -> str:
    try:
        results = await web_search.web_search(query, limit=5)
    except web_search.WebSearchError as exc:
        return f"Pencarian gagal: {exc}"
    return web_search.format_results(results)


async def _ssh_impl(
    host: str,
    username: str,
    command: str,
    port: int = 22,
    credential_ref: str | None = None,
) -> str:
    password: str | None = None
    private_key: str | None = None
    if credential_ref:
        resolver = _current_credential_resolver()
        if resolver is None:
            return (
                "credential_ref tidak didukung pada konteks ini. "
                "Minta pengguna menyambungkan SSH dengan password inline "
                "atau jalankan ulang dari webhook/chat."
            )
        try:
            secret = await resolver(credential_ref)
        except Exception as exc:  # noqa: BLE001
            return f"Kredensial tidak dapat dipakai: {exc}"
        if secret.lstrip().startswith("-----BEGIN"):
            private_key = secret
        else:
            password = secret
    return await device.execute_ssh(
        host=host,
        username=username,
        command=command,
        port=port,
        password=password,
        private_key=private_key,
    )


# --- Context-local hooks (set per conversation turn) --------------------------
# The agent runs with user context, but LangChain tools are plain coroutines.
# These module-level hooks are assigned by `AgentService` before the tool loop
# so tools can resolve credentials / memories without threading DB sessions
# through every tool signature.

from collections.abc import Awaitable, Callable  # noqa: E402

_CredentialResolver = Callable[[str], Awaitable[str]]
_resolver: _CredentialResolver | None = None


def set_credential_resolver(fn: _CredentialResolver | None) -> None:
    global _resolver
    _resolver = fn


def _current_credential_resolver() -> _CredentialResolver | None:
    return _resolver


_MemorySaver = Callable[[str, str], Awaitable[dict]]
_MemoryLister = Callable[[], Awaitable[list]]
_memory_saver: _MemorySaver | None = None
_memory_lister: _MemoryLister | None = None


def set_memory_service(service, user_id=None) -> None:  # noqa: ANN001, ANN002
    """Bind the per-turn MemoryService + owner (or None to unbind).

    The user id is captured in closures, so concurrent turns for different
    users never share state through module globals.
    """
    global _memory_saver, _memory_lister
    if service is None or user_id is None:
        _memory_saver, _memory_lister = None, None
        return

    async def _save(key: str, value: str) -> dict:
        return await service.save(user_id, key, value)

    async def _list() -> list:
        return await service.list(user_id)

    _memory_saver, _memory_lister = _save, _list


async def _remember_impl(key: str, value: str) -> str:
    if _memory_saver is None:
        return "Penyimpanan ingatan tidak tersedia pada konteks ini."
    try:
        saved = await _memory_saver(key.strip().lower()[:50] or "catatan", value)
    except Exception as exc:  # noqa: BLE001
        return f"Gagal menyimpan ingatan: {exc}"
    return f"Oke, udah aku ingat: {saved['key']} = {saved['value']} 👍"


async def _recall_impl(query: str | None = None) -> str:
    if _memory_lister is None:
        return "Ingatan tidak tersedia pada konteks ini."
    items = await _memory_lister()
    if query:
        q = query.lower()
        items = [
            m
            for m in items
            if q in m["key"]
            or q in m["value"].lower()
            or q in m.get("scope", "").lower()
        ]
    if not items:
        return "Aku belum punya ingatan yang cocok."
    lines = [
        f"- {m['key']}" + (f" [{m.get('scope')}]" if m.get("scope", "global") != "global" else "") + f": {m['value']}"
        for m in items[:20]
    ]
    return "Yang aku ingat:\n" + "\n".join(lines)


async def _read_file_impl(path: str) -> str:
    try:
        return repo.read_file(path)
    except repo.RepoAccessError as exc:
        return f"Nggak bisa baca: {exc}"


async def _list_dir_impl(path: str = ".") -> str:
    try:
        return repo.list_dir(path)
    except repo.RepoAccessError as exc:
        return f"Nggak bisa buka: {exc}"


async def _search_code_impl(pattern: str, root: str = ".", ext: str = "") -> str:
    try:
        return repo.search_code(pattern, root=root, ext=ext)
    except repo.RepoAccessError as exc:
        return f"Nggak bisa cari: {exc}"


async def _repo_tree_impl(root: str = ".", depth: int = 2) -> str:
    try:
        return repo.summarize_tree(root, depth=depth)
    except repo.RepoAccessError as exc:
        return f"Nggak bisa: {exc}"


async def _run_code_impl(language: str, code: str) -> str:
    try:
        return await code_exec.run_code(language=language, code=code)
    except code_exec.CodeExecError as exc:
        return f"Nggak bisa jalanin: {exc}"


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
            description=(
                "Cari informasi terbaru di web dan kembalikan ringkasan hasil. "
                "Pakai ini kalau pengguna tanya hal faktual/terkini yang kamu "
                "nggak yakin, BUKAN untuk hal yang sudah kamu ingat tentang dia."
            ),
            args_schema=WebSearchInput,
        ),
        StructuredTool.from_function(
            coroutine=_remember_impl,
            name="remember",
            description=(
                "Simpan fakta permanen tentang pengguna (nama, ulang tahun, "
                "kota, pekerjaan, kesukaan, perangkat). Dipakai kalau pengguna "
                "minta diingat atau menyampaikan fakta diri yang layak disimpan."
            ),
            args_schema=RememberInput,
        ),
        StructuredTool.from_function(
            coroutine=_recall_impl,
            name="recall_memory",
            description=(
                "Lihat kembali hal-hal yang kamu ingat tentang pengguna. "
                "Opsional kasih kata kunci buat nyari ingatan tertentu."
            ),
            args_schema=RecallMemoryInput,
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
        StructuredTool.from_function(
            coroutine=_read_file_impl,
            name="read_file",
            description=(
                "Baca file teks di repo yang diizinkan (REPO_ROOTS). Read-only. "
                "Kalau belum diaktifkan, minta pengguna set REPO_ROOTS dulu."
            ),
            args_schema=ReadFileInput,
        ),
        StructuredTool.from_function(
            coroutine=_list_dir_impl,
            name="list_dir",
            description="Lihat isi folder di repo yang diizinkan.",
            args_schema=ListDirInput,
        ),
        StructuredTool.from_function(
            coroutine=_search_code_impl,
            name="search_code",
            description=(
                "Cari pola regex di kode repo yang diizinkan (mirip grep). "
                "Bisa filter ekstensi, mis. '.py,.js'."
            ),
            args_schema=SearchCodeInput,
        ),
        StructuredTool.from_function(
            coroutine=_repo_tree_impl,
            name="repo_tree",
            description="Lihat struktur folder repo (tree ringkas) buat orientasi.",
            args_schema=RepoTreeInput,
        ),
        StructuredTool.from_function(
            coroutine=_run_code_impl,
            name="run_code",
            description=(
                "Jalankan potongan kode kecil (python/node) di sandbox server buat "
                "testing/debugging: TANPA shell, TANPA akses file/network, timeout "
                "ketat. MATI secara default — kalau mati, minta pengguna nyalakan "
                "CODE_EXEC_ENABLED dulu dan jelaskan risikonya dengan jujur."
            ),
            args_schema=RunCodeInput,
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


DANGEROUS_TOOLS = {"execute_ssh", "manage_vercel", "manage_github", "run_code"}
