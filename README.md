# Batcomputer Portfolio

A neon/HUD portfolio with 20 retained compact Python prototypes, one production-style flagship, and two executable supporting evidence projects. Every project page maps to source and records implemented behavior, limitations, and validation status in [`project-evidence.json`](project-evidence.json).

## Architecture

- `app.py` is a small Flask server for the static site, health and inventory APIs, deterministic Alfred responses, and review-only proposal state.
- `batcomputer_console.html`, `style.css`, and `app.js` provide the main HUD.
- The four category HTML files summarize only behavior demonstrated by the paired source.
- `projects/` contains 20 evidence-led project pages.
- `Cybersecurity/`, `IT Support/`, `Network/`, and `Software Automation/` contain the 20 paired Python entry points and project notes.
- `alfred_agent_console.html` and `alfred_agent.js` expose deterministic preview/review controls. Approval records a decision and returns preview content; it never executes commands or writes files.
- `tests/` verifies Flask behavior, route boundaries, Alfred semantics, proposal review behavior, evidence mappings, and local-link integrity.
- `platform/` is an independently served FastAPI operations platform with tenant isolation, RBAC, CRUD/workflows, immutable audit events, Alembic, PostgreSQL configuration, a minimal operator UI, and focused API tests.
- `orbital-data-lab/` is a deterministic two-body simulation and scenario-data service with RK4/velocity-Verlet comparisons, lineage, visualization, and exports.
- `algorithms-quality/` contains original data-structure/algorithm implementations, edge-case tests, complexity notes, and a quality report.

The static pages can be opened directly or published on GitHub Pages. Flask endpoints and server-backed Alfred responses are available only when `app.py` is running.

## Local development

Python 3.11 or newer is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000>. Useful endpoints:

- `GET /api/health`
- `GET /api/site/summary`
- `POST /alfred` with `{"message": "status"}`

## Tests

```powershell
python -m unittest discover -s tests -v
Set-Location platform; python -m pytest tests -q; Set-Location ..
Set-Location orbital-data-lab; python -m pytest tests -q; Set-Location ..
Set-Location algorithms-quality; python -m pytest tests -q; Set-Location ..
python -m ruff check platform orbital-data-lab algorithms-quality
```

CI runs every command above, applies the Alembic migration to a clean SQLite database, compiles the new modules, and validates the Docker Compose configuration without ignored failures.

## Current scope

- The root site remains a Flask-served static portfolio. The separate `platform/` service is the production-style application evidence.
- Alfred is a deterministic local helper with predefined responses. It has no language model, retrieval, memory, autonomous tools, or action execution.
- Coding and homepage proposal endpoints are review-only previews held in process memory. Approve/reject calls do not generate or write content.
- Most paired projects are dependency-free learning prototypes. Some read local fixture files, two invoke bounded loopback-friendly ping/TCP checks, and one writes a local SQLite database when explicitly run.
- There is no hosted demo, cloud deployment, resume download, email address, or LinkedIn profile configured in this repository.
- The root Flask site has no authentication. The separate platform implements authentication but is not hosted and does not claim production deployment.
- The orbital model is educational and explicitly not flight grade. The algorithm suite is educational evidence, not a standard-library replacement.

Detailed run, architecture, operations, deployment, and limitation notes live in each new project's README.
