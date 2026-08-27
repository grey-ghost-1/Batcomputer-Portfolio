import math
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["ORBITAL_DATABASE_PATH"] = str(ROOT / "orbital-test.db")

from orbital_lab.api import app, store  # noqa: E402
from orbital_lab.physics import simulate  # noqa: E402
from orbital_lab.schemas import SimulationRequest  # noqa: E402


def circular_request() -> SimulationRequest:
    mu = 3.986004418e14
    radius = 7_000_000.0
    period = 2 * math.pi * math.sqrt(radius**3 / mu)
    return SimulationRequest(
        gravitational_parameter=mu,
        initial_position=(radius, 0),
        initial_velocity=(0, math.sqrt(mu / radius)),
        duration_seconds=period,
        step_seconds=10,
    )


def test_known_circular_orbit_returns_near_initial_state():
    result = simulate(circular_request())
    for run in result.runs.values():
        final = run.samples[-1]
        assert math.dist(final.position, (7_000_000.0, 0.0)) < 2_000
        assert math.dist(final.velocity, (0.0, math.sqrt(3.986004418e14 / 7_000_000))) < 3


def test_energy_drift_is_bounded_for_both_integrators():
    result = simulate(circular_request())
    assert result.runs["rk4"].max_relative_energy_drift < 1e-9
    assert result.runs["velocity_verlet"].max_relative_energy_drift < 1e-7
    assert result.comparison.final_position_delta_m is not None


def test_simulation_is_deterministic():
    request = circular_request()
    assert simulate(request).model_dump() == simulate(request).model_dump()


def test_bounded_validation():
    client = TestClient(app)
    too_many = client.post(
        "/api/v1/simulations", json={"duration_seconds": 100_000, "step_seconds": 1}
    )
    assert too_many.status_code == 422
    invalid_radius = client.post(
        "/api/v1/simulations", json={"initial_position": [0, 0]}
    )
    assert invalid_radius.status_code == 422


def test_health_endpoints_report_liveness_and_database_readiness():
    client = TestClient(app)
    assert client.get("/health/live").json() == {
        "status": "ok",
        "service": "orbital-data-lab",
    }
    assert client.get("/health/ready").json() == {
        "status": "ready",
        "database": "reachable",
    }


def test_ui_exposes_accessible_controls_responsive_canvas_and_local_assets():
    client = TestClient(app)
    page = client.get("/")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    html = page.text
    for expected in (
        'id="simulation"',
        'id="runSimulation"',
        'data-state="idle"',
        'aria-describedby="runStatus" aria-busy="false"',
        'id="runStatus" role="status" aria-live="polite"',
        'id="pauseAnimation"',
        'id="replayAnimation"',
        'id="orbitCanvas"',
        'id="rk4DriftMetric"',
        'id="verletDriftMetric"',
        'id="positionDeltaMetric"',
        'id="jsonLink"',
        'id="csvLink"',
        'id="shareLink"',
        "Not flight grade",
    ):
        assert expected in html
    assert 'href="/orbital.css"' in html
    assert 'src="/orbital.js"' in html

    stylesheet = client.get("/orbital.css")
    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert "overflow-x: hidden" in stylesheet.text
    assert ":focus-visible" in stylesheet.text
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet.text

    script = client.get("/orbital.js")
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]
    for expected in (
        'fetch("/api/v1/scenarios"',
        "response.ok",
        "requestAnimationFrame",
        "cancelAnimationFrame",
        "window.devicePixelRatio",
        '"(prefers-reduced-motion: reduce)"',
        "ResizeObserver",
        "max_relative_energy_drift",
        "final_position_delta_m",
        "saved.share_path",
    ):
        assert expected in script.text


def test_saved_scenario_response_matches_ui_metrics_and_result_links():
    client = TestClient(app)
    response = client.post(
        "/api/v1/scenarios",
        json={"duration_seconds": 30, "step_seconds": 10},
    )
    assert response.status_code == 200
    saved = response.json()
    assert saved["request"]["duration_seconds"] == 30
    assert saved["request"]["step_seconds"] == 10
    assert saved["share_path"] == f"/scenarios/{saved['scenario_id']}"
    assert set(saved["result"]["runs"]) == {"rk4", "velocity_verlet"}
    assert set(saved["result"]["comparison"]) == {
        "final_position_delta_m",
        "final_velocity_delta_mps",
    }
    for integrator in ("rk4", "velocity_verlet"):
        run = saved["result"]["runs"][integrator]
        assert len(run["samples"]) >= 2
        assert set(run["samples"][0]) == {
            "time_seconds",
            "position",
            "velocity",
            "specific_energy",
        }
        assert isinstance(run["max_relative_energy_drift"], float)

    scenario_id = saved["scenario_id"]
    assert client.get(saved["share_path"], follow_redirects=True).status_code == 200
    assert client.get(f"/api/v1/scenarios/{scenario_id}/export.json").status_code == 200
    csv_export = client.get(f"/api/v1/scenarios/{scenario_id}/export.csv")
    assert csv_export.status_code == 200
    assert f'filename="{scenario_id}.csv"' in csv_export.headers["content-disposition"]


def test_api_storage_idempotence_exports_and_lineage():
    database = ROOT / "orbital-test.db"
    database.unlink(missing_ok=True)
    store.initialize()
    client = TestClient(app)
    payload = circular_request().model_dump(mode="json")
    first = client.post("/api/v1/scenarios", json=payload)
    second = client.post("/api/v1/scenarios", json=payload)
    assert first.status_code == 200
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    scenario_id = first.json()["scenario_id"]
    stored = client.get(f"/api/v1/scenarios/{scenario_id}")
    assert stored.json()["lineage"]["schema_version"] == 1
    assert stored.json()["lineage"]["algorithm_version"] == "two-body-1"
    assert client.get(first.json()["share_path"]).status_code == 200
    csv_export = client.get(f"/api/v1/scenarios/{scenario_id}/export.csv")
    assert csv_export.status_code == 200
    assert csv_export.text.startswith("scenario_id,integrator,time_seconds")
    assert client.get(f"/api/v1/scenarios/{scenario_id}/export.json").status_code == 200
    assert client.get("/api/v1/scenarios/missing").status_code == 404
