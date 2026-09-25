"""Web search tool: SerpAPI, Brave Search, or free DuckDuckGo fallback.

DuckDuckGo needs no API key: the Instant Answer API is tried first, then the
lightweight html endpoint is scraped for organic results. Perfectly good for a
personal assistant; upgrade to SerpAPI/Brave when you need higher recall.
"""

from __future__ import annotations

import html as html_lib
import re

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_SERPAPI_URL = "https://serpapi.com/search.json"
_BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
_DDG_API_URL = "https://api.duckduckgo.com/"
_DDG_HTML_URL = "https://html.duckduckgo.com/html/"


class WebSearchError(RuntimeError):
    pass


async def web_search(query: str, *, limit: int = 5) -> list[dict[str, str]]:
    """Return a list of {title, link, snippet} results."""
    if settings.search_provider == "serpapi" and settings.serpapi_api_key:
        return await _serpapi(query, limit)
    if settings.search_provider == "brave" and settings.brave_search_api_key:
        return await _brave(query, limit)
    if settings.search_provider == "duckduckgo":
        return await _duckduckgo(query, limit)
    raise WebSearchError(
        "Web search belum dikonfigurasi. Set SEARCH_PROVIDER=duckduckgo "
        "(gratis, tanpa API key) atau serpapi/brave + API key di .env"
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


async def _duckduckgo(query: str, limit: int) -> list[dict[str, str]]:
    """Free search: Instant Answer API first, html scrape as fallback."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Hermes/1.0"}
    async with httpx.AsyncClient(timeout=20, headers=headers) as client:
        try:
            resp = await client.get(
                _DDG_API_URL,
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            log.warning("ddg_api_failed", error=str(exc))
            data = {}

        out: list[dict[str, str]] = []
        abstract = (data.get("AbstractText") or "").strip()
        if abstract:
            out.append(
                {
                    "title": data.get("Heading") or query,
                    "link": data.get("AbstractURL") or "",
                    "snippet": abstract,
                }
            )
        for topic in data.get("RelatedTopics", []) or []:
            if isinstance(topic, dict) and topic.get("Text"):
                out.append(
                    {
                        "title": (topic.get("Text") or "")[:120],
                        "link": topic.get("FirstURL") or "",
                        "snippet": topic.get("Text") or "",
                    }
                )
            if len(out) >= limit:
                return out[:limit]

        # Fallback: scrape the lightweight html endpoint for real web results.
        if len(out) < limit:
            out.extend(await _ddg_html(client, query, limit - len(out)))
        return out[:limit]


async def _ddg_html(
    client: httpx.AsyncClient, query: str, limit: int
) -> list[dict[str, str]]:
    try:
        resp = await client.post(_DDG_HTML_URL, data={"q": query})
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        log.warning("ddg_html_failed", error=str(exc))
        return []
    page = resp.text
    # Each organic result lives in <a class="result__a" href="...">title</a>
    # followed by <a class="result__snippet">snippet</a>.
    pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
        r".*?<a[^>]*class=\"result__snippet\"[^>]*>(.*?)</a>",
        re.DOTALL,
    )
    def _clean(raw: str) -> str:
        return html_lib.unescape(re.sub(r"<[^>]+>", "", raw)).strip()

    out: list[dict[str, str]] = []
    for href, title, snippet in pattern.findall(page):
        link = html_lib.unescape(href)
        if link.startswith("//"):
            link = "https:" + link
        if link.startswith("/"):
            continue
        out.append({"title": _clean(title), "link": link, "snippet": _clean(snippet)})
        if len(out) >= limit:
            break
    return out


def format_results(results: list[dict[str, str]]) -> str:
    if not results:
        return "Tidak ada hasil pencarian."
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}\n   {r['link']}\n   {r['snippet']}")
    return "\n".join(lines)
