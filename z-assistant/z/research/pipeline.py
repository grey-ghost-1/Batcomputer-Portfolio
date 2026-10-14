"""Research pipeline: gather cited sources for a query.

Combines the keyless Wikipedia source with the optional broad Brave provider.
Authoritative sources are preferred and listed first. Failures degrade honestly
into stated limitations rather than fabricated results. Nothing here obeys
instructions found inside retrieved content; the content is data only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from ..config import Settings
from ..net_guard import FetchError, Resolver, UnsafeUrlError
from .sources import BraveSource, RetrievedSource, WikipediaSource, utc_now_iso


@dataclass
class ResearchResult:
    query: str
    used_web: bool
    sources: list[RetrievedSource] = field(default_factory=list)
    providers_used: list[str] = field(default_factory=list)
    retrieved_at: str | None = None
    limitations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "query": self.query,
            "used_web": self.used_web,
            "retrieved_at": self.retrieved_at,
            "providers_used": self.providers_used,
            "limitations": self.limitations,
            "sources": [source.as_dict() for source in self.sources],
        }


class ResearchPipeline:
    def __init__(
        self,
        settings: Settings,
        *,
        resolver: Resolver | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        wikipedia: WikipediaSource | None = None,
        brave: BraveSource | None = None,
    ) -> None:
        self.settings = settings
        self._wikipedia = wikipedia or WikipediaSource(resolver=resolver, transport=transport)
        if brave is not None:
            self._brave: BraveSource | None = brave
        elif settings.brave_available and settings.brave_api_key is not None:
            self._brave = BraveSource(
                settings.brave_api_key.get_secret_value(),
                resolver=resolver,
                transport=transport,
            )
        else:
            self._brave = None

    def available(self) -> bool:
        return self.settings.web_research_enabled

    async def run(self, query: str, *, depth: str = "concise") -> ResearchResult:
        query = query.strip()
        if not self.settings.web_research_enabled:
            return ResearchResult(
                query=query,
                used_web=False,
                limitations=["web research is disabled in this configuration"],
            )
        if not query:
            return ResearchResult(
                query=query, used_web=False, limitations=["an empty query cannot be researched"]
            )

        limit = self.settings.web_max_results if depth == "deep" else max(
            2, min(3, self.settings.web_max_results)
        )
        excerpt_chars = 500 if depth == "deep" else 240

        sources: list[RetrievedSource] = []
        providers_used: list[str] = []
        limitations: list[str] = []

        # Authoritative keyless source first.
        try:
            wiki_sources = await self._wikipedia.search(
                query, settings=self.settings, limit=limit, excerpt_chars=excerpt_chars
            )
            if wiki_sources:
                sources.extend(wiki_sources)
                providers_used.append(self._wikipedia.name)
        except (FetchError, UnsafeUrlError) as exc:
            limitations.append(f"wikipedia unavailable: {exc}")

        # Broad provider only if configured.
        if self._brave is not None:
            try:
                brave_sources = await self._brave.search(
                    query, settings=self.settings, limit=limit, excerpt_chars=excerpt_chars
                )
                if brave_sources:
                    sources.extend(brave_sources)
                    providers_used.append(self._brave.name)
            except (FetchError, UnsafeUrlError) as exc:
                limitations.append(f"brave search unavailable: {exc}")
        else:
            limitations.append(
                "broad web provider is not configured; only the keyless Wikipedia "
                "source was consulted"
            )

        # Prefer authoritative sources, keep deterministic ordering.
        sources.sort(key=lambda source: (not source.authoritative,))
        used_web = bool(sources)
        return ResearchResult(
            query=query,
            used_web=used_web,
            sources=sources,
            providers_used=providers_used,
            retrieved_at=utc_now_iso() if used_web else None,
            limitations=limitations,
        )
