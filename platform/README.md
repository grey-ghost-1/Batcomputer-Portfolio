# Batcomputer Operations Platform

A separate production-style FastAPI flagship. It does not replace or share process state with the root Flask portfolio host.

## Demonstrated behavior

- Typed Pydantic request/response schemas, SQLAlchemy persistence, an Alembic baseline migration, PostgreSQL production configuration, and SQLite development/test support.
- Argon2 password hashing, signed expiring access tokens, server-side admin/operator/viewer RBAC, and workspace filters on every domain read and mutation.
- Shared assets and work items cover software automation, defensive cybersecurity, IT support, data engineering/analytics, cloud/network platform, and quality engineering.
- Asset and work-item CRUD, guarded workflow transitions, filters, bounded pagination, validation envelopes, OpenAPI, liveness/readiness, correlation IDs, JSON request logs, and append-only audit records.
- Alfred reports `unavailable` or `configured`; it stores approval-pending intents with `executed=false`. No generation, provider call, approval, or execution path exists.
- The `/` operator UI supports workspace registration/login, asset/work-item creation, workflow start, and Alfred intent recording.

## Local SQLite

From the repository root:

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
Set-Location platform
python -m alembic -c alembic.ini upgrade head
python -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. OpenAPI is at `/docs`.

## PostgreSQL containers

```powershell
$env:PLATFORM_SECRET_KEY = "replace-with-a-unique-random-secret-at-least-32-characters"
$env:POSTGRES_PASSWORD = "replace-with-a-unique-database-password"
docker compose up --build
```

For a production deployment, set `PLATFORM_ENVIRONMENT=production`, use external secret injection, terminate TLS at a trusted ingress, restrict allowed origins, run migration as a release step, retain PostgreSQL backups, and ship structured stdout logs to centralized storage. Production startup rejects the documented development secret and non-PostgreSQL database URLs.

Compose supplies database host, port, name, user, and password separately. SQLAlchemy assembles and percent-encodes the URL, so passwords containing URI delimiters such as `@:/#` are supported; quote special values in `.env`.

Provider connection strings beginning with `postgresql://` are normalized to the installed Psycopg 3 driver. Before each migration, verify a restorable managed-database backup. Rotate `PLATFORM_SECRET_KEY` through the provider's secret store; rotation intentionally invalidates outstanding access tokens and requires users to sign in again. Never place the key or database URL in an image, build argument, log, or committed `.env` file. The current root [`DEPLOYMENT.md`](../DEPLOYMENT.md) and Render Blueprint deploy only the Flask portfolio; this platform requires a separately reviewed release. Its health checks remain covered by the broader local smoke command.

## Verification

```powershell
Set-Location platform
$env:PLATFORM_ENVIRONMENT = "test"
$env:PLATFORM_DATABASE_URL = "sqlite:///./migration-check.db"
python -m alembic -c alembic.ini upgrade head
python -m pytest tests -q
Set-Location ..
python -m ruff check platform
```

## Architecture and limits

HTTP handlers apply authentication, role checks, and tenant scoping before SQLAlchemy access. Mutations write their audit event in the same transaction. The initial deployment is a modular monolith so authorization and audit rules remain visible and testable; PostgreSQL can later support independent workers without inventing distributed boundaries now.

The service does not provide password reset, refresh tokens, MFA, SSO, audit export/retention jobs, rate limiting, background execution, object storage, external integrations, or a hosted deployment. Access tokens cannot be revoked before expiry. Those are explicit deployment backlog items, not current claims.
