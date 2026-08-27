import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

PLATFORM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLATFORM_ROOT))
os.environ["PLATFORM_ENVIRONMENT"] = "test"
os.environ["PLATFORM_DATABASE_URL"] = f"sqlite:///{PLATFORM_ROOT / 'platform-test.db'}"
os.environ["PLATFORM_SECRET_KEY"] = "test-secret-that-is-long-enough-for-signing"

from app.config import DEVELOPMENT_SECRET, Settings, get_settings  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuditEvent  # noqa: E402


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def register(client: TestClient, workspace: str, email: str = "admin@example.com") -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"workspace_name": workspace, "email": email, "password": "correct-horse-battery"},
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "x-correlation-id": "test-correlation"}


def create_user(client: TestClient, token: str, email: str, role: str) -> None:
    response = client.post(
        "/api/v1/users",
        headers=auth(token),
        json={"email": email, "password": "viewer-password-123", "role": role},
    )
    assert response.status_code == 201, response.text


def login(client: TestClient, workspace: str, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "workspace_name": workspace,
            "email": email,
            "password": "viewer-password-123",
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_health_openapi_and_expiring_auth(client: TestClient):
    assert client.get("/health/live").json()["status"] == "ok"
    assert client.get("/health/ready").json() == {"status": "ready", "database": "reachable"}
    assert client.get("/openapi.json").json()["info"]["title"] == "Batcomputer Operations Platform"
    token = register(client, "Wayne Operations")
    claims = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    assert datetime.fromtimestamp(claims["exp"], UTC) > datetime.now(UTC)
    assert claims["workspace_id"]
    assert client.get("/api/v1/me", headers=auth(token)).json()["role"] == "admin"
    expired = jwt.encode(
        {**claims, "exp": datetime(2000, 1, 1, tzinfo=UTC)},
        get_settings().secret_key,
        algorithm="HS256",
    )
    assert client.get("/api/v1/me", headers=auth(expired)).status_code == 401


def test_production_configuration_guards():
    with pytest.raises(ValidationError, match="unique secret"):
        Settings(
            environment="production",
            database_url="postgresql://db/app",
            secret_key=DEVELOPMENT_SECRET,
        )
    with pytest.raises(ValidationError, match="requires PostgreSQL"):
        Settings(
            environment="production",
            database_url="sqlite:///unsafe.db",
            secret_key="unique-production-secret-with-at-least-32-characters",
        )


def test_password_auth_and_rbac(client: TestClient):
    admin = register(client, "RBAC")
    create_user(client, admin, "viewer@example.com", "viewer")
    viewer = login(client, "RBAC", "viewer@example.com")
    denied = client.post(
        "/api/v1/assets",
        headers=auth(viewer),
        json={"name": "Router", "category": "cloud_network_platform"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["message"] == "insufficient role"
    bad_login = client.post(
        "/api/v1/auth/login",
        json={"workspace_name": "RBAC", "email": "viewer@example.com", "password": "wrong"},
    )
    assert bad_login.status_code == 401


def test_assets_cover_categories_filters_pagination_and_crud(client: TestClient):
    token = register(client, "Assets")
    categories = [
        "software_automation",
        "defensive_cybersecurity",
        "it_support",
        "data_engineering_analytics",
        "cloud_network_platform",
        "quality_engineering",
    ]
    ids = []
    for index, category in enumerate(categories):
        response = client.post(
            "/api/v1/assets",
            headers=auth(token),
            json={"name": f"asset-{index}", "category": category, "description": category},
        )
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    page = client.get("/api/v1/assets?limit=2&offset=1", headers=auth(token)).json()
    assert page["total"] == 6
    assert len(page["items"]) == 2
    filtered = client.get(
        "/api/v1/assets?category=quality_engineering", headers=auth(token)
    ).json()
    assert filtered["total"] == 1
    duplicate = client.post(
        "/api/v1/assets",
        headers=auth(token),
        json={"name": "asset-1", "category": "software_automation"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["message"] == "record conflicts with existing data"
    updated = client.patch(
        f"/api/v1/assets/{ids[0]}",
        headers=auth(token),
        json={"status": "retired"},
    )
    assert updated.json()["status"] == "retired"
    assert client.get(f"/api/v1/assets/{ids[0]}", headers=auth(token)).status_code == 200
    assert client.delete(f"/api/v1/assets/{ids[0]}", headers=auth(token)).status_code == 204
    assert client.get(f"/api/v1/assets/{ids[0]}", headers=auth(token)).status_code == 404


def test_cross_workspace_records_are_hidden(client: TestClient):
    first = register(client, "Tenant One", "one@example.com")
    second = register(client, "Tenant Two", "two@example.com")
    created = client.post(
        "/api/v1/assets",
        headers=auth(first),
        json={"name": "private", "category": "defensive_cybersecurity"},
    ).json()
    assert client.get(f"/api/v1/assets/{created['id']}", headers=auth(second)).status_code == 404
    assert client.patch(
        f"/api/v1/assets/{created['id']}", headers=auth(second), json={"status": "compromised"}
    ).status_code == 404
    assert client.get("/api/v1/assets", headers=auth(second)).json()["total"] == 0


def test_workflow_transitions_crud_and_asset_isolation(client: TestClient):
    token = register(client, "Workflow")
    asset = client.post(
        "/api/v1/assets",
        headers=auth(token),
        json={"name": "pipeline", "category": "data_engineering_analytics"},
    ).json()
    item = client.post(
        "/api/v1/work-items",
        headers=auth(token),
        json={
            "asset_id": asset["id"],
            "title": "Validate ingestion",
            "details": "Run schema checks",
            "category": "data_engineering_analytics",
        },
    )
    assert item.status_code == 201
    item_id = item.json()["id"]
    invalid = client.post(
        f"/api/v1/work-items/{item_id}/transitions",
        headers=auth(token),
        json={"status": "completed"},
    )
    assert invalid.status_code == 409
    for next_status in ("in_progress", "blocked", "in_progress", "completed"):
        transitioned = client.post(
            f"/api/v1/work-items/{item_id}/transitions",
            headers=auth(token),
            json={"status": next_status},
        )
        assert transitioned.status_code == 200, transitioned.text
    assert client.get(f"/api/v1/work-items/{item_id}", headers=auth(token)).json()[
        "status"
    ] == "completed"
    assert client.patch(
        f"/api/v1/work-items/{item_id}",
        headers=auth(token),
        json={"details": "Schema checks passed"},
    ).status_code == 200
    assert client.delete(f"/api/v1/work-items/{item_id}", headers=auth(token)).status_code == 204


def test_audit_events_are_correlated_and_immutable(client: TestClient):
    token = register(client, "Audit")
    client.post(
        "/api/v1/assets",
        headers=auth(token),
        json={"name": "host", "category": "it_support"},
    )
    response = client.get("/api/v1/audit-events?action=asset.created", headers=auth(token))
    event = response.json()["items"][0]
    assert event["correlation_id"] == "test-correlation"
    with Session(engine) as db:
        stored = db.scalar(select(AuditEvent).where(AuditEvent.id == event["id"]))
        assert stored is not None
        stored.action = "tampered"
        with pytest.raises(ValueError, match="immutable"):
            db.commit()
        db.rollback()
        with pytest.raises(ValueError, match="immutable"):
            db.delete(stored)
            db.commit()


def test_validation_uses_explicit_error_envelope(client: TestClient):
    token = register(client, "Validation")
    response = client.post(
        "/api/v1/assets",
        headers=auth(token),
        json={"name": "", "category": "not-a-category"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.headers["x-correlation-id"]
    generated = client.get(
        "/api/v1/assets",
        headers={**auth(token), "x-correlation-id": "x" * 81},
    )
    assert len(generated.headers["x-correlation-id"]) == 36


def test_alfred_is_unavailable_and_intents_never_execute(client: TestClient):
    token = register(client, "Alfred")
    status_response = client.get("/api/v1/alfred/status", headers=auth(token)).json()
    assert status_response == {
        "status": "unavailable",
        "provider_configured": False,
        "generates_content": False,
        "executes_actions": False,
        "intent_mode": "approval_pending_only",
    }
    intent = client.post(
        "/api/v1/alfred/intents",
        headers=auth(token),
        json={"prompt": "Draft a maintenance plan"},
    )
    assert intent.status_code == 202
    assert intent.json()["status"] == "approval_pending"
    assert intent.json()["executed"] is False

    configured = Settings(
        environment="test",
        database_url=get_settings().database_url,
        secret_key=get_settings().secret_key,
        alfred_provider_url="https://configured.invalid",
    )
    app.dependency_overrides[get_settings] = lambda: configured
    try:
        configured_status = client.get("/api/v1/alfred/status", headers=auth(token)).json()
    finally:
        app.dependency_overrides.clear()
    assert configured_status["status"] == "configured"
    assert configured_status["provider_configured"] is True
    assert configured_status["generates_content"] is False
    assert configured_status["executes_actions"] is False
