"""Web research pipeline: provenance, keyless Wikipedia, optional Brave, and
SSRF-safety of Brave-returned citation URLs. No test touches the real network.
"""

from __future__ import annotations

import httpx
from alfred.research.pipeline import ResearchPipeline
from alfred.research.sources import BraveSource, WikipediaSource
from conftest import run_async, stub_resolver

PUBLIC_IP = "93.184.216.34"


def _wiki_response(titles_and_snippets):
    return httpx.Response(
        200,
        json={"query": {"search": [{"title": t, "snippet": s} for t, s in titles_and_snippets]}},
    )


def _brave_response(results):
    return httpx.Response(200, json={"web": {"results": results}})


# --- pipeline disabled / empty query -----------------------------------------


def test_pipeline_disabled_by_default_never_touches_network(settings_factory):
    def forbidden(request: httpx.Request) -> httpx.Response:
        raise AssertionError("disabled research pipeline must never make a request")

    settings = settings_factory(web_research_enabled=False)
    pipeline = ResearchPipeline(settings, transport=httpx.MockTransport(forbidden))
    result = run_async(pipeline.run("anything"))
    assert result.used_web is False
    assert "disabled" in result.limitations[0]


def test_pipeline_empty_query_is_rejected_without_network(settings_factory):
    def forbidden(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must never make a request for an empty query")

    settings = settings_factory(web_research_enabled=True)
    pipeline = ResearchPipeline(
        settings, resolver=stub_resolver({}), transport=httpx.MockTransport(forbidden)
    )
    result = run_async(pipeline.run("   "))
    assert result.used_web is False
    assert "empty query" in result.limitations[0]


# --- wikipedia keyless source --------------------------------------------------


def test_pipeline_uses_wikipedia_when_no_brave_key_configured(settings_factory):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "en.wikipedia.org" in str(request.url)
        return _wiki_response([("Alfred Pennyworth (disambiguation avoided)", "A snippet.")])

    settings = settings_factory(web_research_enabled=True, web_search_provider="none")
    pipeline = ResearchPipeline(
        settings,
        resolver=stub_resolver({"en.wikipedia.org": [PUBLIC_IP]}),
        transport=httpx.MockTransport(handler),
    )
    result = run_async(pipeline.run("test query"))
    assert result.used_web is True
    assert result.providers_used == ["wikipedia"]
    assert any("broad web provider is not configured" in note for note in result.limitations)
    assert result.sources[0].source == "wikipedia"
    assert result.sources[0].authoritative is True
    assert result.sources[0].url.startswith("https://en.wikipedia.org/wiki/")


def test_wikipedia_failure_is_reported_as_a_limitation_not_a_crash(settings_factory):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream broken")

    settings = settings_factory(web_research_enabled=True)
    pipeline = ResearchPipeline(
        settings,
        resolver=stub_resolver({"en.wikipedia.org": [PUBLIC_IP]}),
        transport=httpx.MockTransport(handler),
    )
    result = run_async(pipeline.run("test query"))
    assert result.sources == []
    assert any("wikipedia unavailable" in note for note in result.limitations)


def test_wikipedia_source_builds_fixed_domain_citation_url():
    def handler(request: httpx.Request) -> httpx.Response:
        return _wiki_response([("Multi Word Title", "snippet text")])

    class _Settings:
        web_user_agent = "AlfredAssistant/test"
        web_fetch_timeout_seconds = 2.0
        web_fetch_max_bytes = 4096
        web_max_redirects = 2

    source = WikipediaSource(
        resolver=stub_resolver({"en.wikipedia.org": [PUBLIC_IP]}), transport=httpx.MockTransport(handler)
    )
    results = run_async(source.search("q", settings=_Settings(), limit=3, excerpt_chars=100))
    assert results[0].url == "https://en.wikipedia.org/wiki/Multi_Word_Title"
    assert results[0].authoritative is True


# --- brave broad provider + SSRF safety of returned citation URLs -----------


def test_pipeline_uses_brave_when_configured_and_orders_authoritative_first(settings_factory):
    def handler(request: httpx.Request) -> httpx.Response:
        if "wikipedia" in str(request.url):
            return _wiki_response([("Wiki Result", "wiki snippet")])
        return _brave_response(
            [{"title": "Brave Result", "url": "https://public.example/page", "description": "d"}]
        )

    settings = settings_factory(
        web_research_enabled=True, web_search_provider="brave", brave_api_key="test-brave-key"
    )
    resolver = stub_resolver(
        {
            "en.wikipedia.org": [PUBLIC_IP],
            "public.example": [PUBLIC_IP],
            "api.search.brave.com": [PUBLIC_IP],
        }
    )
    pipeline = ResearchPipeline(settings, resolver=resolver, transport=httpx.MockTransport(handler))
    result = run_async(pipeline.run("query"))
    assert set(result.providers_used) == {"wikipedia", "brave"}
    # Authoritative (wikipedia) sources must be listed first.
    assert result.sources[0].source == "wikipedia"
    assert any(s.source == "brave" for s in result.sources)


def test_brave_source_filters_out_ssrf_unsafe_citation_urls():
    """The core "Brave-returned citation URLs are SSRF-safe" guarantee: a
    result pointing at a private/internal address must never be surfaced as a
    citation, even though Brave itself returned it."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _brave_response(
            [
                {"title": "Safe Result", "url": "https://public.example/ok", "description": "fine"},
                {
                    "title": "Malicious Internal Result",
                    "url": "https://internal.example/admin",
                    "description": "should never surface",
                },
                {
                    "title": "Literal Private IP Result",
                    "url": "https://10.0.0.5/secret",
                    "description": "should never surface either",
                },
                {
                    "title": "Metadata Endpoint Result",
                    "url": "https://169.254.169.254/latest/meta-data/",
                    "description": "cloud metadata must never surface",
                },
            ]
        )

    resolver = stub_resolver(
        {
            "public.example": [PUBLIC_IP],
            "internal.example": ["10.0.0.9"],
            "api.search.brave.com": [PUBLIC_IP],
        }
    )
    source = BraveSource("test-key", resolver=resolver, transport=httpx.MockTransport(handler))

    class _Settings:
        web_user_agent = "AlfredAssistant/test"
        web_fetch_timeout_seconds = 2.0
        web_fetch_max_bytes = 4096
        web_max_redirects = 2

    results = run_async(source.search("q", settings=_Settings(), limit=10, excerpt_chars=200))
    urls = [r.url for r in results]
    assert urls == ["https://public.example/ok"]
    assert "https://internal.example/admin" not in urls
    assert "https://10.0.0.5/secret" not in urls
    assert "https://169.254.169.254/latest/meta-data/" not in urls


def test_brave_source_skips_results_missing_title_or_url():
    def handler(request: httpx.Request) -> httpx.Response:
        return _brave_response(
            [
                {"title": "", "url": "https://public.example/a", "description": "no title"},
                {"title": "No URL", "url": "", "description": "no url"},
                {"title": "Good", "url": "https://public.example/b", "description": "fine"},
            ]
        )

    resolver = stub_resolver({"public.example": [PUBLIC_IP], "api.search.brave.com": [PUBLIC_IP]})
    source = BraveSource("test-key", resolver=resolver, transport=httpx.MockTransport(handler))

    class _Settings:
        web_user_agent = "AlfredAssistant/test"
        web_fetch_timeout_seconds = 2.0
        web_fetch_max_bytes = 4096
        web_max_redirects = 2

    results = run_async(source.search("q", settings=_Settings(), limit=10, excerpt_chars=200))
    assert [r.title for r in results] == ["Good"]


def test_brave_source_sends_subscription_token_header_not_in_url():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["token_header"] = request.headers.get("x-subscription-token")
        captured["url"] = str(request.url)
        return _brave_response([])

    resolver = stub_resolver({"api.search.brave.com": [PUBLIC_IP]})
    source = BraveSource("super-secret-brave-key", resolver=resolver, transport=httpx.MockTransport(handler))

    class _Settings:
        web_user_agent = "AlfredAssistant/test"
        web_fetch_timeout_seconds = 2.0
        web_fetch_max_bytes = 4096
        web_max_redirects = 2

    run_async(source.search("q", settings=_Settings(), limit=3, excerpt_chars=100))
    assert captured["token_header"] == "super-secret-brave-key"
    assert "super-secret-brave-key" not in captured["url"]


def test_brave_failure_is_reported_as_a_limitation(settings_factory):
    def handler(request: httpx.Request) -> httpx.Response:
        if "wikipedia" in str(request.url):
            return _wiki_response([])
        return httpx.Response(500, text="brave is down")

    settings = settings_factory(
        web_research_enabled=True, web_search_provider="brave", brave_api_key="key"
    )
    resolver = stub_resolver({"en.wikipedia.org": [PUBLIC_IP], "api.search.brave.com": [PUBLIC_IP]})
    pipeline = ResearchPipeline(settings, resolver=resolver, transport=httpx.MockTransport(handler))
    result = run_async(pipeline.run("query"))
    assert any("brave search unavailable" in note for note in result.limitations)


def test_pipeline_without_brave_key_never_calls_brave_endpoint(settings_factory):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "brave" not in str(request.url), "must never call Brave without a configured key"
        return _wiki_response([("T", "s")])

    settings = settings_factory(web_research_enabled=True, web_search_provider="none")
    pipeline = ResearchPipeline(
        settings,
        resolver=stub_resolver({"en.wikipedia.org": [PUBLIC_IP]}),
        transport=httpx.MockTransport(handler),
    )
    result = run_async(pipeline.run("query"))
    assert "brave" not in result.providers_used


def test_pipeline_deep_depth_requests_more_results_and_longer_excerpts(settings_factory):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return _wiki_response([(f"Title {i}", "x" * 600) for i in range(5)])

    settings = settings_factory(web_research_enabled=True, web_max_results=5)
    pipeline = ResearchPipeline(
        settings,
        resolver=stub_resolver({"en.wikipedia.org": [PUBLIC_IP]}),
        transport=httpx.MockTransport(handler),
    )
    result = run_async(pipeline.run("query", depth="deep"))
    assert len(result.sources[0].excerpt) <= 500
    assert "srlimit=5" in captured["url"]


def test_pipeline_reports_retrieved_at_only_when_web_was_actually_used(settings_factory):
    settings = settings_factory(web_research_enabled=False)
    pipeline = ResearchPipeline(settings)
    result = run_async(pipeline.run("query"))
    assert result.retrieved_at is None
    assert result.used_web is False
