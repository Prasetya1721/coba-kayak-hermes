"""Sandboxed code execution: run small scripts for testing/debugging.

Safety model (defense in depth):
  1. Global kill-switch: CODE_EXEC_ENABLED must be true (default FALSE).
  2. NO shell: subprocess runs with shell=False and a fixed argv.
  3. Language allowlist: only interpreters in CODE_EXEC_LANGUAGES (default: python).
     The interpreter is resolved via shutil.which — never from user input.
  4. Script allowlist: builtin scripts (pytest one-liners are NOT allowed —
     the agent writes a temp .py/.js file) plus optional inline code only for
     python -c style snippets? NO — always via temp file, never -c, to avoid
     shell-quoting smuggling.
  5. Jail: temp file lives in a fresh mkdtemp dir, cwd=jail, env scrubbed
     (no AWS_/GH_/OPENAI_ secrets leak into the child).
  6. Hard timeout (CODE_EXEC_TIMEOUT_SECONDS) + output truncation.
  7. Network egress is NOT blocked at this layer (documented limitation) —
     keep CODE_EXEC_ENABLED=false on untrusted networks, or run the whole
     backend in a container without egress.

Dangerous patterns in the code itself (os.system, subprocess, socket, eval of
remote code, file writes outside jail) are rejected by a blocklist scan. This
is a speed bump, not a proof — the real boundary is jail+timeout+no-shell.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
import tempfile

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_BLOCKED_PATTERNS = [
    (r"\bos\.system\s*\(", "os.system"),
    (r"\bsubprocess\b", "subprocess"),
    (r"\bsocket\b", "socket"),
    (r"\bctypes\b", "ctypes"),
    (r"\bmultiprocessing\b", "multiprocessing"),
    (r"\bthreading\b", "threading"),
    (r"\bopen\s*\([^)]*['\"]w", "file write"),
    (r"\bos\.(remove|unlink|rmdir|removedirs|rename|replace|chmod|chown|kill|exec\w*|spawn\w*|fork|_exit)\b", "os.* (destructive/exec)"),
    (r"\bshutil\.(rmtree|move|copytree|chown)\b", "shutil.* (destructive)"),
    (r"\bpathlib\b.*\b(unlink|rmdir|rename|write_)", "pathlib write"),
    (r"\beval\s*\(", "eval"),
    (r"\bexec\s*\(", "exec("),
    (r"__import__\s*\(", "__import__"),
    (r"\bimport\s+pty\b", "pty"),
    (r"\bos\.popen\b", "os.popen"),
    (r"\brequests?\b.*\b(post|put|delete|patch)\b", "outbound write HTTP"),
    (r"\burllib\b", "urllib"),
    (r"\bhttp\.client\b", "http.client"),
    (r"\bftplib\b", "ftplib"),
    (r"\bsmtplib\b", "smtplib"),
    (r"\binput\s*\(", "input()"),
]

_INTERPRETERS = {
    "python": ("python", (".py",)),
    "node": ("node", (".js", ".mjs")),
}

_SCRUB_ENV_PREFIXES = (
    "AWS_", "GH_", "GITHUB_", "OPENAI_", "ANTHROPIC_", "TELEGRAM_",
    "TWILIO_", "SERPAPI_", "BRAVE_", "TAVILY_", "VERCEL_", "VAULT_",
    "JWT_", "FIELD_", "POSTGRES_PASSWORD", "REDIS_PASSWORD",
)


class CodeExecError(RuntimeError):
    pass


def validate_code(language: str, code: str) -> tuple[str, str]:
    """Validate language + code. Returns (language, stripped code)."""
    if not settings.code_exec_enabled:
        raise CodeExecError(
            "Eksekusi kode MATI. Nyalakan dengan CODE_EXEC_ENABLED=true di .env "
            "kalau kamu paham risikonya (kode jalan di server backend)."
        )
    lang = (language or "").strip().lower()
    allowed = settings.code_exec_languages_list
    if lang not in allowed or lang not in _INTERPRETERS:
        raise CodeExecError(
            f"Bahasa '{language}' tidak diizinkan. Diizinkan: {', '.join(allowed)}"
        )
    code = (code or "").strip()
    if not code:
        raise CodeExecError("Kode kosong.")
    if len(code) > 20000:
        raise CodeExecError("Kode kepanjangan (maks 20.000 karakter).")
    for pattern, label in _BLOCKED_PATTERNS:
        if re.search(pattern, code):
            raise CodeExecError(
                f"Pola berbahaya ditolak: {label}. Minta yang aman, mis. "
                "perhitungan, parsing string/JSON, atau unit test murni."
            )
    return lang, code


def _scrubbed_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(_SCRUB_ENV_PREFIXES) or "TOKEN" in key or "SECRET" in key or "PASSWORD" in key or "KEY" in key:
            # Keep PATH-ish basics; drop anything secret-looking.
            if key not in ("PATH", "PATHEXT", "SYSTEMROOT", "TEMP", "TMP"):
                del env[key]
    return env


async def run_code(*, language: str, code: str) -> str:
    """Write code to a jail temp file and run it with a fixed interpreter argv."""
    lang, code = validate_code(language, code)
    binary, exts = _INTERPRETERS[lang]
    exe = shutil.which(binary) or (sys.executable if lang == "python" else None)
    if not exe:
        raise CodeExecError(f"Interpreter '{binary}' tidak ketemu di server.")

    jail = tempfile.mkdtemp(prefix="hermes_exec_")
    script_path = os.path.join(jail, f"main{exts[0]}")
    try:
        # One tiny blocking write is acceptable here: it happens once per run,
        # off the event loop's hot path, before the subprocess spawns.
        with open(script_path, "w", encoding="utf-8") as fh:  # noqa: ASYNC230
            fh.write(code)

        log.info("code_exec", language=lang)
        try:
            proc = await asyncio.create_subprocess_exec(
                exe,
                script_path,
                cwd=jail,
                env=_scrubbed_env(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                out, _ = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=settings.code_exec_timeout_seconds,
                )
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                raise CodeExecError(
                    f"Waktu habis ({settings.code_exec_timeout_seconds}s) — proses dimatikan."
                ) from None
        except CodeExecError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("code_exec_failed", error=str(exc))
            return f"Gagal menjalankan kode: {exc}"

        text = (out or b"").decode("utf-8", errors="replace").strip()
        limit = settings.code_exec_max_output_chars
        if len(text) > limit:
            text = text[:limit] + "\n\n…(output dipotong)"
        status = f"[exit {proc.returncode}]"
        return f"{status}\n{text}" if text else f"{status}\n(tidak ada output)"
    finally:
        shutil.rmtree(jail, ignore_errors=True)
