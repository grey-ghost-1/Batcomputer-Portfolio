"""Typed action subsystem: registry, executors, and proposal lifecycle."""

from __future__ import annotations

from .executors import ActionError, DesktopLauncher
from .proposals import Principal, ProposalError, ProposalStore

__all__ = [
    "ActionError",
    "DesktopLauncher",
    "Principal",
    "ProposalError",
    "ProposalStore",
]
