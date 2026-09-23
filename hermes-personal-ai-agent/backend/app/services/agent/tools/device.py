"""Device management tool: whitelisted SSH command execution (PRD §4.2).

Safety model:
  * Every command must start with an entry from SSH_COMMAND_WHITELIST.
  * Shell metacharacters that enable chaining/redirection are rejected.
  * Connect and command timeouts are enforced.
  * Credentials are never logged or returned.
"""

from __future__ import annotations

import asyncio
import re
import shlex

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_FORBIDDEN_META = re.compile(r"[;&|`$<>(){}\n\\]|&&|\|\|")
_MAX_OUTPUT_CHARS = 8000


class SSHCommandRejected(RuntimeError):
    pass


def validate_command(command: str) -> str:
    """Validate a command against the whitelist. Returns the stripped command."""
    cmd = (command or "").strip()
    if not cmd:
        raise SSHCommandRejected("Perintah kosong.")
    if _FORBIDDEN_META.search(cmd):
        raise SSHCommandRejected(
            "Perintah mengandung karakter berbahaya (;&|`$<>). Ditolak."
        )
    whitelist = settings.ssh_whitelist_list
    if not any(cmd == w or cmd.startswith(w + " ") for w in whitelist):
        raise SSHCommandRejected(
            "Perintah tidak ada di whitelist. Diizinkan: " + ", ".join(whitelist)
        )
    return cmd


def _run_ssh_sync(
    host: str,
    username: str,
    command: str,
    *,
    port: int = 22,
    password: str | None = None,
    private_key: str | None = None,
) -> str:
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        connect_kwargs = {
            "hostname": host,
            "port": port,
            "username": username,
            "timeout": settings.ssh_connect_timeout_seconds,
            "banner_timeout": settings.ssh_connect_timeout_seconds,
            "auth_timeout": settings.ssh_connect_timeout_seconds,
        }
        if private_key:
            import io

            connect_kwargs["pkey"] = paramiko.RSAKey.from_private_key(
                io.StringIO(private_key)
            )
        elif password:
            connect_kwargs["password"] = password
        client.connect(**connect_kwargs)

        _stdin, stdout, stderr = client.exec_command(
            command, timeout=settings.ssh_command_timeout_seconds
        )
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        combined = (out + ("\n" + err if err.strip() else "")).strip()
        return combined[:_MAX_OUTPUT_CHARS]
    finally:
        client.close()


async def execute_ssh(
    *,
    host: str,
    username: str,
    command: str,
    port: int = 22,
    password: str | None = None,
    private_key: str | None = None,
) -> str:
    """Run a whitelisted command over SSH, off the event loop."""
    safe_cmd = validate_command(command)
    log.info(
        "ssh_execute",
        host=host,
        user=username,
        command=shlex.split(safe_cmd)[0] if safe_cmd else "",
    )
    try:
        return await asyncio.to_thread(
            _run_ssh_sync,
            host,
            username,
            safe_cmd,
            port=port,
            password=password,
            private_key=private_key,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("ssh_execute_failed", host=host, error=str(exc))
        return f"Gagal menjalankan perintah: {exc}"
