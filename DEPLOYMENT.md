# Deployment guide

No service in this repository is claimed as currently deployed. The configuration below is a repeatable path for a reviewer or owner to deploy three independent web processes:

| Service | Runtime | Default port | Persistence | Health |
|---|---|---:|---|---|
| Portfolio site | Flask + Gunicorn | 5000 | None | `/api/health` |
| Operations platform | FastAPI + Uvicorn | 8000 | PostgreSQL + Alembic | `/health/live`, `/health/ready` |
| Orbital Data Lab | FastAPI + Uvicorn | 8010 | SQLite scenario file | `/health/live`, `/health/ready` |
| Algorithms & Quality | Python tests only | N/A | None | N/A |

The services do not depend on one another at runtime. Deploy them as separate processes and domains so the public portfolio does not share the platform's authentication or database boundary.

## Local production-like startup

Install Python 3.11 or newer and dependencies from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Start each web process in a separate terminal:

```powershell
# Portfolio (Gunicorn runs on Linux deployment hosts; use python app.py on Windows)
gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 4 app:app

# Platform: migrate before every release, then start the API
Set-Location platform
python -m alembic -c alembic.ini upgrade head
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Orbital Data Lab
Set-Location orbital-data-lab
python -m uvicorn orbital_lab.api:app --host 0.0.0.0 --port 8010
```

For a local multi-container environment, copy `.env.example` to `.env`, replace both documented development secrets, and run `docker compose up --build`. Compose explicitly maps the `SITE_*` values from `.env` into the portfolio container; `.env` is not copied into any image. The Compose file starts the portfolio, PostgreSQL, the migrated platform, and the Orbital service with health checks. Docker was not available in the layer-3 local environment; CI performs `docker compose config --quiet`, and an environment with Docker must perform the image build and live Compose check.

## Render blueprint

[`render.yaml`](render.yaml) defines the three web services and a managed PostgreSQL database. Render deployment is intentionally manual (`autoDeploy: false`):

1. Create a Render Blueprint from this repository and review names, regions, and plans before applying it.
2. Set `PLATFORM_ALLOWED_ORIGINS` to the exact HTTPS origins allowed to call the platform. Do not use `*` with authenticated endpoints.
3. Confirm `PLATFORM_SECRET_KEY` is generated and stored only in Render's secret environment.
4. Keep the platform migration in the startup/release command and inspect migration logs before shifting traffic.
5. Use a plan with a persistent disk for Orbital scenarios, or accept that SQLite data will be ephemeral. The blueprint requests a 1 GB disk.
6. After deployment, run the smoke command below against the assigned HTTPS URLs.

The platform accepts Render's `postgresql://` connection string and normalizes it to the installed Psycopg 3 SQLAlchemy driver.

The portfolio container uses one Gunicorn worker as a conservative default. Proposal metadata lives in signed client cookies rather than process memory. If the service is scaled to multiple workers or instances, every instance must receive the same strong `SITE_SESSION_SECRET`; the random fallback is intentionally restart-local.

## Production configuration

| Variable | Service | Secret | Requirement |
|---|---|---|---|
| `PLATFORM_ENVIRONMENT` | Platform | No | Must be `production` outside local/test environments |
| `PLATFORM_DATABASE_URL` | Platform | Yes | PostgreSQL URL; never commit it |
| `PLATFORM_DATABASE_HOST` | Platform | No | Compose host; activates field-based URL assembly |
| `PLATFORM_DATABASE_PORT` | Platform | No | Compose database port; default 5432 |
| `PLATFORM_DATABASE_NAME` | Platform | No | Compose database name |
| `PLATFORM_DATABASE_USER` | Platform | No | Compose database user |
| `PLATFORM_DATABASE_PASSWORD` | Platform | Yes | Raw password assembled and percent-encoded by SQLAlchemy |
| `PLATFORM_SECRET_KEY` | Platform | Yes | Unique random value of at least 32 characters |
| `PLATFORM_ACCESS_TOKEN_MINUTES` | Platform | No | 5–1440; default 30 |
| `PLATFORM_ALLOWED_ORIGINS` | Platform | No | Comma-separated exact HTTPS origins |
| `ORBITAL_DATABASE_PATH` | Orbital | No | Writable persistent path, such as `/data/scenarios.db` |
| `SITE_CONTACT_EMAIL` | Portfolio | Personal | Optional; omitted from UI when unset or invalid |
| `SITE_LINKEDIN_URL` | Portfolio | Personal | Optional HTTPS URL; omitted when unset or invalid |
| `SITE_RESUME_PATH` | Portfolio | No | Optional existing PDF under `assets/`; omitted otherwise |
| `SITE_PLATFORM_DEMO_URL` | Portfolio | No | Optional HTTPS URL; omitted otherwise |
| `SITE_ORBITAL_DEMO_URL` | Portfolio | No | Optional HTTPS URL; omitted otherwise |
| `SITE_PUBLIC_SOURCE_URL` | Portfolio | No | Optional public GitHub tree-root override for forks or branch moves |
| `SITE_PROPOSALS_ENABLED` | Portfolio | No | Disabled by default; enable only for a trusted local review session |
| `SITE_SESSION_SECRET` | Portfolio | Yes | At least 32 random characters with sufficient variety when proposals are enabled |

Do not put secrets in `.env.example`, Docker build arguments, source files, or client-side JavaScript. Inject them through the deployment provider. Rotating `PLATFORM_SECRET_KEY` invalidates all outstanding access tokens; schedule rotation with a user re-login window. Use managed PostgreSQL backups, take a verified backup before migrations, and practice restore. Because the initial migration has no production data downgrade strategy, restore from backup rather than improvising a destructive downgrade.

Compose passes the PostgreSQL host, port, database, user, and password as separate values. The platform uses SQLAlchemy's `URL.create`, so secure passwords containing URI delimiters such as `@:/#` are encoded correctly rather than interpolated into a connection string. Quote such values in `.env` (for example, `POSTGRES_PASSWORD='secure@:/#value'`) so dotenv parsing preserves every character.

Review-only proposal endpoints are unavailable unless `SITE_PROPOSALS_ENABLED=true`. When locally enabled, Flask signs session-owned proposal IDs with `SITE_SESSION_SECRET`; one browser cannot read or decide another browser's proposal. The API records only bounded, user-supplied metadata and never reads or returns repository file content. Session payload limits are regression-tested below Flask's maximum cookie size. Keep this feature disabled on the public portfolio.

Recruiter-facing flagship cards pair locally served evidence with the public GitHub source on this branch. `SITE_PUBLIC_SOURCE_URL` is an optional override for a public fork or branch move; it must be a complete GitHub tree root such as `https://github.com/owner/repository/tree/main`. The server validates the root and returns tested, fully constructed project URLs for the browser.

### Adding a resume later

1. Add the real PDF at a repository path such as `assets/resume.pdf`.
2. Set `SITE_RESUME_PATH=assets/resume.pdf` on the Flask service.
3. Restart and verify `/api/site/config` contains the Resume link.

No resume link is rendered unless the configured file exists. Email, LinkedIn, and hosted-demo links follow the same omission rule. On static-only hosting there is no Flask configuration endpoint, so these environment-driven links remain absent.

## Health and smoke checks

With all three services running:

```powershell
python scripts\smoke_check.py `
  --site http://127.0.0.1:5000 `
  --platform http://127.0.0.1:8000 `
  --orbital http://127.0.0.1:8010
```

For production, pass the three HTTPS origins. The script checks liveness and database readiness but does not create accounts, mutate operational data, or run a simulation.

## GitHub Pages boundary

GitHub Pages can publish the HTML, CSS, JavaScript, images, project pages, and evidence JSON. It cannot run Flask, FastAPI, Gunicorn, Uvicorn, Alembic, health endpoints, Alfred server responses, environment-driven contact links, or either database-backed service. The browser helper falls back to deterministic local text when Flask is absent. Use Render, another container host, or separate application hosting for dynamic behavior; do not describe a Pages-only publication as a deployed API.

The GitHub repository is public at the time of this update. The three configured branch/tree source URLs were checked without authentication before release; keep the local evidence links available so the case studies remain useful if repository visibility or branch names change later.
