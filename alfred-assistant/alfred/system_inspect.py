"""Read-only system inspection with secret redaction.

Every function here is read-only and clearly labelled as such. Text fields
that could carry secret-shaped values (process names, usernames) are passed
through :func:`redact_secrets`. Process *command-line arguments* are never
collected or surfaced at all -- a stronger guarantee than "collect then
redact", since only ``pid``/``name``/``username`` are ever requested from the
process API. Directory listings expose metadata only (never file contents).
Process enumeration uses a safe library API when available and otherwise
reports honestly that it is limited.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from .paths import PathError, relative_display, resolve_within

READ_ONLY_LABEL = "read-only summary; no changes are made"

# Redact common secret shapes: key=value pairs and long high-entropy blobs.
_SECRET_KEYS = re.compile(
    r"(?i)\b(password|passwd|pwd|token|secret|api[_-]?key|apikey|access[_-]?key"
    r"|auth|authorization|bearer|session|cookie|credential|private[_-]?key)\b"
    r"\s*[=:]\s*\S+"
)
_LONG_BLOB = re.compile(r"\b[A-Za-z0-9+/_\-]{40,}\b")


def redact_secrets(text: str) -> str:
    """Redact secret-looking assignments and long high-entropy tokens."""

    if not text:
        return text
    redacted = _SECRET_KEYS.sub(lambda match: _redact_keyval(match.group(0)), text)
    redacted = _LONG_BLOB.sub("[redacted]", redacted)
    return redacted


def _redact_keyval(fragment: str) -> str:
    key = re.split(r"[=:]", fragment, maxsplit=1)[0]
    separator = "=" if "=" in fragment else ":"
    return f"{key}{separator}[redacted]"


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def system_summary() -> dict[str, object]:
    load_average: list[float] | None = None
    if hasattr(os, "getloadavg"):
        try:
            load_average = list(os.getloadavg())
        except OSError:
            load_average = None
    summary: dict[str, object] = {
        "label": READ_ONLY_LABEL,
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "python_version": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "load_average": load_average,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return summary


def disk_summary(roots: list[Path]) -> dict[str, object]:
    volumes: list[dict[str, object]] = []
    for root in roots:
        try:
            usage = shutil.disk_usage(root)
        except OSError as exc:
            volumes.append({"root": Path(root).name, "error": str(exc)})
            continue
        volumes.append(
            {
                "root": Path(root).name,
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
                "used_percent": round(usage.used / usage.total * 100, 2) if usage.total else None,
            }
        )
    return {"label": READ_ONLY_LABEL, "volumes": volumes}


def directory_listing(root: Path, subpath: str, *, limit: int) -> dict[str, object]:
    """List directory entries (metadata only) confined to an approved root."""

    target = resolve_within(root, subpath) if subpath not in {"", "."} else Path(
        os.path.realpath(str(root))
    )
    if not target.exists():
        raise PathError("directory does not exist")
    if not target.is_dir():
        raise PathError("path is not a directory")

    entries: list[dict[str, object]] = []
    truncated = False
    with os.scandir(target) as scanner:
        for index, entry in enumerate(sorted(scanner, key=lambda item: item.name.lower())):
            if index >= limit:
                truncated = True
                break
            try:
                stat = entry.stat(follow_symlinks=False)
                size: int | None = stat.st_size
                modified: str | None = _iso(stat.st_mtime)
            except OSError:
                size = None
                modified = None
            entries.append(
                {
                    "name": entry.name,
                    "kind": "directory" if entry.is_dir(follow_symlinks=False) else "file",
                    "is_symlink": entry.is_symlink(),
                    "size_bytes": size,
                    "modified_at": modified,
                }
            )
    return {
        "label": f"{READ_ONLY_LABEL}; metadata only, no file contents",
        "root": Path(root).name,
        "path": relative_display(root, target),
        "entry_count": len(entries),
        "truncated": truncated,
        "entries": entries,
    }


def process_summary(*, limit: int = 50) -> dict[str, object]:
    """Summarise processes via a safe library API.

    Only ``pid``/``name``/``username`` are ever requested from the process
    API -- command-line arguments are never collected, so there is nothing to
    redact after the fact. The returned ``name``/``username`` text is still
    passed through :func:`redact_secrets` in case either happens to look like
    a secret-bearing key=value pair.
    """

    try:
        import psutil  # type: ignore
    except ImportError:
        return _own_process_summary()

    processes: list[dict[str, object]] = []
    for proc in psutil.process_iter(["pid", "name", "username"]):
        if len(processes) >= limit:
            break
        info = proc.info
        processes.append(
            {
                "pid": info.get("pid"),
                "name": redact_secrets(str(info.get("name") or "unknown")),
                "username": redact_secrets(str(info.get("username") or "unknown")),
            }
        )
    return {
        "label": f"{READ_ONLY_LABEL}; process command-line arguments are never collected",
        "provider": "psutil",
        "available": True,
        "count": len(processes),
        "processes": processes,
    }


def _own_process_summary() -> dict[str, object]:
    return {
        "label": (
            f"{READ_ONLY_LABEL}; full enumeration needs an optional dependency that "
            "is not installed, so only this process is reported"
        ),
        "provider": "stdlib",
        "available": False,
        "count": 1,
        "processes": [
            {
                "pid": os.getpid(),
                "name": redact_secrets(Path(sys.executable).name),
                "username": "current-user",
            }
        ],
    }
