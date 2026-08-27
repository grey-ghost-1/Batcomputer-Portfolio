"""SSRF hardening: scheme/credential/port/address-class rejection, redirect
revalidation, oversized/non-text response rejection. No test touches the
real network -- every fetch uses an injected ``httpx.MockTransport`` and a
stub DNS resolver.
"""

from __future__ import annotations

import socket

import httpx
import pytest
from alfred import net_guard
from alfred.net_guard import FetchError, UnsafeUrlError, assess_url, fetch_json, fetch_text
from conftest import run_async, stub_resolver

PUBLIC_IP = "93.184.216.34"  # example.com's long-standing public IP


# --- scheme / credentials / port ---------------------------------------------


@pytest.mark.parametrize(
    "scheme", ["http", "file", "data", "javascript", "ftp", "ws", "wss", "gopher", "blob"]
)
def test_assess_url_rejects_disallowed_schemes(scheme):
    with pytest.raises(UnsafeUrlError):
        assess_url(f"{scheme}://example.com/", resolver=stub_resolver({"example.com": [PUBLIC_IP]}))


def test_assess_url_rejects_embedded_credentials():
    with pytest.raises(UnsafeUrlError, match="credentials"):
        assess_url(
            "https://user:pass@example.com/", resolver=stub_resolver({"example.com": [PUBLIC_IP]})
        )


def test_assess_url_rejects_nonstandard_port():
    with pytest.raises(UnsafeUrlError, match="port"):
        assess_url(
            "https://example.com:8443/", resolver=stub_resolver({"example.com": [PUBLIC_IP]})
        )


def test_assess_url_accepts_explicit_standard_port():
    assessment = assess_url(
        "https://example.com:443/", resolver=stub_resolver({"example.com": [PUBLIC_IP]})
    )
    assert assessment.port == 443


def test_assess_url_rejects_backslashes():
    with pytest.raises(UnsafeUrlError, match="backslash"):
        assess_url("https://example.com\\@evil.example/")


def test_assess_url_rejects_missing_host():
    with pytest.raises(UnsafeUrlError, match="host"):
        assess_url("https:///path-only")


# --- localhost / loopback / private / link-local / reserved / multicast ----


def test_assess_url_rejects_localhost_hostname():
    with pytest.raises(UnsafeUrlError, match="localhost"):
        assess_url("https://localhost/")


@pytest.mark.parametrize("ip", ["127.0.0.1", "::1"])
def test_assess_url_rejects_literal_loopback_ip(ip):
    host = f"[{ip}]" if ":" in ip else ip
    with pytest.raises(UnsafeUrlError, match="loopback"):
        assess_url(f"https://{host}/")


@pytest.mark.parametrize("ip", ["10.1.2.3", "172.16.0.5", "192.168.1.1"])
def test_assess_url_rejects_private_ip_via_dns(ip):
    with pytest.raises(UnsafeUrlError, match="private"):
        assess_url("https://internal.example/", resolver=stub_resolver({"internal.example": [ip]}))


def test_assess_url_rejects_link_local_ip():
    # Python's ipaddress.is_private() is a superset that also covers
    # link-local addresses, and net_guard checks is_private() first, so the
    # message says "private" rather than "link-local" for IPv4 -- the
    # security property under test is that the address is unconditionally
    # rejected either way.
    with pytest.raises(UnsafeUrlError, match="private|link-local"):
        assess_url("https://lla.example/", resolver=stub_resolver({"lla.example": ["169.254.1.1"]}))


def test_assess_url_rejects_reserved_ip():
    # As above: Python classifies the 240.0.0.0/4 reserved block as private
    # too, so "private" is reported first; it is still unconditionally
    # rejected.
    with pytest.raises(UnsafeUrlError, match="private|reserved"):
        assess_url("https://res.example/", resolver=stub_resolver({"res.example": ["240.0.0.1"]}))


def test_assess_url_rejects_multicast_ip():
    with pytest.raises(UnsafeUrlError, match="multicast"):
        assess_url("https://mc.example/", resolver=stub_resolver({"mc.example": ["224.0.0.1"]}))


def test_assess_url_rejects_unspecified_ip():
    # 0.0.0.0 is also classified as "private" by Python's ipaddress module,
    # which is checked before the more specific is_unspecified branch.
    with pytest.raises(UnsafeUrlError, match="private|unspecified"):
        assess_url("https://unspec.example/", resolver=stub_resolver({"unspec.example": ["0.0.0.0"]}))


@pytest.mark.parametrize("ip", ["169.254.169.254", "100.100.100.200"])
def test_assess_url_rejects_cloud_metadata_ip(ip):
    with pytest.raises(UnsafeUrlError, match="metadata"):
        assess_url("https://meta.example/", resolver=stub_resolver({"meta.example": [ip]}))


def test_assess_url_rejects_ipv4_mapped_ipv6_smuggling_private_range():
    with pytest.raises(UnsafeUrlError, match="private"):
        assess_url(
            "https://mapped.example/", resolver=stub_resolver({"mapped.example": ["::ffff:10.0.0.1"]})
        )


def test_assess_url_rejects_literal_private_ip_host():
    with pytest.raises(UnsafeUrlError, match="private"):
        assess_url("https://192.168.0.1/")


def test_assess_url_accepts_public_ip_and_hostname():
    assessment = assess_url("https://example.com/", resolver=stub_resolver({"example.com": [PUBLIC_IP]}))
    assert assessment.host == "example.com"
    assert assessment.ip_addresses == [PUBLIC_IP]


def test_assess_url_dns_failure_is_rejected():
    def failing_resolver(host):
        raise socket.gaierror("simulated DNS failure")

    with pytest.raises(UnsafeUrlError, match="DNS resolution failed"):
        assess_url("https://nowhere.example/", resolver=failing_resolver)


def test_assess_url_empty_dns_result_is_rejected():
    with pytest.raises(UnsafeUrlError, match="did not resolve"):
        assess_url("https://empty.example/", resolver=stub_resolver({"empty.example": []}))


# --- fetch_text / fetch_json: redirects, size, content-type, timeouts ------


def _settings(**overrides):
    class _S:
        web_user_agent = "AlfredAssistant/test"
        web_fetch_timeout_seconds = 2.0
        web_fetch_max_bytes = 1024
        web_max_redirects = 2

    settings = _S()
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def test_fetch_text_success_returns_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="hello world", headers={"content-type": "text/plain"})

    transport = httpx.MockTransport(handler)
    result = run_async(
        fetch_text(
            "https://example.com/data",
            settings=_settings(),
            resolver=stub_resolver({"example.com": [PUBLIC_IP]}),
            transport=transport,
        )
    )
    assert result == "hello world"


def test_fetch_text_rejects_oversized_response():
    big_body = b"x" * 4096

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big_body, headers={"content-type": "text/plain"})

    transport = httpx.MockTransport(handler)
    with pytest.raises(FetchError, match="byte limit"):
        run_async(
            fetch_text(
                "https://example.com/big",
                settings=_settings(web_fetch_max_bytes=16),
                resolver=stub_resolver({"example.com": [PUBLIC_IP]}),
                transport=transport,
            )
        )


def test_fetch_text_rejects_non_text_content_type():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"\x00\x01binarydata", headers={"content-type": "application/octet-stream"}
        )

    transport = httpx.MockTransport(handler)
    with pytest.raises(FetchError, match="content type"):
        run_async(
            fetch_text(
                "https://example.com/bin",
                settings=_settings(),
                resolver=stub_resolver({"example.com": [PUBLIC_IP]}),
                transport=transport,
            )
        )


@pytest.mark.parametrize("content_type", ["application/json", "text/plain", "text/html", "text/xml"])
def test_fetch_text_allows_expected_content_types(content_type):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="{}", headers={"content-type": content_type})

    transport = httpx.MockTransport(handler)
    result = run_async(
        fetch_text(
            "https://example.com/ok",
            settings=_settings(),
            resolver=stub_resolver({"example.com": [PUBLIC_IP]}),
            transport=transport,
        )
    )
    assert result == "{}"


def test_fetch_text_redirect_hop_is_revalidated_and_rejects_private_target():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "redirector.example":
            return httpx.Response(302, headers={"location": "https://internal.example/secret"})
        raise AssertionError("must not be reached: redirect target was not revalidated")

    transport = httpx.MockTransport(handler)
    resolver = stub_resolver({"redirector.example": [PUBLIC_IP], "internal.example": ["10.0.0.9"]})
    with pytest.raises(UnsafeUrlError, match="private"):
        run_async(
            fetch_text(
                "https://redirector.example/start",
                settings=_settings(),
                resolver=resolver,
                transport=transport,
            )
        )


def test_fetch_text_too_many_redirects_is_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://example.com/next"})

    transport = httpx.MockTransport(handler)
    with pytest.raises(FetchError, match="too many redirects"):
        run_async(
            fetch_text(
                "https://example.com/start",
                settings=_settings(web_max_redirects=1),
                resolver=stub_resolver({"example.com": [PUBLIC_IP]}),
                transport=transport,
            )
        )


def test_fetch_text_redirect_without_location_header_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302)

    transport = httpx.MockTransport(handler)
    with pytest.raises(FetchError, match="location"):
        run_async(
            fetch_text(
                "https://example.com/start",
                settings=_settings(),
                resolver=stub_resolver({"example.com": [PUBLIC_IP]}),
                transport=transport,
            )
        )


def test_fetch_text_timeout_is_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout", request=request)

    transport = httpx.MockTransport(handler)
    with pytest.raises(FetchError, match="timed out"):
        run_async(
            fetch_text(
                "https://example.com/slow",
                settings=_settings(),
                resolver=stub_resolver({"example.com": [PUBLIC_IP]}),
                transport=transport,
            )
        )


def test_fetch_text_upstream_error_status_is_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="oops", headers={"content-type": "text/plain"})

    transport = httpx.MockTransport(handler)
    with pytest.raises(FetchError, match="status 500"):
        run_async(
            fetch_text(
                "https://example.com/broken",
                settings=_settings(),
                resolver=stub_resolver({"example.com": [PUBLIC_IP]}),
                transport=transport,
            )
        )


def test_fetch_text_connection_error_is_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated connection failure", request=request)

    transport = httpx.MockTransport(handler)
    with pytest.raises(FetchError, match="request failed"):
        run_async(
            fetch_text(
                "https://example.com/down",
                settings=_settings(),
                resolver=stub_resolver({"example.com": [PUBLIC_IP]}),
                transport=transport,
            )
        )


def test_fetch_json_parses_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True}, headers={"content-type": "application/json"})

    transport = httpx.MockTransport(handler)
    result = run_async(
        fetch_json(
            "https://example.com/data.json",
            settings=_settings(),
            resolver=stub_resolver({"example.com": [PUBLIC_IP]}),
            transport=transport,
        )
    )
    assert result == {"ok": True}


def test_fetch_json_rejects_invalid_json_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json", headers={"content-type": "application/json"})

    transport = httpx.MockTransport(handler)
    with pytest.raises(FetchError, match="not valid JSON"):
        run_async(
            fetch_json(
                "https://example.com/bad.json",
                settings=_settings(),
                resolver=stub_resolver({"example.com": [PUBLIC_IP]}),
                transport=transport,
            )
        )


def test_fetch_never_uses_real_dns_or_sockets_by_default(monkeypatch):
    """Defence in depth: if a test forgets to stub the resolver/transport, it
    must fail loudly rather than silently reaching the real network."""

    def forbidden_resolver(host):
        raise AssertionError("a test attempted real DNS resolution")

    def forbidden_handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("a test attempted a real network call")

    monkeypatch.setattr(net_guard, "default_resolver", forbidden_resolver)
    transport = httpx.MockTransport(forbidden_handler)
    with pytest.raises(UnsafeUrlError):
        # example.com resolves via the *forbidden* default resolver only if we
        # do not pass resolver explicitly -- prove the guard still fires on
        # an obviously-disallowed scheme before ever touching DNS/socket.
        run_async(
            fetch_text("http://example.com/", settings=_settings(), transport=transport)
        )
