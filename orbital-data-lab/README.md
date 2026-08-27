# Orbital Data Lab

A deterministic educational two-body simulator and small scenario-data service. It is **not flight grade** and must not be used for mission planning, navigation, collision assessment, or safety decisions.

## Capabilities

- Configurable central-body label, gravitational parameter, 2D initial position/velocity, duration, step size, and RK4/velocity-Verlet selection.
- Bounded Pydantic inputs (including a 20,000-step limit), full trajectory output, specific-energy tracking, integrator drift, and final-state comparison metrics.
- A browser canvas visualization at `/`.
- SQLite scenario storage with content-derived IDs, idempotent writes, share paths, schema/algorithm lineage, input hashes, and JSON/CSV exports.

## Run and test

From the repository root:

```powershell
python -m pip install -r requirements.txt
Set-Location orbital-data-lab
python -m uvicorn orbital_lab.api:app --reload --port 8010
```

Open <http://127.0.0.1:8010>. Tests and lint:

```powershell
Set-Location orbital-data-lab
python -m pytest tests -q
Set-Location ..
python -m ruff check orbital-data-lab
```

## Model and limits

The equations model one point mass moving in a fixed, spherically symmetric central gravity field. They omit perturbations, finite burns, atmosphere, relativity, body rotation, ephemerides, frame transformations, uncertainty propagation, collision detection, and numerical event handling. Energy-drift tests use one idealized circular Earth orbit; passing them does not validate other regimes.

SQLite is appropriate for this local evidence project, not concurrent distributed ingestion. Scenario lineage records code-level algorithm/schema versions but not a signed build provenance chain.
