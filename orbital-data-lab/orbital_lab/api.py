import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse

from .physics import simulate
from .schemas import SavedScenario, SimulationRequest, SimulationResult
from .storage import ScenarioStore

ROOT = Path(__file__).resolve().parents[1]
store = ScenarioStore(Path(os.getenv("ORBITAL_DATABASE_PATH", ROOT / "scenarios.db")))
app = FastAPI(
    title="Orbital Data Lab",
    version="1.0.0",
    description="Deterministic, educational two-body simulation. Explicitly not flight grade.",
)


@app.get("/health/live")
def liveness():
    return {"status": "ok", "service": "orbital-data-lab"}


@app.get("/health/ready")
def readiness():
    connection = store.connect()
    try:
        connection.execute("SELECT 1").fetchone()
    finally:
        connection.close()
    return {"status": "ready", "database": "reachable"}


@app.get("/", include_in_schema=False)
def ui():
    return FileResponse(ROOT / "ui" / "index.html")


@app.post("/api/v1/simulations", response_model=SimulationResult)
def run_simulation(request: SimulationRequest):
    return simulate(request)


@app.post("/api/v1/scenarios", response_model=SavedScenario)
def save_scenario(request: SimulationRequest):
    return store.save(request, simulate(request))


@app.get("/api/v1/scenarios/{scenario_id}", response_model=SavedScenario)
def get_scenario(scenario_id: str):
    try:
        return store.get(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="scenario not found") from exc


@app.get("/scenarios/{scenario_id}", include_in_schema=False)
def share_scenario(scenario_id: str):
    get_scenario(scenario_id)
    return RedirectResponse(f"/api/v1/scenarios/{scenario_id}/export.json")


@app.get("/api/v1/scenarios/{scenario_id}/export.json", response_model=SavedScenario)
def export_json(scenario_id: str):
    return get_scenario(scenario_id)


@app.get("/api/v1/scenarios/{scenario_id}/export.csv", response_class=PlainTextResponse)
def export_csv(scenario_id: str):
    try:
        return PlainTextResponse(
            store.export_csv(scenario_id),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{scenario_id}.csv"'},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="scenario not found") from exc
