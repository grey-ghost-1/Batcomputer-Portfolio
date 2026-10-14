"""Action registry: specs, payload validation, canonical hashing, and dispatch."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from ..config import Settings
from ..schemas import (
    CreateFolderPayload,
    MoveFilePayload,
    OpenAppPayload,
    OpenUrlPayload,
    OrganizeFolderPayload,
    SetClipboardPayload,
)
from . import executors
from .executors import ActionError, DesktopLauncher


@dataclass
class ActionSpec:
    action_type: str
    model: type[BaseModel]
    desktop: bool
    requires_clipboard: bool
    # Each concrete executor function below takes a *specific* Pydantic
    # payload subtype (e.g. CreateFolderPayload), not the general BaseModel,
    # so these fields intentionally use an unchecked-parameter Callable
    # (mypy parameter types are contravariant, so a narrower-payload function
    # is not assignable to `Callable[[Settings, BaseModel], dict]`). Every
    # concrete function is still fully annotated on its own definition.
    build_preview: Callable[..., dict]
    execute: Callable[..., dict]
    description: str


SPECS: dict[str, ActionSpec] = {
    "create_folder": ActionSpec(
        action_type="create_folder",
        model=CreateFolderPayload,
        desktop=True,
        requires_clipboard=False,
        build_preview=executors.preview_create_folder,
        execute=executors.execute_create_folder,
        description="Create exactly one folder under an approved root.",
    ),
    "move_file": ActionSpec(
        action_type="move_file",
        model=MoveFilePayload,
        desktop=True,
        requires_clipboard=False,
        build_preview=executors.preview_move_file,
        execute=executors.execute_move_file,
        description="Move or rename one file within an approved root.",
    ),
    "organize_folder": ActionSpec(
        action_type="organize_folder",
        model=OrganizeFolderPayload,
        desktop=True,
        requires_clipboard=False,
        build_preview=executors.preview_organize_folder,
        execute=executors.execute_organize_folder,
        description="Organise a folder by explicit extension rules (dry-run manifest first).",
    ),
    "open_app": ActionSpec(
        action_type="open_app",
        model=OpenAppPayload,
        desktop=True,
        requires_clipboard=False,
        build_preview=executors.preview_open_app,
        execute=executors.execute_open_app,
        description="Open one allow-listed executable with no user arguments.",
    ),
    "open_url": ActionSpec(
        action_type="open_url",
        model=OpenUrlPayload,
        desktop=True,
        requires_clipboard=False,
        build_preview=executors.preview_open_url,
        execute=executors.execute_open_url,
        description="Open one allow-listed HTTPS URL in the browser.",
    ),
    "set_clipboard": ActionSpec(
        action_type="set_clipboard",
        model=SetClipboardPayload,
        desktop=True,
        requires_clipboard=True,
        build_preview=executors.preview_set_clipboard,
        execute=executors.execute_set_clipboard,
        description="Place approved text on the clipboard (optional; disabled by default).",
    ),
}


def get_spec(action_type: str) -> ActionSpec:
    spec = SPECS.get(action_type)
    if spec is None:
        raise KeyError(action_type)
    return spec


def validate_payload(action_type: str, payload: dict) -> BaseModel:
    spec = get_spec(action_type)
    try:
        return spec.model.model_validate(payload)
    except ValidationError as exc:
        raise ActionError(f"invalid payload: {exc.error_count()} problem(s)") from exc


def canonical_payload(action_type: str, model: BaseModel) -> str:
    data = {"action_type": action_type, "payload": model.model_dump(mode="json")}
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def payload_hash(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_preview(settings: Settings, action_type: str, model: BaseModel) -> dict:
    spec = get_spec(action_type)
    return spec.build_preview(settings, model)


def execute_action(settings: Settings, action_type: str, model: BaseModel, launcher: DesktopLauncher) -> dict:
    spec = get_spec(action_type)
    return spec.execute(settings, model, launcher)


def execution_enabled(settings: Settings, spec: ActionSpec) -> bool:
    if spec.desktop and not settings.desktop_actions_enabled:
        return False
    if spec.requires_clipboard and not settings.clipboard_enabled:
        return False
    return True


def catalog(settings: Settings) -> list[dict]:
    items = []
    for spec in SPECS.values():
        items.append(
            {
                "action_type": spec.action_type,
                "description": spec.description,
                "desktop": spec.desktop,
                "requires_clipboard": spec.requires_clipboard,
                "execution_enabled": execution_enabled(settings, spec),
                "payload_schema": spec.model.model_json_schema(),
            }
        )
    return items
