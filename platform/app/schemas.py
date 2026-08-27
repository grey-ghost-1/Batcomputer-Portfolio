from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import Category, Role, WorkStatus


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


class RegisterRequest(APIModel):
    workspace_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(APIModel):
    workspace_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(APIModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserCreate(APIModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    role: Role = Role.VIEWER


class UserRead(APIModel):
    id: str
    workspace_id: str
    email: EmailStr
    role: Role
    active: bool


class AssetCreate(APIModel):
    category: Category
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=4000)
    status: str = Field(default="active", min_length=2, max_length=40)


class AssetUpdate(APIModel):
    category: Category | None = None
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    status: str | None = Field(default=None, min_length=2, max_length=40)


class AssetRead(AssetCreate):
    id: str
    workspace_id: str
    created_at: datetime
    updated_at: datetime


class WorkItemCreate(APIModel):
    asset_id: str | None = None
    category: Category
    title: str = Field(min_length=2, max_length=180)
    details: str = Field(default="", max_length=8000)


class WorkItemUpdate(APIModel):
    asset_id: str | None = None
    category: Category | None = None
    title: str | None = Field(default=None, min_length=2, max_length=180)
    details: str | None = Field(default=None, max_length=8000)


class TransitionRequest(APIModel):
    status: WorkStatus


class WorkItemRead(WorkItemCreate):
    id: str
    workspace_id: str
    status: WorkStatus
    created_at: datetime
    updated_at: datetime


class AuditRead(APIModel):
    id: str
    actor_user_id: str | None
    action: str
    entity_type: str
    entity_id: str
    correlation_id: str
    payload: dict[str, object]
    created_at: datetime


class AlfredIntentCreate(APIModel):
    prompt: str = Field(min_length=3, max_length=2000)


class AlfredIntentRead(APIModel):
    id: str
    prompt: str
    status: str
    executed: bool
    created_at: datetime


class Page(APIModel):
    items: list[object]
    total: int
    limit: int
    offset: int
