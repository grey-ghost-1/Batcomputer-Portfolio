"""FastAPI application for the Alfred Assistant service.

Wires configuration, persistence, the knowledge index, the reasoning provider,
the web-research pipeline, and the typed action lifecycle into a local-first,
loopback-only HTTP service with an accessible browser console.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from . import personality
from .actions import DesktopLauncher, Principal, ProposalError, ProposalStore
from .actions import registry as action_registry
from .config import Settings, get_settings
from .db import Database
from .knowledge import build_index
from .net_guard import Resolver
from .orchestrator import Orchestrator
from .paths import PathError
from .providers import ReasoningProvider, build_provider
from .research import ResearchPipeline
from .schemas import ApproveRequest, ChatRequest, ProposeRequest, ResearchRequest
from .security import authenticate
from .system_inspect import directory_listing, disk_summary, process_summary, system_summary

SERVICE_DIR = Path(__file__).resolve().parent.parent
UI_DIR = SERVICE_DIR / "ui"

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'; "
    "frame-ancestors 'none'"
)

ANSWER_MODES = ["deterministic", "model", "website", "web"]


def create_app(
    settings: Settings | None = None,
    *,
    launcher: DesktopLauncher | None = None,
    provider: ReasoningProvider | None = None,
    research: ResearchPipeline | None = None,
    resolver: Resolver | None = None,
    provider_transport: httpx.AsyncBaseTransport | None = None,
    research_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    db = Database(settings.db_path)
    index = build_index(settings.knowledge_root, max_bytes=settings.knowledge_max_bytes)
    provider = provider or build_provider(settings, transport=provider_transport)
    research = research or ResearchPipeline(settings, resolver=resolver, transport=research_transport)
    orchestrator = Orchestrator(settings, index, provider, research)
    store = ProposalStore(db, settings, launcher=launcher)

    app = FastAPI(
        title="Alfred Assistant",
        version="1.0.0",
        description=(
            "Local-first household-manager assistant. Loopback only. Desktop actions "
            "are disabled by default and always require explicit approval."
        ),
    )
    app.state.settings = settings
    app.state.db = db
    app.state.index = index
    app.state.orchestrator = orchestrator
    app.state.store = store

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def principal(request: Request) -> Principal:
        return authenticate(request, request.app.state.settings)

    # -- health / meta -----------------------------------------------------

    @app.get("/health/live")
    def liveness() -> dict:
        return {"status": "ok", "service": "alfred-assistant"}

    @app.get("/health/ready")
    def readiness() -> dict:
        version = db.schema_version()
        return {
            "status": "ready",
            "database": "reachable",
            "schema_version": version,
            "knowledge_documents": index.document_count,
        }

    @app.get("/api/capabilities")
    def capabilities() -> dict:
        return {
            "persona": personality.persona_descriptor(),
            "persona_policy_version": personality.PERSONA_POLICY_VERSION,
            "capabilities_summary": personality.capabilities_sentence(),
            "answer_modes": ANSWER_MODES,
            "research_modes": ["concise", "deep"],
            "provider": settings.provider_status(),
            "web": settings.web_status(),
            "actions": action_registry.catalog(settings),
            "desktop_actions_enabled": settings.desktop_actions_enabled,
            "clipboard_enabled": settings.clipboard_enabled,
            "safety_policy": [
                "loopback-only networking",
                "desktop actions disabled by default",
                "every action requires propose -> approve -> execute with an immutable audit",
                "strict path confinement to approved roots",
                "web research is SSRF-hardened and off unless enabled",
                "retrieved content is untrusted data and never alters persona or safety",
            ],
        }

    @app.get("/api/status")
    def status() -> dict:
        return {
            "config": settings.sanitized_status(),
            "provider": provider.describe().as_dict(),
            "web": settings.web_status(),
            "index": index.status(),
            "persona_policy_version": personality.PERSONA_POLICY_VERSION,
            "schema_version": db.schema_version(),
        }

    # -- chat / research ---------------------------------------------------

    @app.post("/api/chat")
    async def chat(request: ChatRequest) -> dict:
        return await orchestrator.chat(request)

    @app.post("/api/research")
    async def research_endpoint(request: ResearchRequest) -> dict:
        return await orchestrator.research_answer(request)

    # -- system inspection (authenticated, read-only) ----------------------

    @app.get("/api/system/summary")
    def system_summary_endpoint(_: Principal = Depends(principal)) -> dict:
        return system_summary()

    @app.get("/api/system/disk")
    def system_disk_endpoint(_: Principal = Depends(principal)) -> dict:
        roots = settings.approved_roots or [SERVICE_DIR]
        return disk_summary(roots)

    @app.get("/api/system/directory")
    def system_directory_endpoint(
        root: int = Query(default=0, ge=0),
        path: str = Query(default="."),
        _: Principal = Depends(principal),
    ) -> dict:
        if root >= len(settings.approved_roots):
            raise HTTPException(status_code=400, detail="approved root index is out of range")
        try:
            return directory_listing(
                settings.approved_roots[root], path, limit=settings.directory_listing_limit
            )
        except PathError as exc:
            raise HTTPException(status_code=400, detail=exc.reason) from exc

    @app.get("/api/system/processes")
    def system_processes_endpoint(_: Principal = Depends(principal)) -> dict:
        return process_summary()

    # -- actions (authenticated) ------------------------------------------

    @app.get("/api/actions/catalog")
    def actions_catalog(_: Principal = Depends(principal)) -> dict:
        return {"actions": action_registry.catalog(settings)}

    @app.get("/api/actions/audit")
    def actions_audit(owner: Principal = Depends(principal)) -> dict:
        return {"audit": store.audit_log(owner)}

    @app.get("/api/actions")
    def actions_list(owner: Principal = Depends(principal)) -> dict:
        return {"proposals": store.list_proposals(owner)}

    @app.post("/api/actions/propose")
    def actions_propose(
        request: ProposeRequest, owner: Principal = Depends(principal)
    ) -> dict:
        try:
            return store.propose(owner, request.action_type, request.payload)
        except ProposalError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    @app.get("/api/actions/{proposal_id}")
    def actions_get(proposal_id: str, owner: Principal = Depends(principal)) -> dict:
        try:
            return store.get(owner, proposal_id)
        except ProposalError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    @app.post("/api/actions/{proposal_id}/approve")
    def actions_approve(
        proposal_id: str, request: ApproveRequest, owner: Principal = Depends(principal)
    ) -> dict:
        try:
            return store.approve(owner, proposal_id, request.payload_hash)
        except ProposalError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    @app.post("/api/actions/{proposal_id}/execute")
    def actions_execute(proposal_id: str, owner: Principal = Depends(principal)) -> dict:
        try:
            return store.execute(owner, proposal_id)
        except ProposalError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    @app.post("/api/actions/{proposal_id}/reject")
    def actions_reject(proposal_id: str, owner: Principal = Depends(principal)) -> dict:
        try:
            return store.reject(owner, proposal_id)
        except ProposalError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    # -- UI (local assets only) -------------------------------------------
    # response_model=None tells FastAPI not to build an OpenAPI/Pydantic
    # response model from the Union[FileResponse, JSONResponse] return
    # annotation below -- these routes return a Response subclass directly,
    # which is not itself a valid Pydantic field type.

    @app.get("/", include_in_schema=False, response_model=None)
    def ui_index() -> FileResponse | JSONResponse:
        return _ui_file("index.html", "text/html")

    @app.get("/console.css", include_in_schema=False, response_model=None)
    def ui_css() -> FileResponse | JSONResponse:
        return _ui_file("console.css", "text/css")

    @app.get("/console.js", include_in_schema=False, response_model=None)
    def ui_js() -> FileResponse | JSONResponse:
        return _ui_file("console.js", "application/javascript")

    return app


def _ui_file(name: str, media_type: str) -> FileResponse | JSONResponse:
    path = UI_DIR / name
    if not path.is_file():
        return JSONResponse({"error": "ui asset not found"}, status_code=404)
    return FileResponse(path, media_type=media_type)


app = create_app()
