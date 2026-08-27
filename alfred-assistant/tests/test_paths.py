"""Path confinement: traversal, absolute, UNC, device, and symlink escapes."""

from __future__ import annotations

import os

import pytest
from alfred import paths
from alfred.paths import PathError, canonical_root, relative_display, resolve_within, single_segment

# --- absolute / drive-relative / UNC / device -------------------------------


@pytest.mark.parametrize(
    "candidate",
    [
        r"C:\Windows\System32",
        "/etc/passwd",
        r"C:/Windows/System32",
        "C:foo",  # drive-relative, no root slash
    ],
)
def test_resolve_within_rejects_absolute_and_drive_relative_paths(tmp_path, candidate):
    with pytest.raises(PathError):
        resolve_within(tmp_path, candidate)


@pytest.mark.parametrize(
    "candidate",
    [
        r"\\server\share\file.txt",
        "//server/share/file.txt",
        r"\\?\C:\Windows\System32",
        r"\\.\PhysicalDrive0",
    ],
)
def test_resolve_within_rejects_unc_and_device_paths(tmp_path, candidate):
    with pytest.raises(PathError):
        resolve_within(tmp_path, candidate)


@pytest.mark.parametrize(
    "candidate",
    [
        "..",
        "../outside",
        "a/../../outside",
        "sub/../../../etc",
        r"a\..\..\b",
    ],
)
def test_resolve_within_rejects_traversal(tmp_path, candidate):
    with pytest.raises(PathError, match="traversal"):
        resolve_within(tmp_path, candidate)


def test_resolve_within_rejects_null_byte(tmp_path):
    with pytest.raises(PathError, match="null byte"):
        resolve_within(tmp_path, "foo\x00bar")


@pytest.mark.parametrize("candidate", [None, "", "   "])
def test_resolve_within_rejects_empty_paths(tmp_path, candidate):
    with pytest.raises(PathError, match="required"):
        resolve_within(tmp_path, candidate)


def test_resolve_within_accepts_and_confines_normal_relative_path(tmp_path):
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    resolved = resolve_within(tmp_path, "a/b")
    assert resolved == canonical_root(nested)


def test_resolve_within_accepts_windows_style_separators(tmp_path):
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    resolved = resolve_within(tmp_path, "a\\b")
    assert resolved == canonical_root(nested)


def test_resolve_within_dot_means_root_itself(tmp_path):
    resolved = resolve_within(tmp_path, ".")
    assert resolved == canonical_root(tmp_path)


# --- symlink / reparse escape (simulated; no elevated privileges required) --


def test_resolve_within_blocks_realpath_escape(tmp_path, monkeypatch):
    """Simulate a symlink/reparse point that resolves outside the root.

    This does not require OS-level symlink privileges (which may be denied on
    a locked-down Windows CI runner): it monkeypatches ``os.path.realpath`` so
    that one specific candidate resolves outside the approved root, exactly as
    a real symlink pointing outside the root would, and proves the defence in
    :func:`alfred.paths.resolve_within` actually rejects it.
    """

    outside = tmp_path.parent / "outside-target"
    outside.mkdir(exist_ok=True)
    escape_name = "escape-link"
    real_realpath = os.path.realpath

    def fake_realpath(path, *args, **kwargs):
        text = str(path)
        if os.path.basename(text.rstrip("\\/")) == escape_name:
            return str(outside / "leaked.txt")
        return real_realpath(path, *args, **kwargs)

    monkeypatch.setattr(paths.os.path, "realpath", fake_realpath)
    with pytest.raises(PathError, match="escapes the approved root"):
        resolve_within(tmp_path, escape_name)


@pytest.mark.skipif(
    not hasattr(os, "symlink"), reason="platform has no symlink support"
)
def test_resolve_within_blocks_real_symlink_escape_when_privileges_allow(tmp_path):
    outside = tmp_path.parent / "real-outside-target"
    outside.mkdir(exist_ok=True)
    target_file = outside / "secret.txt"
    target_file.write_text("do not read me via the approved root")
    link = tmp_path / "escape"
    try:
        os.symlink(target_file, link)
    except (OSError, NotImplementedError):
        pytest.skip("creating symlinks is not permitted in this environment")
    with pytest.raises(PathError, match="escapes the approved root"):
        resolve_within(tmp_path, "escape")


# --- single_segment ----------------------------------------------------------


@pytest.mark.parametrize("name", ["", "   ", ".", "..", "a/b", "a\\b", 'bad"name', "bad|name", "bad*name"])
def test_single_segment_rejects_invalid_names(name):
    with pytest.raises(PathError):
        single_segment(name)


def test_single_segment_accepts_simple_name():
    assert single_segment("My Folder") == "My Folder"


def test_single_segment_rejects_null_byte():
    with pytest.raises(PathError, match="null byte"):
        single_segment("foo\x00")


def test_single_segment_rejects_unc_looking_name():
    with pytest.raises(PathError):
        single_segment(r"\\server\share")


# --- relative_display never leaks absolute paths -----------------------------


def test_relative_display_is_relative_and_posix_style(tmp_path):
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    display = relative_display(tmp_path, nested)
    assert display == "a/b"
    assert not display.startswith(str(tmp_path))


def test_relative_display_root_itself_is_dot(tmp_path):
    assert relative_display(tmp_path, canonical_root(tmp_path)) == "."


def test_relative_display_falls_back_to_name_outside_root(tmp_path):
    outside = tmp_path.parent / "elsewhere"
    outside.mkdir(exist_ok=True)
    display = relative_display(tmp_path, outside)
    assert display == "elsewhere"
    assert str(tmp_path.parent) not in display
