"""Typed request/response models for the Alfred Assistant API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ActionType = Literal[
    "create_folder",
    "move_file",
    "organize_folder",
    "open_app",
    "open_url",
    "set_clipboard",
]


# --- Chat / research ------------------------------------------------------


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    mode: Literal["auto", "deterministic", "model"] = "auto"
    use_web: bool = False
    research_depth: Literal["concise", "deep"] = "concise"
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


class ResearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    depth: Literal["concise", "deep"] = "concise"


# --- Action payloads ------------------------------------------------------


class CreateFolderPayload(BaseModel):
    root: int = Field(default=0, ge=0)
    parent: str = Field(default=".", max_length=400)
    name: str = Field(min_length=1, max_length=120)


class MoveFilePayload(BaseModel):
    root: int = Field(default=0, ge=0)
    source: str = Field(min_length=1, max_length=400)
    destination: str = Field(min_length=1, max_length=400)


class OrganizeRule(BaseModel):
    extension: str = Field(min_length=1, max_length=20)
    subfolder: str = Field(min_length=1, max_length=120)


class OrganizeFolderPayload(BaseModel):
    root: int = Field(default=0, ge=0)
    folder: str = Field(default=".", max_length=400)
    rules: list[OrganizeRule] = Field(min_length=1, max_length=20)


class OpenAppPayload(BaseModel):
    executable: str = Field(min_length=1, max_length=1000)


class OpenUrlPayload(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


class SetClipboardPayload(BaseModel):
    text: str = Field(min_length=1, max_length=4096)


# --- Action lifecycle -----------------------------------------------------


class ProposeRequest(BaseModel):
    action_type: ActionType
    payload: dict


class ApproveRequest(BaseModel):
    payload_hash: str = Field(min_length=16, max_length=128)
