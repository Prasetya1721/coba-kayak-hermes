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
import uuid

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
    action: str = Field(
        description=(
            "Salah satu: get_repo | list_files | read_file | search_code | list_commits "
            "| list_workflows | push_file"
        )
    )
    repo: str = Field(
        description="'owner/repo' atau URL GitHub lengkap (mis. https://github.com/owner/repo)."
    )
    path: str | None = Field(
        default=None, description="Path file/folder untuk list_files/read_file/push_file."
    )
    query: str | None = Field(default=None, description="Kata kunci untuk search_code.")
    content: str | None = Field(default=None, description="Isi file untuk push_file.")
    message: str | None = Field(default=None, description="Pesan commit untuk push_file.")
    branch: str | None = Field(
        default=None, description="Branch (default: branch utama repo)."
    )


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
        description=(
            "Label singkat: nama, ulang_tahun, kota, pekerjaan, preferensi, "
            "perangkat, proyek, kode, catatan."
        )
    )
    value: str = Field(description="Fakta yang mau disimpan tentang pengguna.")
    scope: str | None = Field(
        default=None,
        description=(
            "Opsional: 'global' (default), 'kode' (preferensi coding), atau "
            "'proyek:<nama>' (konteks proyek tertentu, mis. 'proyek:pms')."
        ),
    )


class ForgetMemoryInput(BaseModel):
    target: str = Field(
        description=(
            "Yang mau dilupakan: nama/isi ingatan ('dong'), key ('kota'), atau "
            "scope ('proyek:pms', 'kode')."
        )
    )


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


_TokenResolver = Callable[[], Awaitable[str]]
_token_resolver: _TokenResolver | None = None


def set_github_token_resolver(fn: _TokenResolver | None) -> None:
    """Bind a per-turn resolver that returns this user's GitHub token."""
    global _token_resolver
    _token_resolver = fn


async def _github_token() -> str | None:
    """Prefer the user's stored token, else the operator env token."""
    if _token_resolver is not None:
        try:
            token = await _token_resolver()
            if token:
                return token
        except Exception as exc:  # noqa: BLE001
            log_github_resolver_error(exc)
    return settings.github_token or None


def log_github_resolver_error(exc: Exception) -> None:
    from app.core.logging import get_logger

    get_logger(__name__).warning("github_token_resolver_failed", error=str(exc))


def github_tool_available() -> bool:
    """The tool is always exposed; it explains what to do if no token exists."""
    return True


_MemorySaver = Callable[..., Awaitable[dict]]
_MemoryLister = Callable[[], Awaitable[list]]
_MemoryForgetter = Callable[[str], Awaitable[int]]
_memory_saver: _MemorySaver | None = None
_memory_lister: _MemoryLister | None = None
_memory_forgetter: _MemoryForgetter | None = None


def set_memory_service(service, user_id=None) -> None:  # noqa: ANN001, ANN002
    """Bind the per-turn MemoryService + owner (or None to unbind).

    The user id is captured in closures, so concurrent turns for different
    users never share state through module globals.
    """
    global _memory_saver, _memory_lister, _memory_forgetter
    if service is None or user_id is None:
        _memory_saver, _memory_lister, _memory_forgetter = None, None, None
        return

    async def _save(key: str, value: str, scope: str | None = None) -> dict:
        return await service.save(user_id, key, value, scope=scope)

    async def _list() -> list:
        return await service.list(user_id)

    def _matches(target: str, key: str, value: str, scope: str) -> bool:
        """True if any word of target appears in key/value/scope.

        Word-based so "proyek pms" matches key "proyek_pms_stack" and scope
        "proyek:pms" (both contain "pms"), without matching unrelated facts.
        """
        haystack = f"{key} {value} {scope}".lower().replace(":", " ").replace("_", " ")
        words = [w for w in re_split_words(target) if len(w) >= 2]
        if not words:
            return False
        return all(w in haystack for w in words)

    async def _forget(target: str) -> int:
        """Delete by exact key/scope, or by all-word match on key/value/scope."""
        target = (target or "").strip().lower()
        if not target:
            return 0
        removed = 0
        # 1) exact scope ("proyek:pms", "kode") or exact key ("nama")
        removed += await service.delete_by_scope(user_id, target)
        removed += await service.delete_by_key(user_id, target)
        # 2) word-based match across key, value, and scope
        items = await service.list(user_id)
        for m in items:
            if _matches(target, m["key"], m["value"], m.get("scope", "global")):
                mid = m["id"]
                mid = uuid.UUID(mid) if isinstance(mid, str) else mid
                if await service.delete(user_id, mid):
                    removed += 1
        return removed

    _memory_saver, _memory_lister, _memory_forgetter = _save, _list, _forget


def re_split_words(text: str) -> list[str]:
    """Split on non-alphanumeric so 'proyek pms' -> ['proyek', 'pms']."""
    import re as _re

    return [w for w in _re.split(r"[^a-z0-9]+", (text or "").lower()) if w]


async def _remember_impl(key: str, value: str, scope: str | None = None) -> str:
    if _memory_saver is None:
        return "Penyimpanan ingatan tidak tersedia pada konteks ini."
    clean_key = key.strip().lower()[:50] or "catatan"
    clean_scope = (scope or "").strip()[:80] or None
    # Guard: a scope must look like "global" | "kode" | "proyek:<name>".
    if clean_scope and clean_scope not in ("global", "kode") and not clean_scope.startswith("proyek:"):
        clean_scope = None
    try:
        saved = await _memory_saver(clean_key, value, clean_scope)
    except Exception as exc:  # noqa: BLE001
        return f"Gagal menyimpan ingatan: {exc}"
    tag = "" if saved.get("scope", "global") == "global" else f" [{saved['scope']}]"
    return f"Oke, udah aku ingat: {saved['key']}{tag} = {saved['value']} 👍"


async def _forget_impl(target: str) -> str:
    if _memory_forgetter is None:
        return "Penghapusan ingatan tidak tersedia pada konteks ini."
    try:
        n = await _memory_forgetter(target)
    except Exception as exc:  # noqa: BLE001
        return f"Gagal menghapus ingatan: {exc}"
    if n:
        return f"Beres, {n} ingatan soal '{target}' udah aku lupain 👍"
    return (
        f"Hmm, aku nggak nemu ingatan soal '{target}'. "
        "Coba cek halaman Memory di dashboard ya."
    )


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
    repo: str,
    path: str | None = None,
    query: str | None = None,
    content: str | None = None,
    message: str | None = None,
    branch: str | None = None,
) -> str:
    try:
        token = await _github_token()
        if not token:
            return (
                "GitHub belum tersambung: belum ada token. Minta pengguna menyimpan "
                "token GitHub (Personal Access Token, scope 'repo') lewat halaman "
                "Onboarding/dashboard (service_name: github_token), atau set "
                "GITHUB_TOKEN di .env."
            )
        owner, name = web_management.parse_repo(repo)
        if action == "get_repo":
            data = await web_management.github_get_repo(owner, name, token=token)
        elif action == "list_files":
            data = await web_management.github_list_files(
                owner, name, path or "", branch=branch, token=token
            )
        elif action == "read_file":
            if not path:
                return "read_file butuh 'path' file."
            data = await web_management.github_read_file(
                owner, name, path, branch=branch, token=token
            )
        elif action == "search_code":
            if not query:
                return "search_code butuh 'query'."
            data = await web_management.github_search_code(
                owner, name, query, token=token
            )
        elif action == "list_commits":
            data = await web_management.github_list_commits(
                owner, name, branch=branch, token=token
            )
        elif action == "list_workflows":
            data = await web_management.github_list_workflows(owner, name, token=token)
        elif action == "push_file":
            if not (path and content and message):
                return "push_file butuh path, content, dan message."
            data = await web_management.github_push_file(
                owner=owner,
                repo=name,
                path=path,
                content=content,
                message=message,
                branch=branch,
                token=token,
            )
        else:
            return f"Aksi tidak dikenal: {action}"
    except web_management.WebManagementError as exc:
        return f"GitHub error: {exc}"
    result = json.dumps(data, ensure_ascii=False)
    # GitHub read_file content can be large; keep tool output bounded.
    limit = settings.repo_max_output_chars if hasattr(settings, "repo_max_output_chars") else 12000
    return result[:limit] if len(result) > limit else result


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
                "kota, pekerjaan, kesukaan, perangkat, proyek, preferensi kode). "
                "Pakai 'scope' untuk konteks proyek ('proyek:pms') atau 'kode'. "
                "Dipakai kalau pengguna minta diingat atau menyampaikan fakta "
                "diri yang layak disimpan. Jangan simpan pesan satu kata/arti "
                "tidak jelas — pastikan faktanya utuh."
            ),
            args_schema=RememberInput,
        ),
        StructuredTool.from_function(
            coroutine=_forget_impl,
            name="forget_memory",
            description=(
                "Hapus ingatan yang salah/duplikat/sudah tidak relevan. Bisa "
                "berupa key ('kota'), isi ('dong'), atau scope ('proyek:pms'). "
                "Pakai ini kalau pengguna minta lupakan ATAU kamu sadar ada "
                "ingatan sampah yang perlu dibersihkan."
            ),
            args_schema=ForgetMemoryInput,
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

    # Always expose GitHub tooling: it can read from the per-user token store,
    # and gives a clear "connect a token first" message when none exists.
    tools.append(
        StructuredTool.from_function(
            coroutine=_github_impl,
            name="manage_github",
            description=(
                "Baca & kelola repo GitHub secara LANGSUNG (bukan web search): "
                "get_repo (info), list_files (isi folder), read_file (isi file), "
                "search_code (cari kode), list_commits (riwayat), list_workflows "
                "(CI), push_file (tulis/commit). Terima 'owner/repo' atau URL."
            ),
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
