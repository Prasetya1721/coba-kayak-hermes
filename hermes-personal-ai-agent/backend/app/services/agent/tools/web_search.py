"""Web search tool: SerpAPI or Brave Search, with an LLM-facing summariser."""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_SERPAPI_URL = "https://serpapi.com/search.json"
_BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


class WebSearchError(RuntimeError):
    pass


async def web_search(query: str, *, limit: int = 5) -> list[dict[str, str]]:
    """Return a list of {title, link, snippet} results."""
    if settings.search_provider == "serpapi" and settings.serpapi_api_key:
        return await _serpapi(query, limit)
    if settings.search_provider == "brave" and settings.brave_search_api_key:
        return await _brave(query, limit)
    raise WebSearchError(
        "Web search belum dikonfigurasi. Set SEARCH_PROVIDER + API key di .env"
    )


async def _serpapi(query: str, limit: int) -> list[dict[str, str]]:
    params = {
        "q": query,
        "api_key": settings.serpapi_api_key,
        "engine": "google",
        "num": limit,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(_SERPAPI_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
    out: list[dict[str, str]] = []
    for item in data.get("organic_results", [])[:limit]:
        out.append(
            {
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
        )
    return out


async def _brave(query: str, limit: int) -> list[dict[str, str]]:
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": settings.brave_search_api_key,
    }
    params = {"q": query, "count": limit}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(_BRAVE_URL, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
    out: list[dict[str, str]] = []
    for item in data.get("web", {}).get("results", [])[:limit]:
        out.append(
            {
                "title": item.get("title", ""),
                "link": item.get("url", ""),
                "snippet": item.get("description", ""),
            }
        )
    return out


def format_results(results: list[dict[str, str]]) -> str:
    if not results:
        return "Tidak ada hasil pencarian."
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}\n   {r['link']}\n   {r['snippet']}")
    return "\n".join(lines)
