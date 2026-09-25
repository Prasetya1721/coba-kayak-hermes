"""Sandboxed repository tools: read files and search code.

Safety model:
  * Reads are jailed to REPO_ROOTS (absolute dirs in config). Anything outside
    is refused — including via `..`, symlinks, or absolute-path tricks.
  * Binary files are refused (null byte / undecodable).
  * Output is truncated (repo_max_file_bytes / repo_max_output_chars).
  * Write operations are NOT exposed. This tool is read-only by design.
"""

from __future__ import annotations

import os
import re

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    ".next", "dist", "build", ".idea", ".vscode", ".tox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache",
}
_SKIP_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".pdf",
    ".zip", ".tar", ".gz", ".7z", ".rar", ".exe", ".dll", ".so", ".dylib",
    ".pyc", ".pyo", ".class", ".o", ".a", ".lib", ".mp3", ".mp4", ".wav",
    ".avi", ".mov", ".mkv", ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".db", ".sqlite", ".sqlite3",
}
_MAX_LIST_ENTRIES = 200


class RepoAccessError(RuntimeError):
    pass


def _roots() -> list[str]:
    roots = settings.repo_roots_list
    if not roots:
        raise RepoAccessError(
            "Akses repo belum diaktifkan. Set REPO_ROOTS di .env ke folder "
            "yang boleh dibaca Stella (mis. folder proyek PMS)."
        )
    return roots


def _resolve(path: str) -> tuple[str, str]:
    """Resolve `path` against allowed roots. Returns (root, abs_path).

    Raises RepoAccessError on escape attempts (.., absolute paths outside
    roots, symlinks pointing outside).
    """
    roots = _roots()
    requested = (path or "").strip().strip('"').strip("'")
    if not requested:
        raise RepoAccessError("Path kosong.")

    candidates: list[str] = []
    if os.path.isabs(requested):
        candidates = [os.path.realpath(requested)]
    else:
        candidates = [os.path.realpath(os.path.join(r, requested)) for r in roots]

    for abs_path in candidates:
        for root in roots:
            real_root = os.path.realpath(root)
            if abs_path == real_root or abs_path.startswith(real_root + os.sep):
                if os.path.islink(abs_path) and not abs_path.startswith(real_root + os.sep):
                    continue
                return real_root, abs_path
    raise RepoAccessError(
        f"Path di luar area yang diizinkan: {path}. "
        f"Area aktif: {', '.join(roots)}"
    )


def _is_binary(path: str, chunk: bytes) -> bool:
    if b"\x00" in chunk:
        return True
    _, ext = os.path.splitext(path)
    return ext.lower() in _SKIP_EXTS


def read_file(path: str, *, max_bytes: int | None = None) -> str:
    """Read a text file inside allowed roots, truncated."""
    _, abs_path = _resolve(path)
    if not os.path.isfile(abs_path):
        raise RepoAccessError(f"Bukan file: {path}")
    limit = max_bytes or settings.repo_max_file_bytes
    with open(abs_path, "rb") as fh:
        chunk = fh.read(limit + 1)
    truncated = len(chunk) > limit
    chunk = chunk[:limit]
    if _is_binary(abs_path, chunk):
        raise RepoAccessError(f"File biner tidak bisa dibaca: {path}")
    try:
        text = chunk.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RepoAccessError(f"File bukan teks UTF-8: {path}") from exc
    out = text[: settings.repo_max_output_chars]
    if truncated or len(text) > len(out):
        out += f"\n\n…(dipotong, file lebih besar dari {limit} byte)"
    return out


def list_dir(path: str = ".") -> str:
    """List entries of a directory inside allowed roots."""
    _, abs_path = _resolve(path)
    if not os.path.isdir(abs_path):
        raise RepoAccessError(f"Bukan folder: {path}")
    try:
        entries = sorted(os.listdir(abs_path))
    except OSError as exc:
        raise RepoAccessError(f"Tidak bisa membaca folder: {path}") from exc
    lines = []
    for e in entries[:_MAX_LIST_ENTRIES]:
        full = os.path.join(abs_path, e)
        suffix = "/" if os.path.isdir(full) else ""
        try:
            size = "" if os.path.isdir(full) else f" ({os.path.getsize(full)} B)"
        except OSError:
            size = ""
        lines.append(f"{e}{suffix}{size}")
    if len(entries) > _MAX_LIST_ENTRIES:
        lines.append(f"…(+{len(entries) - _MAX_LIST_ENTRIES} lagi)")
    return "\n".join(lines) if lines else "(folder kosong)"


def search_code(pattern: str, *, root: str = ".", ext: str = "") -> str:
    """Grep `pattern` (regex, case-insensitive) under a root dir."""
    _, abs_root = _resolve(root)
    if not os.path.isdir(abs_root):
        raise RepoAccessError(f"Bukan folder: {root}")
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise RepoAccessError(f"Regex tidak valid: {exc}") from exc

    exts = {e.strip().lower() for e in ext.split(",") if e.strip()} if ext else set()
    matches: list[str] = []
    max_matches = settings.repo_max_matches
    for dirpath, dirnames, filenames in os.walk(abs_root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in sorted(filenames):
            if exts and os.path.splitext(fn)[1].lower() not in exts:
                continue
            full = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(full) > settings.repo_max_file_bytes:
                    continue
                with open(full, "rb") as fh:
                    chunk = fh.read(settings.repo_max_file_bytes)
                if _is_binary(full, chunk):
                    continue
                text = chunk.decode("utf-8", errors="strict")
            except (OSError, UnicodeDecodeError):
                continue
            rel = os.path.relpath(full, abs_root)
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    matches.append(f"{rel}:{i}: {line.strip()[:200]}")
                    if len(matches) >= max_matches:
                        out = "\n".join(matches)
                        return out[: settings.repo_max_output_chars]
    if not matches:
        return "Nggak nemu yang cocok."
    out = "\n".join(matches)
    return out[: settings.repo_max_output_chars]


def summarize_tree(root: str = ".", *, depth: int = 2) -> str:
    """Compact directory tree (for repo orientation)."""
    _, abs_root = _resolve(root)
    if not os.path.isdir(abs_root):
        raise RepoAccessError(f"Bukan folder: {root}")
    lines: list[str] = []

    def _walk(current: str, prefix: str, level: int) -> None:
        if level > depth or len(lines) > _MAX_LIST_ENTRIES:
            return
        try:
            entries = sorted(os.listdir(current))
        except OSError:
            return
        entries = [e for e in entries if e not in _SKIP_DIRS and not e.startswith(".env")]
        for idx, e in enumerate(entries):
            last = idx == len(entries) - 1
            full = os.path.join(current, e)
            is_dir = os.path.isdir(full)
            # ASCII-only markers: safe on cp1252 consoles, Telegram, browsers.
            lines.append(f"{prefix}{'+-- ' if last else '|-- '}{e}{'/' if is_dir else ''}")
            if is_dir:
                _walk(full, prefix + ("    " if last else "|   "), level + 1)

    _walk(abs_root, "", 0)
    base = os.path.basename(abs_root.rstrip(os.sep)) or abs_root
    return f"{base}/\n" + "\n".join(lines)
