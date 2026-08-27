# Batcomputer Portfolio

Justin Wimmer's dark-neon engineering portfolio for entry-level full-stack and backend software roles. The strongest evidence is four production-style Python projects backed by runnable tests, exact local commands, explicit security/reliability boundaries, and honest limitations. All 20 original learning-project folders remain intact; 19 are secondary **Labs & Prototypes**, while Alfred has been promoted into a local-assistant flagship.

**Strongest stack:** Python, FastAPI, Flask, Pydantic, SQLAlchemy, Alembic, PostgreSQL, SQLite, JavaScript, Pytest, Ruff, Docker configuration, and GitHub Actions.

[Open the recruiter homepage](batcomputer_console.html) · [Review evidence inventory](project-evidence.json) · [Deployment guide](DEPLOYMENT.md)

> **Sharing status:** The repository is public. Each flagship card pairs a locally served evidence page with its public GitHub branch/tree source.

## Primary project matrix

| Project | Engineering evidence | Tests | Demo status |
|---|---|---:|---|
| [Batcomputer Operations Platform](projects/operations-platform.html) | Tenant-isolated FastAPI modular monolith; Argon2 auth, RBAC, workflows, same-transaction audits, Alembic/PostgreSQL, operator UI | 9 | Local only; not claimed as hosted |
| [Orbital Data Lab](projects/orbital-data-lab.html) | Deterministic RK4/velocity-Verlet API; bounded inputs, energy drift, content-addressed SQLite, lineage, exports, interactive canvas UI | 8 | Local only; educational, not flight grade |
| [Algorithms & Quality](projects/algorithm-quality-lab.html) | Original data structures and algorithms; complexity trade-offs and deterministic normal/edge behavior | 7 | Source-and-test project; no service |
| [Alfred AI Assistant](projects/alfred-ai-assistant.html) | Loopback-only FastAPI; broad safe chat through optional Ollama/compatible models; cited website/web knowledge; deterministic fallback/refusals; redacted inspection; typed owner-bound, expiring, approval-gated Windows actions | Dedicated local safety suite plus public showcase route, boundary, XSS, state, approval, audit, accessibility, and link tests | [Controlled public showcase](alfred-showcase.html) ships with Flask; local model and desktop service remain separate and off the public surface |
| [Labs & Prototypes](labs.html) | 19 secondary exercises across software, security, IT support, and network/systems fundamentals; all 20 legacy folders retained | Covered by site inventory/link tests | Local scripts only |

## Architecture

```text
Recruiter-facing Flask site (:5000)
├── Neon HUD, four primary case studies, labs, evidence, optional application links
├── Deterministic Alfred helper (no model or action execution)
├── Controlled Alfred showcase -> fixed evidence + synthetic scenarios + session-local audit
└── Route/link/config/accessibility/deployment-contract tests

Independent FastAPI services
├── platform/ (:8000) -> auth/RBAC/workflows/audits -> PostgreSQL (SQLite in tests)
├── orbital-data-lab/ (:8010) -> simulation/API/exports -> SQLite scenarios
└── alfred-assistant/ (:8020, loopback only)
    ├── broad safe chat + cited site/web knowledge + optional bounded reasoning providers
    └── authenticated preview/approval/execution -> local SQLite audit state

Executable quality evidence
└── algorithms-quality/ -> dependency-free implementations + Pytest
```

The Flask site, platform, Orbital service, and Alfred local service are separate processes and do not share authentication or process state. The public Flask site never proxies Alfred's action APIs. Its showcase uses a separate fixed-data Python module, same-origin JSON routes, signed per-browser state, exact synthetic previews, explicit approval, and capped simulated audits. It has no model, research, repository-read, system-inspection, filesystem, app, URL-launch, or clipboard adapter. `project-evidence.json` maps all 23 project pages to source folders, run commands, implemented behavior, limitations, and validation status.

## Repository map

- `batcomputer_console.html`, `style.css`, `app.js` — visually faithful recruiter homepage and deterministic browser behavior
- `alfred-showcase.html`, `alfred-showcase.js`, `alfred_showcase.py` — bounded cited public Q&A and synthetic approval workflow
- `app.py`, `site_config.py` — Flask delivery, safe routes, health/summary/config APIs, optional-link omission, and disabled-by-default session-owned proposal metadata
- `projects/` — four primary case studies across the original 23 detail-page paths
- `Cybersecurity/`, `IT Support/`, `Network/`, `Software Automation/` — all 20 original prototype source folders
- `platform/` — independently served operations platform, migration, container, UI, and API tests
- `orbital-data-lab/` — independently served simulation API, storage, UI, container, and tests
- `algorithms-quality/` — algorithms, edge-case tests, complexity table, and quality report
- `alfred-assistant/` — native local FastAPI assistant, provider/research boundaries, typed desktop actions, SQLite audit state, console, and tests
- `ALFRED_STATUS.md` — code-grounded implementation checklist, staged roadmap, threat model, and non-goals
- `render.yaml`, `docker-compose.yml`, `Dockerfile`, `DEPLOYMENT.md` — deployment path and operational boundaries
- `scripts/smoke_check.py` — non-mutating health/readiness checks for all deployable services
- `.github/workflows/ci.yml` — all suites, migration, lint, compile, and Compose config validation

Static HTML/CSS/JavaScript and evidence JSON can be published on GitHub Pages. Flask/FastAPI endpoints, environment-driven application links, Alfred server responses, migrations, and databases cannot run on Pages. Alfred is deliberately excluded from Render and Docker because desktop skills require a trusted native Windows session and loopback-only binding. See [DEPLOYMENT.md](DEPLOYMENT.md) for the exact boundary.

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
- `GET /api/site/config`
- `POST /alfred` with `{"message": "status"}`
- `GET /api/alfred-showcase/state`
- `POST /api/alfred-showcase/ask`
- `POST /api/alfred-showcase/proposals`

Optional email, LinkedIn, resume, platform demo, Orbital demo, and public-source override values come from the single safe source in `site_config.py`; missing or invalid values are omitted. The site defaults to the now-public repository source URLs, while `SITE_PUBLIC_SOURCE_URL` can redirect them to a validated public GitHub tree root after a fork or branch move. No resume file is currently included. To add one later, follow [Adding a resume later](DEPLOYMENT.md#adding-a-resume-later).

## Verified commands and counts

The current baseline is **435 passing automated tests** across five suites, with one platform-dependent Alfred symlink test skipped where the host cannot create links: 34 Flask/site/showcase tests, 10 platform tests, 8 Orbital tests, 7 algorithm tests, and 376 Alfred safety/provider/API/UI tests.

```powershell
# Portfolio and public showcase: 34
python -m unittest discover -s tests -v

# Platform migration + API: 10
Set-Location platform
$env:PLATFORM_ENVIRONMENT = "test"
$env:PLATFORM_DATABASE_URL = "sqlite:///./migration-check.db"
$env:PLATFORM_SECRET_KEY = "ci-only-secret-that-is-long-enough-for-tests"
python -m alembic -c alembic.ini upgrade head
python -m pytest tests -q
Set-Location ..

# Orbital: 8
Set-Location orbital-data-lab
python -m pytest tests -q
Set-Location ..

# Algorithms: 7
python -m pytest algorithms-quality\tests -q

# Alfred local assistant: 376 passed, 1 host-dependent symlink skip
python -m pytest alfred-assistant\tests -q

# Static checks
python -m ruff check app.py site_config.py scripts tests platform orbital-data-lab algorithms-quality alfred-assistant
python -m mypy --check-untyped-defs alfred-assistant\alfred
python -m compileall -q app.py site_config.py scripts tests platform orbital-data-lab algorithms-quality alfred-assistant
node --check alfred-assistant\ui\console.js
docker compose config --quiet
```

CI runs this chain and validates Compose structure. Docker is unavailable in the current local environment, so image builds and live Compose startup remain CI/host validation steps rather than claimed local results.

## Deployment status and limits

- **Deployment status:** configuration exists; no hosted deployment is claimed.
- **Source visibility:** the GitHub repository is public; each flagship retains both local evidence and a clearly labeled source CTA.
- The root Flask site has no user accounts because it serves public portfolio content. Local proposal metadata is disabled by default, session-owned when enabled, and never reads repository files.
- The platform implements authentication and tenant boundaries, but not MFA, SSO, password reset, refresh-token revocation, rate limiting, background jobs, or external integrations.
- The homepage helper and public showcase remain deterministic and non-executing. The showcase answers only from fixed evidence and simulates fixed scenarios with exact previews, explicit approval, synthetic results, and per-browser capped audits. The separate local Alfred service can send ordinary safe questions to a deliberately configured Ollama or compatible provider, with bounded conversation history and an explicit deterministic fallback when unavailable. Website and web research remain cited modes. It is not generally autonomous: harmful/disallowed requests are refused before provider/tool use, while desktop actions are typed, disabled by default, and require exact preview plus explicit per-action approval.
- The Orbital model is educational and omits perturbations, burns, atmosphere, ephemerides, uncertainty, collision handling, and flight validation.
- Algorithm implementations demonstrate reasoning and tests; they do not replace optimized standard-library or production packages.
- Most retained labs are intentionally small, dependency-light learning prototypes—not production systems.

## Ownership and contribution

This repository presents Justin Wimmer's portfolio work; project direction and the implementation described in each case study belong to that portfolio. Git history remains the source of individual commit attribution. Proposed outside changes should use focused issues and pull requests, preserve all legacy project paths, include tests, and avoid expanding claims beyond executable behavior.

## Roadmap / issue candidates

1. Add platform refresh-token rotation/revocation, rate limiting, audit export/retention, and a documented backup-restore drill.
2. Version Orbital storage migrations and add validated perturbation models as separately scoped educational experiments.
3. Deploy the three web services, record real HTTPS URLs only after smoke checks pass, and add centralized logs/alerts.
4. Run a browser-assisted accessibility matrix across Chromium/Firefox at mobile and desktop widths and record reproducible findings.
