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
