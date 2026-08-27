"""Action executors and desktop launchers.

Each executor produces an exact preview (effects and path diff) without side
effects, and an execute step that re-validates paths, allow-lists, and filesystem
preconditions immediately before acting (TOCTOU defence). Operations are narrow
by construction: create one folder, move/rename one file, organise by explicit
extension rules, open an allow-listed executable (no user args), open an
allow-listed HTTPS URL, or set the clipboard. No shell, no delete, no overwrite,
no recursion.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from ..config import Settings
from ..paths import canonical_root, relative_display, resolve_within, single_segment
from ..schemas import (
    CreateFolderPayload,
    MoveFilePayload,
    OpenAppPayload,
    OpenUrlPayload,
    OrganizeFolderPayload,
    SetClipboardPayload,
)


class ActionError(ValueError):
    """Raised for invalid action payloads or failed safety re-validation."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# --- Desktop launchers (mockable) ----------------------------------------


class DesktopLauncher:
    """Real desktop launcher. Tests inject a recording double instead."""

    def open_executable(self, path: Path) -> None:
        starter = getattr(os, "startfile", None)
        if starter is not None:
            starter(str(path))
            return
        import subprocess

        subprocess.Popen([str(path)], close_fds=True)

    def open_url(self, url: str) -> None:
        import webbrowser

        webbrowser.open(url, new=2)

    def set_clipboard(self, text: str) -> None:
        raise ActionError("clipboard integration is not enabled on this host")


# --- Path helpers ---------------------------------------------------------


def select_root(settings: Settings, index: int) -> Path:
    if index < 0 or index >= len(settings.approved_roots):
        raise ActionError("approved root index is out of range")
    return settings.approved_roots[index]


def _join(parent: str, name: str) -> str:
    parent = (parent or ".").strip()
    if parent in {"", "."}:
        return name
    return f"{parent}/{name}"


def _normalise_extension(extension: str) -> str:
    ext = extension.strip().lower()
    if not ext:
        raise ActionError("extension is required")
    if not ext.startswith("."):
        ext = "." + ext
    if len(ext) < 2 or "/" in ext or "\\" in ext or ext.count(".") != 1:
        raise ActionError(f"invalid extension: {extension!r}")
    return ext


# --- create_folder --------------------------------------------------------


def preview_create_folder(settings: Settings, payload: CreateFolderPayload) -> dict:
    root = select_root(settings, payload.root)
    name = single_segment(payload.name)
    target = resolve_within(root, _join(payload.parent, name))
    parent = resolve_within(root, payload.parent) if payload.parent.strip() not in {"", "."} else \
        canonical_root(root)
    warnings = []
    if not parent.exists():
        warnings.append("parent directory does not exist yet; it must exist at execution time")
    if target.exists():
        warnings.append("a file or folder with this name already exists; execution will be refused")
    return {
        "summary": f"Create a new folder '{name}' in '{relative_display(root, parent)}'.",
        "effects": ["create exactly one directory"],
        "path_diff": [
            {"kind": "create-directory", "from": None, "to": relative_display(root, target)}
        ],
        "warnings": warnings,
    }


def execute_create_folder(settings: Settings, payload: CreateFolderPayload, launcher: DesktopLauncher) -> dict:
    root = select_root(settings, payload.root)
    name = single_segment(payload.name)
    parent = resolve_within(root, payload.parent) if payload.parent.strip() not in {"", "."} else \
        canonical_root(root)
    target = resolve_within(root, _join(payload.parent, name))
    if not parent.is_dir():
        raise ActionError("parent directory does not exist")
    if target.exists():
        raise ActionError("target already exists; refusing to overwrite")
    os.mkdir(target)
    return {
        "created_directory": relative_display(root, target),
        "root": root.name,
    }


# --- move_file ------------------------------------------------------------


def preview_move_file(settings: Settings, payload: MoveFilePayload) -> dict:
    root = select_root(settings, payload.root)
    source = resolve_within(root, payload.source)
    destination = resolve_within(root, payload.destination)
    warnings = []
    if not source.exists():
        warnings.append("source does not exist yet; it must exist at execution time")
    elif not source.is_file():
        warnings.append("source is not a regular file; only single files may be moved")
    if destination.exists():
        warnings.append("destination already exists; execution will be refused")
    return {
        "summary": (
            f"Move '{relative_display(root, source)}' to "
            f"'{relative_display(root, destination)}'."
        ),
        "effects": ["move or rename exactly one file"],
        "path_diff": [
            {
                "kind": "move",
                "from": relative_display(root, source),
                "to": relative_display(root, destination),
            }
        ],
        "warnings": warnings,
    }


def execute_move_file(settings: Settings, payload: MoveFilePayload, launcher: DesktopLauncher) -> dict:
    root = select_root(settings, payload.root)
    source = resolve_within(root, payload.source)
    destination = resolve_within(root, payload.destination)
    if not source.exists() or not source.is_file():
        raise ActionError("source is not an existing regular file")
    if destination.exists():
        raise ActionError("destination already exists; refusing to overwrite")
    if not destination.parent.is_dir():
        raise ActionError("destination directory does not exist")
    os.rename(source, destination)
    return {
        "moved_from": relative_display(root, source),
        "moved_to": relative_display(root, destination),
        "root": root.name,
    }


# --- organize_folder ------------------------------------------------------


def _build_manifest(
    settings: Settings, payload: OrganizeFolderPayload
) -> tuple[Path, Path, list[dict], list[dict], int]:
    root = select_root(settings, payload.root)
    folder = resolve_within(root, payload.folder) if payload.folder.strip() not in {"", "."} else \
        canonical_root(root)
    if not folder.is_dir():
        raise ActionError("folder to organise does not exist")

    rules: dict[str, str] = {}
    for rule in payload.rules:
        rules[_normalise_extension(rule.extension)] = single_segment(rule.subfolder)

    moves: list[dict] = []
    conflicts: list[dict] = []
    seen_targets: set[str] = set()
    total_bytes = 0
    with os.scandir(folder) as scanner:
        entries = sorted(scanner, key=lambda item: item.name.lower())
    for entry in entries:
        if not entry.is_file(follow_symlinks=False):
            continue
        suffix = Path(entry.name).suffix.lower()
        subfolder = rules.get(suffix)
        if subfolder is None:
            continue
        source = resolve_within(root, _join(payload.folder, entry.name))
        dest_rel = _join(_join(payload.folder, subfolder), entry.name)
        destination = resolve_within(root, dest_rel)
        dest_display = relative_display(root, destination)
        if destination.exists() or dest_display in seen_targets:
            conflicts.append({"name": entry.name, "reason": "destination exists", "to": dest_display})
            continue
        try:
            size = entry.stat(follow_symlinks=False).st_size
        except OSError:
            size = 0
        total_bytes += size
        seen_targets.add(dest_display)
        moves.append(
            {
                "kind": "move",
                "from": relative_display(root, source),
                "to": dest_display,
                "subfolder": subfolder,
            }
        )
        if len(moves) > settings.max_organize_files:
            raise ActionError(
                f"organise plan exceeds the {settings.max_organize_files}-file limit"
            )
        if total_bytes > settings.max_organize_total_bytes:
            raise ActionError("organise plan exceeds the total-size limit")
    return root, folder, moves, conflicts, total_bytes


def preview_organize_folder(settings: Settings, payload: OrganizeFolderPayload) -> dict:
    root, folder, moves, conflicts, total_bytes = _build_manifest(settings, payload)
    return {
        "summary": (
            f"Organise '{relative_display(root, folder)}': {len(moves)} file(s) into "
            f"subfolders by extension (dry run)."
        ),
        "effects": [
            f"create up to {len({m['subfolder'] for m in moves})} subfolder(s)",
            f"move {len(moves)} file(s)",
        ],
        "path_diff": moves,
        "manifest": moves,
        "conflicts": conflicts,
        "planned_bytes": total_bytes,
        "warnings": (
            [f"{len(conflicts)} file(s) skipped due to existing destinations"] if conflicts else []
        ),
    }


def execute_organize_folder(settings: Settings, payload: OrganizeFolderPayload, launcher: DesktopLauncher) -> dict:
    root, _folder, moves, conflicts, _total = _build_manifest(settings, payload)
    moved: list[dict] = []
    skipped: list[dict] = list(conflicts)
    for move in moves:
        source = resolve_within(root, move["from"])
        destination = resolve_within(root, move["to"])
        if destination.exists():
            skipped.append({"name": source.name, "reason": "destination appeared", "to": move["to"]})
            continue
        if not destination.parent.exists():
            os.mkdir(destination.parent)
        if not source.is_file():
            skipped.append({"name": source.name, "reason": "source vanished", "to": move["to"]})
            continue
        os.rename(source, destination)
        moved.append({"from": move["from"], "to": move["to"]})
    return {"root": root.name, "moved": moved, "skipped": skipped, "moved_count": len(moved)}


# --- open_app -------------------------------------------------------------


def _match_executable(settings: Settings, candidate: str) -> Path:
    candidate = candidate.strip()
    if not candidate:
        raise ActionError("executable is required")
    for allowed in settings.allowed_executables:
        if candidate == str(allowed) or candidate == allowed.name:
            return allowed
    raise ActionError("executable is not on the allow-list")


def preview_open_app(settings: Settings, payload: OpenAppPayload) -> dict:
    matched = _match_executable(settings, payload.executable)
    return {
        "summary": f"Open the allow-listed application '{matched.name}' with no arguments.",
        "effects": ["launch one allow-listed executable (no user arguments)"],
        "path_diff": [],
        "target": matched.name,
        "warnings": [] if matched.exists() else ["executable not found at execution path"],
    }


def execute_open_app(settings: Settings, payload: OpenAppPayload, launcher: DesktopLauncher) -> dict:
    matched = _match_executable(settings, payload.executable)
    if not matched.exists():
        raise ActionError("allow-listed executable does not exist at execution time")
    launcher.open_executable(matched)
    return {"launched": matched.name}


# --- open_url -------------------------------------------------------------


def _validate_url(settings: Settings, url: str) -> str:
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme.lower() != "https":
        raise ActionError("only https URLs may be opened")
    if parts.username or parts.password:
        raise ActionError("URLs must not contain embedded credentials")
    try:
        port = parts.port
    except ValueError as exc:
        raise ActionError("URL port is invalid") from exc
    if port not in (None, 443):
        raise ActionError("only the standard https port is permitted")
    host = (parts.hostname or "").lower()
    if not host:
        raise ActionError("URL host is missing")
    if host not in settings.allowed_url_hosts:
        raise ActionError("URL host is not on the allow-list")
    return url


def preview_open_url(settings: Settings, payload: OpenUrlPayload) -> dict:
    url = _validate_url(settings, payload.url)
    host = urlsplit(url).hostname
    return {
        "summary": f"Open the allow-listed HTTPS address at '{host}' in the browser.",
        "effects": ["open one allow-listed HTTPS URL in the default browser"],
        "path_diff": [],
        "target": url,
        "warnings": [],
    }


def execute_open_url(settings: Settings, payload: OpenUrlPayload, launcher: DesktopLauncher) -> dict:
    url = _validate_url(settings, payload.url)
    launcher.open_url(url)
    return {"opened": url}


# --- set_clipboard --------------------------------------------------------


def preview_set_clipboard(settings: Settings, payload: SetClipboardPayload) -> dict:
    if not settings.clipboard_enabled:
        raise ActionError("clipboard actions are disabled in this configuration")
    return {
        "summary": f"Place {len(payload.text)} character(s) of text on the clipboard.",
        "effects": ["replace the clipboard contents"],
        "path_diff": [],
        "character_count": len(payload.text),
        "warnings": [],
    }


def execute_set_clipboard(settings: Settings, payload: SetClipboardPayload, launcher: DesktopLauncher) -> dict:
    if not settings.clipboard_enabled:
        raise ActionError("clipboard actions are disabled in this configuration")
    launcher.set_clipboard(payload.text)
    return {"character_count": len(payload.text)}
