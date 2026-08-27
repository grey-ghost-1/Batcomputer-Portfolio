"""SSRF-hardened outbound HTTP for the web research pipeline.

Neither the model nor the browser ever fetches arbitrary URLs. Only the research
pipeline reaches the network, and only through :func:`fetch_json`/:func:`fetch_text`,
which enforce: HTTPS only; no embedded credentials; standard ports only; and
rejection of loopback/private/link-local/reserved/multicast/unspecified IPs and
known cloud-metadata endpoints. DNS is validated before connecting and every
redirect hop is re-validated. Responses are bounded by timeout, byte count, and
content type. Retrieved bytes are returned as untrusted data.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import httpx

if TYPE_CHECKING:
    from .config import Settings

Resolver = Callable[[str], list[str]]

ALLOWED_SCHEMES = {"https"}
ALLOWED_PORTS = {443}
BLOCKED_SCHEMES = {"http", "file", "data", "javascript", "ftp", "ws", "wss", "gopher", "blob"}
CLOUD_METADATA_IPS = {"169.254.169.254", "fd00:ec2::254", "100.100.100.200"}
ALLOWED_CONTENT_TYPES = ("application/json", "text/plain", "text/html")


class UnsafeUrlError(ValueError):
    """Raised when a URL fails SSRF validation."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class FetchError(RuntimeError):
    """Raised when a permitted fetch fails at the network/content layer."""


@dataclass
class UrlAssessment:
    url: str
    host: str
    port: int
    ip_addresses: list[str]


def default_resolver(host: str) -> list[str]:
    """Resolve ``host`` to a list of IP strings using the stdlib."""

    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return sorted({str(info[4][0]) for info in infos})


def _ip_block_reason(ip_text: str) -> str | None:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return "unparseable IP address"
    if ip_text in CLOUD_METADATA_IPS:
        return "cloud metadata address is forbidden"
    if ip.is_loopback:
        return "loopback address is forbidden"
    if ip.is_private:
        return "private address is forbidden"
    if ip.is_link_local:
        return "link-local address is forbidden"
    if ip.is_reserved:
        return "reserved address is forbidden"
    if ip.is_multicast:
        return "multicast address is forbidden"
    if ip.is_unspecified:
        return "unspecified address is forbidden"
    # IPv4-mapped IPv6 (::ffff:a.b.c.d) can smuggle private ranges.
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        return _ip_block_reason(str(mapped))
    return None


def assess_url(url: str, *, resolver: Resolver = default_resolver) -> UrlAssessment:
    """Validate ``url`` for SSRF safety, resolving and checking every IP."""

    if not url or not isinstance(url, str):
        raise UnsafeUrlError("a URL string is required")
    if "\\" in url:
        raise UnsafeUrlError("backslashes are not permitted in URLs")
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise UnsafeUrlError("URL could not be parsed") from exc

    scheme = parts.scheme.lower()
    if scheme in BLOCKED_SCHEMES:
        raise UnsafeUrlError(f"scheme '{scheme}' is not permitted")
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrlError("only https URLs are permitted")
    if parts.username or parts.password:
        raise UnsafeUrlError("embedded credentials are not permitted")

    host = parts.hostname
    if not host:
        raise UnsafeUrlError("URL host is missing")

    try:
        port = parts.port or 443
    except ValueError as exc:
        raise UnsafeUrlError("URL port is invalid") from exc
    if port not in ALLOWED_PORTS:
        raise UnsafeUrlError(f"non-standard port {port} is not permitted")

    # A literal IP host is validated directly; otherwise resolve via DNS.
    try:
        ipaddress.ip_address(host)
        candidate_ips = [host]
    except ValueError:
        if host.lower() == "localhost":
            raise UnsafeUrlError("localhost is forbidden") from None
        try:
            candidate_ips = resolver(host)
        except (socket.gaierror, OSError) as exc:
            raise UnsafeUrlError(f"DNS resolution failed for host '{host}'") from exc
        if not candidate_ips:
            raise UnsafeUrlError(f"host '{host}' did not resolve to any address") from None

    for ip_text in candidate_ips:
        reason = _ip_block_reason(ip_text)
        if reason:
            raise UnsafeUrlError(f"{reason} ({ip_text})")

    return UrlAssessment(url=url, host=host, port=port, ip_addresses=candidate_ips)


def _check_content_type(content_type: str | None) -> None:
    if content_type is None:
        return
    main = content_type.split(";", 1)[0].strip().lower()
    if main and not any(main == allowed or main.startswith("text/") for allowed in ALLOWED_CONTENT_TYPES):
        raise FetchError(f"unsupported content type '{main}'")


async def _read_capped(response: httpx.Response, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise FetchError("response exceeded the byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


async def fetch_text(
    url: str,
    *,
    settings: "Settings",
    resolver: Resolver = default_resolver,
    transport: httpx.AsyncBaseTransport | None = None,
    headers: dict[str, str] | None = None,
) -> str:
    """Fetch a URL as text under strict SSRF and size controls.

    Redirects are followed manually and each hop is re-validated. ``transport``
    is injectable so tests never touch the network.
    """

    request_headers = {
        "User-Agent": settings.web_user_agent,
        "Accept": "application/json, text/plain, text/html;q=0.5",
    }
    if headers:
        request_headers.update(headers)

    timeout = httpx.Timeout(
        connect=settings.web_fetch_timeout_seconds,
        read=settings.web_fetch_timeout_seconds,
        write=settings.web_fetch_timeout_seconds,
        pool=settings.web_fetch_timeout_seconds,
    )

    current_url = url
    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=timeout,
        transport=transport,
        trust_env=False,
    ) as client:
        for _ in range(settings.web_max_redirects + 1):
            assess_url(current_url, resolver=resolver)
            try:
                response = await client.get(current_url, headers=request_headers)
            except httpx.TimeoutException as exc:
                raise FetchError("request timed out") from exc
            except httpx.HTTPError as exc:
                raise FetchError(f"request failed: {exc.__class__.__name__}") from exc

            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise FetchError("redirect without a location header")
                current_url = str(httpx.URL(current_url).join(location))
                await response.aclose()
                continue

            _check_content_type(response.headers.get("content-type"))
            try:
                body = await _read_capped(response, settings.web_fetch_max_bytes)
            finally:
                await response.aclose()
            if response.status_code >= 400:
                raise FetchError(f"upstream returned status {response.status_code}")
            return body.decode(response.encoding or "utf-8", errors="replace")

    raise FetchError("too many redirects")


async def fetch_json(
    url: str,
    *,
    settings: "Settings",
    resolver: Resolver = default_resolver,
    transport: httpx.AsyncBaseTransport | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    import json

    text = await fetch_text(
        url,
        settings=settings,
        resolver=resolver,
        transport=transport,
        headers=headers,
    )
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise FetchError("response was not valid JSON") from exc
