import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .database import Base, engine, get_db
from .models import (
    AlfredIntent,
    Asset,
    AuditEvent,
    Category,
    Role,
    User,
    WorkItem,
    Workspace,
    WorkStatus,
)
from .schemas import (
    AlfredIntentCreate,
    AlfredIntentRead,
    AssetCreate,
    AssetRead,
    AssetUpdate,
    AuditRead,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    TransitionRequest,
    UserCreate,
    UserRead,
    WorkItemCreate,
    WorkItemRead,
    WorkItemUpdate,
)
from .security import create_token, current_user, hash_password, require_roles, verify_password

logger = logging.getLogger("batcomputer.platform")
logging.basicConfig(level=logging.INFO, format="%(message)s")
UI_DIR = Path(__file__).resolve().parents[1] / "ui"
TRANSITIONS = {
    WorkStatus.PLANNED: {WorkStatus.IN_PROGRESS},
    WorkStatus.IN_PROGRESS: {WorkStatus.BLOCKED, WorkStatus.COMPLETED},
    WorkStatus.BLOCKED: {WorkStatus.IN_PROGRESS},
    WorkStatus.COMPLETED: set(),
}


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    if get_settings().environment in {"development", "test"}:
        Base.metadata.create_all(engine)
    yield


app = FastAPI(
    title="Batcomputer Operations Platform",
    version="1.0.0",
    description="Tenant-isolated operational assets, workflows, audit evidence, and approval-only Alfred intents.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_logging(request: Request, call_next):
    supplied_id = request.headers.get("x-correlation-id", "")
    correlation_id = supplied_id if 0 < len(supplied_id) <= 80 else str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["x-correlation-id"] = correlation_id
    logger.info(
        json.dumps(
            {
                "event": "http_request",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "correlation_id": correlation_id,
            }
        )
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed.",
                "details": jsonable_encoder(exc.errors()),
                "correlation_id": getattr(request.state, "correlation_id", None),
            }
        },
    )


@app.exception_handler(HTTPException)
async def api_error(request: Request, exc: HTTPException):
    response = await http_exception_handler(request, exc)
    return JSONResponse(
        status_code=response.status_code,
        headers=response.headers,
        content={
            "error": {
                "code": f"http_{response.status_code}",
                "message": exc.detail,
                "correlation_id": getattr(request.state, "correlation_id", None),
            }
        },
    )


def audit(
    db: Session,
    request: Request,
    user: User,
    action: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditEvent(
            workspace_id=user.workspace_id,
            actor_user_id=user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            correlation_id=request.state.correlation_id,
            payload=payload or {},
        )
    )


def commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="record conflicts with existing data") from exc


def flush(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="record conflicts with existing data") from exc


def tenant_record(db: Session, model: Any, record_id: str, workspace_id: str):
    record = db.scalar(select(model).where(model.id == record_id, model.workspace_id == workspace_id))
    if record is None:
        raise HTTPException(status_code=404, detail="record not found")
    return record


@app.get("/", include_in_schema=False)
def operator_ui():
    return FileResponse(UI_DIR / "index.html")


@app.get("/operator.js", include_in_schema=False)
def operator_js():
    return FileResponse(UI_DIR / "operator.js", media_type="application/javascript")


@app.get("/health/live", tags=["health"])
def live():
    return {"status": "ok", "service": "batcomputer-platform"}


@app.get("/health/ready", tags=["health"])
def ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "reachable"}


@app.post("/api/v1/auth/register", response_model=TokenResponse, status_code=201, tags=["auth"])
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    workspace = Workspace(name=payload.workspace_name.strip())
    user = User(
        workspace=workspace,
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
        role=Role.ADMIN,
    )
    db.add_all([workspace, user])
    commit(db)
    token, expires = create_token(user, get_settings())
    return TokenResponse(access_token=token, expires_in=expires)


@app.post("/api/v1/auth/login", response_model=TokenResponse, tags=["auth"])
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(
        select(User)
        .join(Workspace)
        .where(
            Workspace.name == payload.workspace_name.strip(),
            User.email == str(payload.email).lower(),
        )
    )
    if user is None or not user.active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    token, expires = create_token(user, get_settings())
    return TokenResponse(access_token=token, expires_in=expires)


@app.post("/api/v1/users", response_model=UserRead, status_code=201, tags=["users"])
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(Role.ADMIN)),
):
    user = User(
        workspace_id=actor.workspace_id,
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    flush(db)
    audit(db, request, actor, "user.created", "user", user.id, {"role": user.role.value})
    commit(db)
    return user


@app.get("/api/v1/me", response_model=UserRead, tags=["users"])
def me(user: User = Depends(current_user)):
    return user


@app.post("/api/v1/assets", response_model=AssetRead, status_code=201, tags=["assets"])
def create_asset(
    payload: AssetCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.ADMIN, Role.OPERATOR)),
):
    asset = Asset(workspace_id=user.workspace_id, **payload.model_dump())
    db.add(asset)
    flush(db)
    audit(db, request, user, "asset.created", "asset", asset.id, {"category": asset.category.value})
    commit(db)
    return asset


@app.get("/api/v1/assets", tags=["assets"])
def list_assets(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    category: Category | None = None,
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    filters = [Asset.workspace_id == user.workspace_id]
    if category:
        filters.append(Asset.category == category)
    if status_filter:
        filters.append(Asset.status == status_filter)
    total = db.scalar(select(func.count()).select_from(Asset).where(*filters)) or 0
    items = db.scalars(
        select(Asset).where(*filters).order_by(Asset.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "items": [AssetRead.model_validate(item) for item in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/v1/assets/{asset_id}", response_model=AssetRead, tags=["assets"])
def get_asset(asset_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return tenant_record(db, Asset, asset_id, user.workspace_id)


@app.patch("/api/v1/assets/{asset_id}", response_model=AssetRead, tags=["assets"])
def update_asset(
    asset_id: str,
    payload: AssetUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.ADMIN, Role.OPERATOR)),
):
    asset = tenant_record(db, Asset, asset_id, user.workspace_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(asset, field, value)
    audit(db, request, user, "asset.updated", "asset", asset.id)
    commit(db)
    return asset


@app.delete("/api/v1/assets/{asset_id}", status_code=204, tags=["assets"])
def delete_asset(
    asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.ADMIN)),
):
    asset = tenant_record(db, Asset, asset_id, user.workspace_id)
    audit(db, request, user, "asset.deleted", "asset", asset.id, {"name": asset.name})
    db.delete(asset)
    commit(db)


@app.post("/api/v1/work-items", response_model=WorkItemRead, status_code=201, tags=["workflows"])
def create_work_item(
    payload: WorkItemCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.ADMIN, Role.OPERATOR)),
):
    if payload.asset_id:
        tenant_record(db, Asset, payload.asset_id, user.workspace_id)
    item = WorkItem(workspace_id=user.workspace_id, **payload.model_dump())
    db.add(item)
    flush(db)
    audit(db, request, user, "work_item.created", "work_item", item.id)
    commit(db)
    return item


@app.get("/api/v1/work-items", tags=["workflows"])
def list_work_items(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    category: Category | None = None,
    status_filter: WorkStatus | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    filters = [WorkItem.workspace_id == user.workspace_id]
    if category:
        filters.append(WorkItem.category == category)
    if status_filter:
        filters.append(WorkItem.status == status_filter)
    total = db.scalar(select(func.count()).select_from(WorkItem).where(*filters)) or 0
    items = db.scalars(
        select(WorkItem)
        .where(*filters)
        .order_by(WorkItem.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "items": [WorkItemRead.model_validate(item) for item in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/v1/work-items/{item_id}", response_model=WorkItemRead, tags=["workflows"])
def get_work_item(
    item_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    return tenant_record(db, WorkItem, item_id, user.workspace_id)


@app.patch("/api/v1/work-items/{item_id}", response_model=WorkItemRead, tags=["workflows"])
def update_work_item(
    item_id: str,
    payload: WorkItemUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.ADMIN, Role.OPERATOR)),
):
    item = tenant_record(db, WorkItem, item_id, user.workspace_id)
    values = payload.model_dump(exclude_unset=True)
    if values.get("asset_id"):
        tenant_record(db, Asset, values["asset_id"], user.workspace_id)
    for field, value in values.items():
        setattr(item, field, value)
    audit(db, request, user, "work_item.updated", "work_item", item.id)
    commit(db)
    return item


@app.delete("/api/v1/work-items/{item_id}", status_code=204, tags=["workflows"])
def delete_work_item(
    item_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.ADMIN)),
):
    item = tenant_record(db, WorkItem, item_id, user.workspace_id)
    audit(db, request, user, "work_item.deleted", "work_item", item.id, {"title": item.title})
    db.delete(item)
    commit(db)


@app.post(
    "/api/v1/work-items/{item_id}/transitions", response_model=WorkItemRead, tags=["workflows"]
)
def transition_work_item(
    item_id: str,
    payload: TransitionRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.ADMIN, Role.OPERATOR)),
):
    item = tenant_record(db, WorkItem, item_id, user.workspace_id)
    if payload.status not in TRANSITIONS[item.status]:
        raise HTTPException(
            status_code=409, detail=f"cannot transition from {item.status.value} to {payload.status.value}"
        )
    previous = item.status
    item.status = payload.status
    audit(
        db,
        request,
        user,
        "work_item.transitioned",
        "work_item",
        item.id,
        {"from": previous.value, "to": item.status.value},
    )
    commit(db)
    return item


@app.get("/api/v1/audit-events", tags=["audit"])
def list_audit_events(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    action: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    filters = [AuditEvent.workspace_id == user.workspace_id]
    if action:
        filters.append(AuditEvent.action == action)
    total = db.scalar(select(func.count()).select_from(AuditEvent).where(*filters)) or 0
    items = db.scalars(
        select(AuditEvent)
        .where(*filters)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "items": [AuditRead.model_validate(item) for item in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/v1/alfred/status", tags=["alfred"])
def alfred_status(
    settings: Settings = Depends(get_settings), _user: User = Depends(current_user)
):
    return {
        "status": "configured" if settings.alfred_provider_url else "unavailable",
        "provider_configured": bool(settings.alfred_provider_url),
        "generates_content": False,
        "executes_actions": False,
        "intent_mode": "approval_pending_only",
    }


@app.post(
    "/api/v1/alfred/intents", response_model=AlfredIntentRead, status_code=202, tags=["alfred"]
)
def create_alfred_intent(
    payload: AlfredIntentCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.ADMIN, Role.OPERATOR)),
):
    intent = AlfredIntent(
        workspace_id=user.workspace_id,
        actor_user_id=user.id,
        prompt=payload.prompt,
        status="approval_pending",
        executed=False,
    )
    db.add(intent)
    flush(db)
    audit(db, request, user, "alfred.intent_created", "alfred_intent", intent.id)
    commit(db)
    return intent
