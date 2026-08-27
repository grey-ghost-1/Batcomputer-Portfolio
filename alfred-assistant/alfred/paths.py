"""Filesystem confinement helpers.

Every filesystem action is confined to an approved root. These helpers reject
absolute, UNC, and device paths, resolve real paths to defeat ``..`` traversal
and symlink/reparse escapes, and never read file contents.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath, PureWindowsPath


class PathError(ValueError):
    """Raised when a candidate path is unsafe or escapes its approved root."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def is_unc_or_device(raw: str) -> bool:
    """Detect UNC (``\\\\server\\share``) and device (``\\\\?\\``) prefixes."""

    if not raw:
        return False
    normalised = raw.replace("/", "\\")
    if normalised.startswith("\\\\"):
        return True
    # Drive-relative or device namespaces such as \\.\ and \\?\ are covered above,
    # but also guard PureWindowsPath's view of the anchor.
    anchor = PureWindowsPath(raw).anchor
    return anchor.startswith("\\\\")


def _looks_absolute(raw: str) -> bool:
    return PureWindowsPath(raw).is_absolute() or PurePosixPath(raw).is_absolute()


def _has_drive(raw: str) -> bool:
    return bool(PureWindowsPath(raw).drive)


def canonical_root(root: Path) -> Path:
    return Path(os.path.realpath(str(root)))


def resolve_within(root: Path, candidate: str, *, allow_symlink_leaf: bool = False) -> Path:
    """Resolve ``candidate`` (relative to ``root``) and confine it to ``root``.

    ``allow_symlink_leaf`` is unused today but reserved: even the leaf must resolve
    inside the root. The function never touches file contents.
    """

    if candidate is None:
        raise PathError("path is required")
    text = str(candidate)
    if not text.strip():
        raise PathError("path is required")
    if "\x00" in text:
        raise PathError("path contains a null byte")
    if is_unc_or_device(text):
        raise PathError("UNC and device paths are not permitted")
    if _looks_absolute(text) or _has_drive(text):
        raise PathError("path must be relative to an approved root")

    parts = PureWindowsPath(text).parts
    if any(part == ".." for part in parts):
        raise PathError("parent-directory traversal is not permitted")

    root_real = canonical_root(root)
    combined = Path(os.path.join(str(root_real), *parts)) if parts else root_real
    resolved = Path(os.path.realpath(str(combined)))

    try:
        resolved.relative_to(root_real)
    except ValueError as exc:
        raise PathError("resolved path escapes the approved root") from exc

    # Defend against a symlink/reparse component that resolves back inside the
    # root only by coincidence: verify the lexical join and the real path agree
    # on their relationship to the root.
    lexical = Path(os.path.normpath(str(combined)))
    try:
        lexical.relative_to(root_real)
    except ValueError as exc:
        raise PathError("resolved path escapes the approved root") from exc

    return resolved


def single_segment(name: str) -> str:
    """Validate a single, safe path segment (used for new folder names)."""

    if not name or not name.strip():
        raise PathError("name is required")
    if "\x00" in name:
        raise PathError("name contains a null byte")
    if is_unc_or_device(name):
        raise PathError("name must not be a UNC or device path")
    candidate = name.strip()
    parts = PureWindowsPath(candidate).parts
    if len(parts) != 1 or candidate in {".", ".."}:
        raise PathError("name must be a single path segment")
    if any(sep in candidate for sep in ("/", "\\")):
        raise PathError("name must not contain path separators")
    reserved = set('<>:"|?*')
    if reserved & set(candidate):
        raise PathError("name contains reserved characters")
    return candidate


def relative_display(root: Path, path: Path) -> str:
    """A stable, root-relative display string (never an absolute machine path)."""

    root_real = canonical_root(root)
    try:
        return path.relative_to(root_real).as_posix() or "."
    except ValueError:
        return path.name
