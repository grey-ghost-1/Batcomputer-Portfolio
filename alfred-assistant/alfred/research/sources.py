"""Web research sources.

A keyless narrow source (Wikipedia) works out of the box; a broad provider
(Brave Search) is used only when an API key is configured. Every source is
fetched through the SSRF-hardened :mod:`alfred.net_guard`, targets a fixed API
host, and normalises results to a common shape with a UTC retrieval timestamp.
Citation URLs are surfaced for the reader but never fetched server-side.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from urllib.parse import quote, urlencode

import httpx

from .. import net_guard
from ..net_guard import Resolver

if TYPE_CHECKING:
    from ..config import Settings

_TAG = re.compile(r"<[^>]+>")

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_PAGE = "https://en.wikipedia.org/wiki/"
BRAVE_API = "https://api.search.brave.com/res/v1/web/search"


def strip_html(text: str) -> str:
    return html.unescape(_TAG.sub("", text or "")).strip()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RetrievedSource:
    title: str
    url: str
    source: str
    excerpt: str
    retrieved_at: str
    authoritative: bool = False

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "excerpt": self.excerpt,
            "retrieved_at": self.retrieved_at,
            "authoritative": self.authoritative,
        }


class WikipediaSource:
    """Keyless encyclopedic search via the MediaWiki action API."""

    name = "wikipedia"
    authoritative = True

    def __init__(self, *, resolver: Resolver | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._resolver = resolver or net_guard.default_resolver
        self._transport = transport

    async def search(
        self, query: str, *, settings: "Settings", limit: int, excerpt_chars: int
    ) -> list[RetrievedSource]:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "srlimit": max(1, min(limit, 10)),
            "srprop": "snippet",
        }
        url = f"{WIKIPEDIA_API}?{urlencode(params)}"
        data = await net_guard.fetch_json(
            url, settings=settings, resolver=self._resolver, transport=self._transport
        )
        retrieved_at = utc_now_iso()
        results = ((data or {}).get("query") or {}).get("search") or []
        sources: list[RetrievedSource] = []
        for item in results[:limit]:
            title = str(item.get("title", "")).strip()
            if not title:
                continue
            excerpt = strip_html(str(item.get("snippet", "")))[:excerpt_chars]
            page_url = WIKIPEDIA_PAGE + quote(title.replace(" ", "_"))
            sources.append(
                RetrievedSource(
                    title=title,
                    url=page_url,
                    source=self.name,
                    excerpt=excerpt,
                    retrieved_at=retrieved_at,
                    authoritative=True,
                )
            )
        return sources


class BraveSource:
    """Broad web search via the Brave Search API (requires an API key)."""

    name = "brave"
    authoritative = False

    def __init__(
        self, api_key: str, *, resolver: Resolver | None = None, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._api_key = api_key
        self._resolver = resolver or net_guard.default_resolver
        self._transport = transport

    async def search(
        self, query: str, *, settings: "Settings", limit: int, excerpt_chars: int
    ) -> list[RetrievedSource]:
        params = {"q": query, "count": max(1, min(limit, 20))}
        url = f"{BRAVE_API}?{urlencode(params)}"
        data = await net_guard.fetch_json(
            url,
            settings=settings,
            resolver=self._resolver,
            transport=self._transport,
            headers={"X-Subscription-Token": self._api_key, "Accept": "application/json"},
        )
        retrieved_at = utc_now_iso()
        results = ((data or {}).get("web") or {}).get("results") or []
        sources: list[RetrievedSource] = []
        for item in results[:limit]:
            title = strip_html(str(item.get("title", ""))).strip()
            page_url = str(item.get("url", "")).strip()
            if not title or not page_url:
                continue
            try:
                net_guard.assess_url(page_url, resolver=self._resolver)
            except net_guard.UnsafeUrlError:
                continue
            excerpt = strip_html(str(item.get("description", "")))[:excerpt_chars]
            sources.append(
                RetrievedSource(
                    title=title,
                    url=page_url,
                    source=self.name,
                    excerpt=excerpt,
                    retrieved_at=retrieved_at,
                    authoritative=False,
                )
            )
        return sources
