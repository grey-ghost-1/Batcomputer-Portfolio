"""Shared pytest fixtures for the Alfred Assistant test suite.

No test in this suite ever performs a live network call: HTTP-capable code is
always exercised through an injected ``httpx.MockTransport`` (or a stub DNS
resolver), and every ``Settings`` instance built here points ``db_path`` and
``knowledge_root`` at pytest's isolated ``tmp_path`` so the real repository's
``alfred-assistant/alfred.db`` is never created or touched by the tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make ``import alfred`` work regardless of the current working directory the
# test runner was invoked from (repository root, ``alfred-assistant/``, or an
# IDE's own working directory), mirroring the sys.path bootstrap used by the
# sibling ``platform/tests`` suite in this repository.
ALFRED_ROOT = Path(__file__).resolve().parents[1]
if str(ALFRED_ROOT) not in sys.path:
    sys.path.insert(0, str(ALFRED_ROOT))

import asyncio  # noqa: E402
from collections.abc import Callable  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from alfred.actions.executors import DesktopLauncher  # noqa: E402
from alfred.config import Settings, get_settings  # noqa: E402

# A fixed, high-entropy token used across tests (40 hex characters: length 40,
# 16 unique symbols -- comfortably above the configured minimums of 32/10).
TEST_TOKEN = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"
OTHER_TOKEN = "0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a"


@pytest.fixture(autouse=True)
def _isolated_settings_cache():
    """Never let ``get_settings()``'s process-wide cache leak across tests."""

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def run_async(coro):
    """Drive a coroutine from a plain ``def`` test without pytest-asyncio."""

    return asyncio.run(coro)


class RecordingLauncher(DesktopLauncher):
    """A desktop launcher double that never touches the real OS.

    Used by every action-lifecycle test so "execute" can never actually start
    a process, open a browser, or touch the real clipboard -- it only records
    what *would* have been launched.
    """

    def __init__(self) -> None:
        self.executed: list[str] = []
        self.opened_urls: list[str] = []
        self.clipboard_writes: list[str] = []

    def open_executable(self, path) -> None:
        self.executed.append(str(path))

    def open_url(self, url: str) -> None:
        self.opened_urls.append(url)

    def set_clipboard(self, text: str) -> None:
        self.clipboard_writes.append(text)


@pytest.fixture
def launcher() -> RecordingLauncher:
    return RecordingLauncher()


@pytest.fixture
def approved_root(tmp_path: Path) -> Path:
    """A temp directory that stands in for an operator-approved filesystem root."""

    root = tmp_path / "approved-root"
    root.mkdir()
    return root


@pytest.fixture
def knowledge_dir(tmp_path: Path) -> Path:
    """An empty knowledge root; individual tests populate README/evidence files."""

    root = tmp_path / "knowledge"
    root.mkdir()
    return root


@pytest.fixture
def settings_factory(tmp_path: Path) -> Callable[..., Settings]:
    """Factory for a safe, fully isolated :class:`Settings` instance.

    Every field that could otherwise touch the real repository (``db_path``,
    ``knowledge_root``) is pinned under ``tmp_path`` by default so tests can
    never create or mutate ``alfred-assistant/alfred.db`` or depend on the
    live repository's documents unless a test explicitly opts in.
    """

    counter = {"n": 0}

    def _make(**overrides) -> Settings:
        counter["n"] += 1
        defaults = {
            "host": "127.0.0.1",
            "port": 8020,
            "action_token": TEST_TOKEN,
            "desktop_actions_enabled": False,
            "clipboard_enabled": False,
            "approved_roots": [],
            "allowed_executables": [],
            "allowed_url_hosts": [],
            "db_path": tmp_path / f"test-{counter['n']}.db",
            "knowledge_root": tmp_path / "empty-knowledge",
            "model_provider": "none",
            "web_research_enabled": False,
            "proposal_ttl_seconds": 180,
        }
        defaults.update(overrides)
        empty_knowledge = defaults["knowledge_root"]
        Path(empty_knowledge).mkdir(parents=True, exist_ok=True)
        return Settings(**defaults)

    return _make


@pytest.fixture
def settings(settings_factory) -> Settings:
    return settings_factory()


def make_transport(handler) -> httpx.MockTransport:
    """Wrap a request handler in an ``httpx.MockTransport`` (no real sockets)."""

    return httpx.MockTransport(handler)


def json_response(payload, status_code: int = 200, headers=None) -> httpx.Response:
    merged = {"content-type": "application/json"}
    if headers:
        merged.update(headers)
    import json as _json

    return httpx.Response(status_code, content=_json.dumps(payload).encode("utf-8"), headers=merged)


def stub_resolver(mapping: dict[str, list[str]]):
    """Return a resolver function usable with ``net_guard``/sources without DNS."""

    def _resolve(host: str) -> list[str]:
        try:
            return mapping[host]
        except KeyError as exc:
            raise OSError(f"no stub address configured for host {host!r}") from exc

    return _resolve
