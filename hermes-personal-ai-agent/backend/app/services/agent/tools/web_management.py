"""Web management tool: GitHub repo operations and Vercel deployments.

Tokens are resolved per-user from the encrypted credentials store, falling
back to operator-level env tokens. Nothing is ever logged.
"""

from __future__ import annotations

import base64
import re

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_GITHUB_API = "https://api.github.com"
_VERCEL_API = "https://api.vercel.com"

# Binary/irrelevant extensions never fetched as text from GitHub.
_SKIP_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".pdf", ".zip", ".tar",
    ".gz", ".7z", ".rar", ".exe", ".dll", ".so", ".dylib", ".pyc", ".class",
    ".o", ".a", ".lib", ".mp3", ".mp4", ".wav", ".avi", ".mov", ".ttf",
    ".otf", ".woff", ".woff2", ".eot", ".db", ".sqlite", ".lock",
}


def parse_repo(repo_ref: str) -> tuple[str, str]:
    """Accept 'owner/repo', a full GitHub URL, or 'git@github.com:owner/repo'.

    Returns (owner, repo). Raises WebManagementError on garbage.
    """
    ref = (repo_ref or "").strip()
    if not ref:
        raise WebManagementError("Repo kosong. Contoh: 'owner/repo'.")
    m = re.search(
        r"github\.com[/:]([^/\s]+)/([^/\s#?]+?)(?:\.git)?(?:[/#?].*)?$", ref
    )
    if m:
        return m.group(1), m.group(2)
    if "/" in ref:
        owner, _, name = ref.partition("/")
        owner, name = owner.strip(), name.strip().removesuffix(".git")
        if owner and name:
            return owner, name
    raise WebManagementError(
        f"Format repo nggak dikenali: {repo_ref}. Pakai 'owner/repo' atau URL GitHub."
    )


class WebManagementError(RuntimeError):
    pass


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def github_get_repo(owner: str, repo: str, *, token: str | None = None) -> dict:
    token = token or settings.github_token
    if not token:
        raise WebManagementError("GITHUB_TOKEN belum dikonfigurasi.")
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{_GITHUB_API}/repos/{owner}/{repo}", headers=_github_headers(token)
        )
        if resp.status_code == 404:
            return {"error": "Repository tidak ditemukan."}
        resp.raise_for_status()
        r = resp.json()
    return {
        "full_name": r.get("full_name"),
        "default_branch": r.get("default_branch"),
        "private": r.get("private"),
        "html_url": r.get("html_url"),
        "description": r.get("description"),
        "pushed_at": r.get("pushed_at"),
    }


async def github_push_file(
    *,
    owner: str,
    repo: str,
    path: str,
    content: str,
    message: str,
    branch: str | None = None,
    token: str | None = None,
) -> dict:
    """Create or update a single file via the Contents API (base64 encoded)."""
    import base64

    token = token or settings.github_token
    if not token:
        raise WebManagementError("GITHUB_TOKEN belum dikonfigurasi.")

    headers = _github_headers(token)
    url = f"{_GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
    payload: dict = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
    }
    if branch:
        payload["branch"] = branch

    async with httpx.AsyncClient(timeout=30) as client:
        existing = await client.get(url, headers=headers, params={"ref": branch} if branch else None)
        if existing.status_code == 200:
            payload["sha"] = existing.json().get("sha")
        resp = await client.put(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return {"commit": data.get("commit", {}).get("sha"), "path": path}


async def github_list_workflows(owner: str, repo: str, *, token: str | None = None) -> dict:
    token = token or settings.github_token
    if not token:
        raise WebManagementError("GITHUB_TOKEN belum dikonfigurasi.")
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{_GITHUB_API}/repos/{owner}/{repo}/actions/runs",
            headers=_github_headers(token),
            params={"per_page": 5},
        )
        resp.raise_for_status()
        runs = resp.json().get("workflow_runs", [])
    return {
        "runs": [
            {
                "name": r.get("name"),
                "status": r.get("status"),
                "conclusion": r.get("conclusion"),
                "created_at": r.get("created_at"),
            }
            for r in runs
        ]
    }


async def github_list_files(
    owner: str,
    repo: str,
    path: str = "",
    *,
    branch: str | None = None,
    token: str | None = None,
) -> dict:
    """List a directory (or file metadata) in a repo via the Contents API."""
    token = token or settings.github_token
    if not token:
        raise WebManagementError("GITHUB_TOKEN belum dikonfigurasi.")
    url = f"{_GITHUB_API}/repos/{owner}/{repo}/contents/{path.lstrip('/')}"
    params = {"ref": branch} if branch else None
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url, headers=_github_headers(token), params=params)
        if resp.status_code == 404:
            return {"error": f"Path tidak ditemukan: {path or '/'}"}
        resp.raise_for_status()
        data = resp.json()

    if isinstance(data, dict):
        return {
            "type": "file",
            "path": data.get("path"),
            "size": data.get("size"),
            "sha": data.get("sha"),
        }
    entries = []
    for item in data:
        entries.append(
            {
                "name": item.get("name"),
                "type": item.get("type"),
                "size": item.get("size"),
                "path": item.get("path"),
            }
        )
    entries.sort(key=lambda e: (e["type"] != "dir", e["name"] or ""))
    return {"path": path or "/", "entries": entries[:200]}


async def github_read_file(
    owner: str,
    repo: str,
    path: str,
    *,
    branch: str | None = None,
    token: str | None = None,
    max_chars: int = 12000,
) -> dict:
    """Read a text file from GitHub, decoding base64 and truncating."""
    token = token or settings.github_token
    if not token:
        raise WebManagementError("GITHUB_TOKEN belum dikonfigurasi.")
    path = (path or "").strip().lstrip("/")
    if not path:
        raise WebManagementError("Path file kosong.")
    _, ext = _split_ext(path)
    if ext in _SKIP_EXTS:
        raise WebManagementError(f"File biner/tidak didukung: {path}")

    url = f"{_GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
    params = {"ref": branch} if branch else None
    async with httpx.AsyncClient(timeout=25) as client:
        resp = await client.get(url, headers=_github_headers(token), params=params)
        if resp.status_code == 404:
            return {"error": f"File tidak ditemukan: {path} (branch: {branch or 'default'})"}
        resp.raise_for_status()
        data = resp.json()

    if isinstance(data, list):
        return {"error": f"{path} itu folder, bukan file. Pakai list_files."}
    if data.get("encoding") != "base64":
        return {"error": "Encoding file tidak didukung."}

    raw = base64.b64decode(data.get("content", ""))
    if b"\x00" in raw[:2000]:
        return {"error": f"{path} sepertinya biner."}
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")
    truncated = len(text) > max_chars
    return {
        "path": data.get("path"),
        "size": data.get("size"),
        "sha": data.get("sha"),
        "content": text[:max_chars],
        "truncated": truncated,
    }


async def github_search_code(
    owner: str,
    repo: str,
    query: str,
    *,
    token: str | None = None,
    limit: int = 20,
) -> dict:
    """Search code within a repo via the GitHub code-search API."""
    token = token or settings.github_token
    if not token:
        raise WebManagementError("GITHUB_TOKEN belum dikonfigurasi.")
    params = {"q": f"{query} repo:{owner}/{repo}", "per_page": min(limit, 30)}
    async with httpx.AsyncClient(timeout=25) as client:
        resp = await client.get(
            f"{_GITHUB_API}/search/code",
            headers=_github_headers(token),
            params=params,
        )
        if resp.status_code == 403:
            return {"error": "Rate limit / butuh scope repo. Cek token GitHub."}
        resp.raise_for_status()
        data = resp.json()
    items = data.get("items", [])[:limit]
    return {
        "total": data.get("total_count", 0),
        "matches": [{"path": i.get("path"), "url": i.get("html_url")} for i in items],
    }


async def github_list_commits(
    owner: str,
    repo: str,
    *,
    branch: str | None = None,
    limit: int = 10,
    token: str | None = None,
) -> dict:
    """Recent commits (who changed what, when)."""
    token = token or settings.github_token
    if not token:
        raise WebManagementError("GITHUB_TOKEN belum dikonfigurasi.")
    params = {"per_page": min(limit, 30)}
    if branch:
        params["sha"] = branch
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{_GITHUB_API}/repos/{owner}/{repo}/commits",
            headers=_github_headers(token),
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()
    return {
        "commits": [
            {
                "sha": (c.get("sha") or "")[:8],
                "message": (c.get("commit", {}).get("message") or "").splitlines()[0][:120],
                "author": c.get("commit", {}).get("author", {}).get("name"),
                "date": c.get("commit", {}).get("author", {}).get("date"),
            }
            for c in data[:limit]
        ]
    }


def _split_ext(path: str) -> tuple[str, str]:
    import os

    base = os.path.basename(path)
    if "." not in base:
        return base, ""
    stem, dot, ext = base.rpartition(".")
    return f"{stem}.{ext}", f".{ext.lower()}"


def _vercel_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def vercel_list_deployments(
    project: str, *, token: str | None = None, limit: int = 5
) -> dict:
    token = token or settings.vercel_token
    if not token:
        raise WebManagementError("VERCEL_TOKEN belum dikonfigurasi.")
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{_VERCEL_API}/v6/deployments",
            headers=_vercel_headers(token),
            params={"app": project, "limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()
    return {
        "deployments": [
            {
                "url": d.get("url"),
                "state": d.get("state"),
                "created_at": d.get("createdAt"),
                "target": d.get("target"),
            }
            for d in data.get("deployments", [])
        ]
    }


async def vercel_trigger_deploy(
    project: str, *, ref: str = "main", token: str | None = None
) -> dict:
    """Trigger a redeploy by creating a deployment from a Git ref."""
    token = token or settings.vercel_token
    if not token:
        raise WebManagementError("VERCEL_TOKEN belum dikonfigurasi.")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{_VERCEL_API}/v13/deployments",
            headers=_vercel_headers(token),
            json={"name": project, "gitSource": {"type": "github", "ref": ref}},
        )
        resp.raise_for_status()
        data = resp.json()
    return {"id": data.get("id"), "url": data.get("url"), "readyState": data.get("readyState")}
