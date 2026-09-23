"""Web management tool: GitHub repo operations and Vercel deployments.

Tokens are resolved per-user from the encrypted credentials store, falling
back to operator-level env tokens. Nothing is ever logged.
"""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_GITHUB_API = "https://api.github.com"
_VERCEL_API = "https://api.vercel.com"


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
