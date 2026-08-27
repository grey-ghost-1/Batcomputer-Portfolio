"""HTTP-level tests via FastAPI's TestClient: health/readiness/status/
capabilities/UI/CSP, authentication, and the full action lifecycle end to
end. No test calls a live network endpoint -- ``create_app`` is always given
an explicit, tmp_path-scoped ``Settings`` plus a recording launcher so no
proposal execution can ever start a real process, browser, or clipboard
write.
"""

from __future__ import annotations

import pytest
from alfred.main import CSP, create_app
from conftest import TEST_TOKEN, RecordingLauncher
from fastapi.testclient import TestClient

SESSION_A = "session-aaaaaaaaaaaaaaaaaaaaaaaa"
SESSION_B = "session-bbbbbbbbbbbbbbbbbbbbbbbb"


def auth_headers(token=TEST_TOKEN, session=SESSION_A):
    return {"Authorization": f"Bearer {token}", "X-Alfred-Session": session}


@pytest.fixture
def launcher():
    return RecordingLauncher()


@pytest.fixture
def app_client(settings_factory, approved_root, knowledge_dir, launcher):
    settings = settings_factory(
        desktop_actions_enabled=True,
        approved_roots=[approved_root],
        knowledge_root=knowledge_dir,
    )
    app = create_app(settings, launcher=launcher)
    with TestClient(app) as client:
        yield client


# --- health / readiness --------------------------------------------------------


def test_liveness(app_client):
    response = app_client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "alfred-assistant"}


def test_readiness_reports_schema_version_and_index(app_client):
    response = app_client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["database"] == "reachable"
    assert isinstance(body["schema_version"], int) and body["schema_version"] >= 1
    assert "knowledge_documents" in body


# --- capabilities / status ------------------------------------------------------


def test_capabilities_lists_all_actions_and_safety_policy(app_client):
    body = app_client.get("/api/capabilities").json()
    assert body["persona"]["name"] == "Alfred"
    assert set(body["answer_modes"]) >= {"deterministic", "model", "website", "web"}
    assert {a["action_type"] for a in body["actions"]} == {
        "create_folder",
        "move_file",
        "organize_folder",
        "open_app",
        "open_url",
        "set_clipboard",
    }
    assert isinstance(body["safety_policy"], list) and body["safety_policy"]
    assert body["desktop_actions_enabled"] is True


def test_capabilities_is_unauthenticated_and_read_only(app_client):
    # Capabilities/status are informational and safe to expose without a
    # token; they must never require auth (only actions/system do).
    response = app_client.get("/api/capabilities")
    assert response.status_code == 200


def test_status_never_leaks_the_token(app_client):
    body = app_client.get("/api/status").json()
    assert TEST_TOKEN not in str(body)
    assert body["config"]["action_token_configured"] is True
    assert body["config"]["local_only"] is True


# --- UI / CSP --------------------------------------------------------------------


def test_ui_index_served_with_csp_and_security_headers(app_client):
    response = app_client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert response.headers["Content-Security-Policy"] == CSP
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "Alfred" in response.text


def test_csp_forbids_external_script_and_object_sources():
    assert "script-src 'self'" in CSP
    assert "default-src 'self'" in CSP
    assert "frame-ancestors 'none'" in CSP


def test_ui_css_and_js_served_with_correct_media_types(app_client):
    css = app_client.get("/console.css")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]

    js = app_client.get("/console.js")
    assert js.status_code == 200
    assert "javascript" in js.headers["content-type"]


def test_security_headers_present_even_on_404(app_client):
    response = app_client.get("/this-route-does-not-exist")
    assert response.status_code == 404
    assert response.headers["Content-Security-Policy"] == CSP


def test_ui_missing_asset_returns_honest_404_json(app_client, monkeypatch, tmp_path):
    import alfred.main as main_module

    empty_dir = tmp_path / "no-ui-assets-here"
    empty_dir.mkdir()
    monkeypatch.setattr(main_module, "UI_DIR", empty_dir)
    response = app_client.get("/")
    assert response.status_code == 404
    assert response.json() == {"error": "ui asset not found"}


# --- authentication --------------------------------------------------------------


def test_actions_endpoint_requires_bearer_token(app_client):
    response = app_client.get("/api/actions", headers={"X-Alfred-Session": SESSION_A})
    assert response.status_code == 401


def test_actions_endpoint_rejects_wrong_token(app_client):
    wrong = "z9y8x7w6v5u4t3s2r1q0p9o8n7m6l5k4j3i2h1g0"
    response = app_client.get("/api/actions", headers=auth_headers(token=wrong))
    assert response.status_code == 401


def test_actions_endpoint_requires_valid_session_header(app_client):
    response = app_client.get("/api/actions", headers={"Authorization": f"Bearer {TEST_TOKEN}"})
    assert response.status_code == 400


def test_actions_endpoint_rejects_malformed_session_header(app_client):
    response = app_client.get(
        "/api/actions", headers={"Authorization": f"Bearer {TEST_TOKEN}", "X-Alfred-Session": "short"}
    )
    assert response.status_code == 400


def test_actions_unavailable_returns_503_when_no_token_configured(
    settings_factory, approved_root, knowledge_dir, launcher
):
    settings = settings_factory(
        action_token=None, approved_roots=[approved_root], knowledge_root=knowledge_dir
    )
    app = create_app(settings, launcher=launcher)
    with TestClient(app) as client:
        response = client.get("/api/actions", headers=auth_headers())
        assert response.status_code == 503


# --- system inspection endpoints (authenticated, read-only) --------------------


def test_system_summary_requires_auth_then_succeeds(app_client):
    assert app_client.get("/api/system/summary").status_code == 401
    response = app_client.get("/api/system/summary", headers=auth_headers())
    assert response.status_code == 200
    assert "read-only" in response.json()["label"]


def test_system_directory_is_metadata_only_and_confined(app_client, approved_root):
    marker = "SECRET-FILE-CONTENT-MARKER-XYZ"
    (approved_root / "f.txt").write_text(marker, encoding="utf-8")
    response = app_client.get("/api/system/directory?root=0&path=.", headers=auth_headers())
    assert response.status_code == 200
    assert marker not in response.text


def test_system_directory_rejects_out_of_range_root(app_client):
    response = app_client.get("/api/system/directory?root=99&path=.", headers=auth_headers())
    assert response.status_code == 400


def test_system_directory_rejects_traversal(app_client):
    response = app_client.get("/api/system/directory?root=0&path=../", headers=auth_headers())
    assert response.status_code == 400


def test_system_processes_endpoint_requires_auth(app_client):
    assert app_client.get("/api/system/processes").status_code == 401
    response = app_client.get("/api/system/processes", headers=auth_headers())
    assert response.status_code == 200


# --- action lifecycle over HTTP, end to end ------------------------------------


def test_http_full_action_lifecycle(app_client, approved_root):
    propose = app_client.post(
        "/api/actions/propose",
        headers=auth_headers(),
        json={"action_type": "create_folder", "payload": {"name": "HttpFolder"}},
    )
    assert propose.status_code == 200
    body = propose.json()
    assert body["status"] == "proposed"

    approve = app_client.post(
        f"/api/actions/{body['id']}/approve",
        headers=auth_headers(),
        json={"payload_hash": body["payload_hash"]},
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    execute = app_client.post(f"/api/actions/{body['id']}/execute", headers=auth_headers())
    assert execute.status_code == 200
    assert execute.json()["status"] == "executed"
    assert (approved_root / "HttpFolder").is_dir()


def test_http_execute_without_approval_is_conflict(app_client):
    propose = app_client.post(
        "/api/actions/propose",
        headers=auth_headers(),
        json={"action_type": "create_folder", "payload": {"name": "NoApproval"}},
    )
    body = propose.json()
    execute = app_client.post(f"/api/actions/{body['id']}/execute", headers=auth_headers())
    assert execute.status_code == 409


def test_http_two_sessions_are_isolated(app_client):
    propose = app_client.post(
        "/api/actions/propose",
        headers=auth_headers(session=SESSION_A),
        json={"action_type": "create_folder", "payload": {"name": "Isolated"}},
    )
    proposal_id = propose.json()["id"]
    other_session = app_client.get(
        f"/api/actions/{proposal_id}", headers=auth_headers(session=SESSION_B)
    )
    assert other_session.status_code == 404

    own_session = app_client.get(f"/api/actions/{proposal_id}", headers=auth_headers(session=SESSION_A))
    assert own_session.status_code == 200


def test_http_audit_endpoint_reflects_proposal_events(app_client):
    app_client.post(
        "/api/actions/propose",
        headers=auth_headers(),
        json={"action_type": "create_folder", "payload": {"name": "AuditMe"}},
    )
    audit = app_client.get("/api/actions/audit", headers=auth_headers())
    assert audit.status_code == 200
    assert any(row["event"] == "proposed" for row in audit.json()["audit"])


def test_http_propose_unknown_action_type_is_422_via_schema_validation(app_client):
    # ProposeRequest.action_type is a Literal of the six known types, so an
    # unknown type is rejected by schema validation (422) before it ever
    # reaches the store's own KeyError->404 path (that path is exercised
    # directly against ProposalStore in test_actions_registry.py).
    response = app_client.post(
        "/api/actions/propose",
        headers=auth_headers(),
        json={"action_type": "delete_everything", "payload": {}},
    )
    assert response.status_code == 422


def test_http_propose_invalid_payload_is_400(app_client):
    response = app_client.post(
        "/api/actions/propose",
        headers=auth_headers(),
        json={"action_type": "create_folder", "payload": {"name": 12345}},
    )
    assert response.status_code == 400


def test_http_actions_catalog_endpoint(app_client):
    response = app_client.get("/api/actions/catalog", headers=auth_headers())
    assert response.status_code == 200
    assert len(response.json()["actions"]) == 6


# --- chat / research endpoints (no live network; web disabled by default) -----


def test_chat_endpoint_smoke(app_client):
    response = app_client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 200
    assert response.json()["reply"]


def test_chat_endpoint_rejects_empty_message(app_client):
    response = app_client.post("/api/chat", json={"message": ""})
    assert response.status_code == 422


def test_research_endpoint_disabled_by_default_never_touches_network(app_client):
    response = app_client.post("/api/research", json={"query": "anything"})
    assert response.status_code == 200
    assert response.json()["used_web"] is False
