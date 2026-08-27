# Deployment guide

No service in this repository is claimed as currently deployed. This layer provides a repeatable Render release for the Flask portfolio and its controlled Alfred showcase as one public web service. The other repository applications remain independently runnable:

| Service | Runtime | Default port | Persistence | Health |
|---|---|---:|---|---|
| Portfolio site | Flask + Gunicorn | 5000 | None | `/api/health` |
| Operations platform | FastAPI + Uvicorn | 8000 | PostgreSQL + Alembic | `/health/live`, `/health/ready` |
| Orbital Data Lab | FastAPI + Uvicorn | 8010 | SQLite scenario file | `/health/live`, `/health/ready` |
| Algorithms & Quality | Python tests only | N/A | None | N/A |
| Alfred local assistant | FastAPI + Uvicorn (native Windows only) | 8020 | Local SQLite audit store | `/health/live`, `/health/ready` |

The applications do not depend on one another at runtime. This Render release intentionally deploys only the portfolio. It includes a controlled Alfred showcase backed only by fixed evidence and synthetic per-session state. The Operations Platform and Orbital Data Lab are not provisioned by this Blueprint. **The desktop-capable Alfred service is never a public deployment target.** It rejects non-loopback binding, starts with execution disabled, and must run natively on the user's trusted Windows session. It is intentionally absent from Docker Compose and Render.

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

# Alfred (separate trusted local terminal; see alfred-assistant/README.md first)
Set-Location alfred-assistant
.\start.ps1
```

For a local multi-container environment, copy `.env.example` to `.env`, replace both documented development secrets, and run `docker compose up --build`. Compose explicitly maps the `SITE_*` values from `.env` into the portfolio container; `.env` is not copied into any image. The Compose file starts the portfolio, PostgreSQL, the migrated platform, and the Orbital service with health checks. Docker was not available in the layer-3 local environment; CI performs `docker compose config --quiet`, and an environment with Docker must perform the image build and live Compose check.

## Render blueprint

[`render.yaml`](render.yaml) defines one manually activated Python web service named `batcomputer-portfolio`. It installs the root requirements, starts `app:app` with Gunicorn, binds only the deployment process to `0.0.0.0:$PORT`, and uses `/healthz` for health checks. Local `python app.py` startup remains loopback-only on port 5000. Automatic deploys are off so applying or promoting a release remains an explicit owner decision.

### Blueprint setup

1. Merge the release into `agents/batcomputer-website-query`, then open the repository's exact [Deploy to Render activation URL](https://render.com/deploy?repo=https://github.com/grey-ghost-1/Batcomputer-Portfolio). Sign in and authorize repository access in Render; these are the remaining owner-controlled steps, and no credentials belong in git.
2. Review the repository-root `render.yaml`, the `agents/batcomputer-website-query` production branch, and the single `batcomputer-portfolio` service, then apply the Blueprint. Do not add the platform, Orbital, or `alfred-assistant` as linked services.
3. Confirm Render generated `SITE_SESSION_SECRET`. Keep `SITE_ENVIRONMENT=production`, `SITE_HOSTED_MODE=true`, and `SITE_PROPOSALS_ENABLED=false`. Hosted startup fails closed if these safety requirements conflict or the managed session secret is absent.
4. Trigger the first manual deploy and wait for the `/healthz` check to pass. The expected URL is `https://batcomputer-portfolio.onrender.com` when that globally unique service hostname is available; otherwise use the exact `https://<render-assigned-service-name>.onrender.com` shown by Render. The corresponding health URL is `<service-origin>/healthz`.
5. Verify `/alfred-showcase.html` on that HTTPS origin. It must report curated evidence, no connected model, disabled network tools, and permanently simulated execution.

The hosted process trusts one Render proxy hop for forwarded scheme, client, and host information. Secure cookies, HTTPS URL generation, HSTS, a same-origin CSP, framing denial, MIME-sniffing denial, and a no-referrer policy are enabled in production. Public pages contain no `http://` or localhost links. Port 8020 is not bound, proxied, linked, or configured in the Blueprint.

### Rollback

In the Render service, open **Deploys**, select the last known-good successful deploy, and choose **Rollback**. Confirm `<service-origin>/healthz` returns `{"status":"ok"}` and recheck the controlled showcase. Because this service has no database or durable server state, rollback requires no data migration. Keep automatic deploys off until the rolled-back release is accepted.

### Custom domain follow-up

After the generated `onrender.com` URL passes smoke and security checks, add the custom domain in **Settings > Custom Domains**, create the exact DNS records Render provides, wait for Render's TLS certificate to become valid, and then test the custom-domain `/healthz` and showcase URLs. Do not publish the domain before HTTPS is active. No localhost or port-8020 URL should be added as a redirect, environment value, or public link.

## Production configuration

| Variable | Service | Secret | Requirement |
|---|---|---|---|
| `PYTHON_VERSION` | Portfolio | No | Render default is pinned by the Blueprint to `3.12.11` |
| `SITE_ENVIRONMENT` | Portfolio | No | `production` in Render; defaults to `development` locally |
| `SITE_HOSTED_MODE` | Portfolio | No | `true` in Render; defaults to `false` locally and enforces hosted safety invariants |
| `SITE_PROPOSALS_ENABLED` | Portfolio | No | Must remain `false` in hosted mode; optional local review routes stay available only outside hosted mode |
| `SITE_SESSION_SECRET` | Portfolio | Yes | Required in hosted mode; generated and retained by Render, never committed |
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

Only the first five variables above apply to the Render portfolio service. All contact, LinkedIn, resume, demo, and source-link variables are optional and safely omitted when unset. The platform and Orbital variables are for their separate local or future deployment paths; they are not present in this Blueprint.

Do not put secrets in `.env.example`, Docker build arguments, source files, or client-side JavaScript. Inject them through the deployment provider. Rotating `PLATFORM_SECRET_KEY` invalidates all outstanding access tokens; schedule rotation with a user re-login window. Use managed PostgreSQL backups, take a verified backup before migrations, and practice restore. Because the initial migration has no production data downgrade strategy, restore from backup rather than improvising a destructive downgrade.

Compose passes the PostgreSQL host, port, database, user, and password as separate values. The platform uses SQLAlchemy's `URL.create`, so secure passwords containing URI delimiters such as `@:/#` are encoded correctly rather than interpolated into a connection string. Quote such values in `.env` (for example, `POSTGRES_PASSWORD='secure@:/#value'`) so dotenv parsing preserves every character.

Review-only proposal endpoints are unavailable unless `SITE_PROPOSALS_ENABLED=true`. Hosted mode rejects startup if that value is enabled. When locally enabled, Flask signs session-owned proposal IDs with `SITE_SESSION_SECRET`; one browser cannot read or decide another browser's proposal. The API records only bounded, user-supplied metadata and never reads or returns repository file content. Session payload limits are regression-tested below Flask's maximum cookie size.

The Alfred showcase routes are intentionally public and require no account because they have no real adapter or billable provider. They accept only a bounded question string, a fixed scenario ID, or explicit boolean approval/reset fields. Answers come from compiled curated copy and fixed local citation paths. Action results and capped audit entries are synthetic and live only in the signed browser session. The Blueprint includes no Alfred, Ollama, OpenAI-compatible, provider, token, or API-key setting. Do not add credentials, a proxy, a service link, or a firewall path to port 8020.

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

For this Render release, verify the portfolio directly:

```powershell
Invoke-RestMethod https://<render-assigned-service-name>.onrender.com/healthz
```

Replace the origin if Render assigns a suffixed hostname. The broader smoke script remains available when the independently deployed platform and Orbital services also exist. It checks liveness and database readiness but does not create accounts, mutate operational data, or run a simulation.

## GitHub Pages boundary

GitHub Pages can publish the HTML, CSS, JavaScript, images, project pages, and evidence JSON. It cannot run Flask, FastAPI, Gunicorn, Uvicorn, Alembic, health endpoints, Alfred server responses, showcase APIs, environment-driven contact links, or database-backed services. The showcase page explains when its Flask API is unavailable; it does not silently substitute a less controlled workflow. Use the existing Flask deployment path for public interactivity. Run the full Alfred edition only as the documented native loopback service and never expose its action API through a public site.

The GitHub repository is public at the time of this update. The configured branch/tree source URLs have local evidence counterparts so the case studies remain useful if repository visibility or branch names change later.
