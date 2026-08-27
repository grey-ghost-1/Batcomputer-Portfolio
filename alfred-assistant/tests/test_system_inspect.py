"""Read-only system inspection: secret redaction and honest process reporting.

The key guarantee under test: process *command-line arguments* are never
collected at all (a stronger property than "collected then redacted"), and
directory listings never return file contents.
"""

from __future__ import annotations

import sys
import types

import pytest
from alfred import system_inspect
from alfred.paths import PathError
from alfred.system_inspect import (
    directory_listing,
    disk_summary,
    process_summary,
    redact_secrets,
    system_summary,
)

# --- redact_secrets --------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "password=hunter2extra",
        "PASSWORD: hunter2extra",
        "token=abcd1234efgh5678",
        "api_key=sk-1234567890abcdef",
        "apikey: sk-1234567890abcdef",
        "Authorization: Bearer abcd1234",
        "secret=topvalue123",
        "access_key=AKIA1234567890",
        "private_key=abcdefgh12345",
    ],
)
def test_redact_secrets_masks_key_value_patterns(text):
    redacted = redact_secrets(text)
    assert "[redacted]" in redacted
    # The key name itself may remain, but the value must not.
    value = text.split("=", 1)[-1].split(":", 1)[-1].strip()
    assert value not in redacted


def test_redact_secrets_masks_long_high_entropy_blob():
    blob = "aB3dE9fG2hJ4kL6mN8pQ0rS1tU3vW5xY7zA9bC1dE3f"
    redacted = redact_secrets(f"payload: {blob}")
    assert blob not in redacted
    assert "[redacted]" in redacted


def test_redact_secrets_leaves_ordinary_text_untouched():
    text = "The service is running normally today."
    assert redact_secrets(text) == text


def test_redact_secrets_handles_empty_string():
    assert redact_secrets("") == ""


# --- system / disk summaries -------------------------------------------------------


def test_system_summary_is_labelled_read_only():
    summary = system_summary()
    assert "read-only" in summary["label"]
    assert summary["system"]
    assert "generated_at" in summary


def test_disk_summary_reports_root_name_only_not_absolute_path(tmp_path):
    nested = tmp_path / "Users" / "secret-user" / "Documents"
    nested.mkdir(parents=True)
    summary = disk_summary([nested])
    assert summary["volumes"][0]["root"] == "Documents"
    assert "secret-user" not in str(summary)
    assert str(tmp_path) not in str(summary)


def test_disk_summary_handles_missing_root_gracefully(tmp_path):
    missing = tmp_path / "does-not-exist"
    summary = disk_summary([missing])
    assert "error" in summary["volumes"][0]


# --- directory_listing: metadata only, confined, no contents -----------------


def test_directory_listing_returns_metadata_only_never_file_contents(tmp_path):
    secret_text = "THIS-EXACT-CONTENT-MUST-NEVER-APPEAR-IN-A-LISTING"
    (tmp_path / "file.txt").write_text(secret_text, encoding="utf-8")
    listing = directory_listing(tmp_path, ".", limit=50)
    assert secret_text not in str(listing)
    entry = listing["entries"][0]
    assert set(entry.keys()) == {"name", "kind", "is_symlink", "size_bytes", "modified_at"}
    assert entry["name"] == "file.txt"
    assert entry["kind"] == "file"


def test_directory_listing_reports_root_name_not_absolute_path(tmp_path):
    nested = tmp_path / "secret-owner"
    nested.mkdir()
    listing = directory_listing(nested, ".", limit=10)
    assert listing["root"] == "secret-owner"
    assert listing["path"] == "."
    assert str(tmp_path) not in str(listing)


def test_directory_listing_confined_rejects_traversal(tmp_path):
    with pytest.raises(PathError):
        directory_listing(tmp_path, "../", limit=10)


def test_directory_listing_rejects_missing_directory(tmp_path):
    with pytest.raises(PathError, match="does not exist"):
        directory_listing(tmp_path, "nope", limit=10)


def test_directory_listing_rejects_file_as_directory(tmp_path):
    (tmp_path / "afile.txt").write_text("x", encoding="utf-8")
    with pytest.raises(PathError, match="not a directory"):
        directory_listing(tmp_path, "afile.txt", limit=10)


def test_directory_listing_truncates_at_limit(tmp_path):
    for i in range(10):
        (tmp_path / f"f{i}.txt").write_text("x", encoding="utf-8")
    listing = directory_listing(tmp_path, ".", limit=3)
    assert listing["truncated"] is True
    assert listing["entry_count"] == 3


def test_directory_listing_label_mentions_metadata_only(tmp_path):
    listing = directory_listing(tmp_path, ".", limit=10)
    assert "metadata only" in listing["label"]
    assert "no file contents" in listing["label"]


# --- process_summary: never surfaces command-line arguments ------------------


def test_process_summary_without_psutil_is_honest_about_the_limitation(monkeypatch):
    # In this environment psutil is not installed, so this exercises the
    # real fallback path; force it regardless of environment.
    monkeypatch.setitem(sys.modules, "psutil", None)
    summary = process_summary()
    assert summary["available"] is False
    assert "cmdline" not in str(summary)
    assert summary["processes"][0]["pid"] == __import__("os").getpid()


def test_process_summary_never_requests_or_exposes_cmdline_when_psutil_present(monkeypatch):
    """Simulate psutil being installed and returning a process whose command
    line contains a secret; prove Alfred never requests or surfaces it."""

    captured_attrs = {}

    class FakeProcess:
        def __init__(self, info):
            self.info = info

    def fake_process_iter(attrs):
        captured_attrs["attrs"] = attrs
        yield FakeProcess(
            {
                "pid": 4321,
                "name": "victim.exe",
                "username": "local-user",
                # Even if a hostile/buggy psutil build included cmdline, the
                # call below never asked for it, so it is never read here.
                "cmdline": ["victim.exe", "--token=super-secret-value"],
            }
        )

    fake_psutil = types.SimpleNamespace(process_iter=fake_process_iter)
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)

    summary = process_summary()
    assert captured_attrs["attrs"] == ["pid", "name", "username"]
    assert "super-secret-value" not in str(summary)
    assert "cmdline" not in summary["processes"][0]
    assert summary["label"].endswith("process command-line arguments are never collected")


def test_process_summary_redacts_secret_shaped_process_name(monkeypatch):
    def fake_process_iter(attrs):
        yield types.SimpleNamespace(info={"pid": 1, "name": "token=abcd1234efgh", "username": "u"})

    fake_psutil = types.SimpleNamespace(process_iter=fake_process_iter)
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    summary = process_summary()
    assert "abcd1234efgh" not in str(summary)


def test_own_process_summary_never_includes_username_secrets():
    summary = system_inspect._own_process_summary()
    assert summary["processes"][0]["username"] == "current-user"
