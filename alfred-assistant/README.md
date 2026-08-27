# Alfred Assistant

A local-first, typed FastAPI household-manager service. It can hold broad,
general-purpose conversations through an explicitly configured Ollama or
OpenAI-compatible model, answer from this repository's curated evidence,
optionally research the public web, and prepare a small set of typed
desktop actions -- but **every desktop action requires its own explicit
preview, approval, and execution step.** Nothing runs automatically.

Alfred is an original persona (a discreet, precise, dry-witted British
household manager). It does not reproduce dialogue, catchphrases, or
characterization from any copyrighted work.

## Safety boundaries (read this first)

- **Native Windows process only.** There is no Docker image, no container,
  and no public/hosted deployment path for this service. It is intentionally
  excluded from this repository's `Dockerfile`, `docker-compose.yml`, and
  Render blueprint.
- **Loopback only.** The service refuses to start if configured to bind
  anywhere but `127.0.0.0/8`, `::1`, or `localhost`. There is no supported way
  to expose it on a LAN or the public internet.
- **No startup persistence.** `start.ps1` runs Alfred in the foreground of
  the terminal you launch it from. It does not create a scheduled task, a
  registry Run key, a Windows service, or a startup shortcut. Closing the
  terminal (or `Ctrl+C`) stops it completely; nothing is left running.
- **Desktop actions are disabled by default.** Creating a folder, moving a
  file, organizing a folder, launching an allow-listed application, opening
  an allow-listed HTTPS URL, or writing the clipboard all require
  `ALFRED_DESKTOP_ACTIONS_ENABLED=true` to even be *executable* -- and even
  then, **every single action still requires its own propose -> preview ->
  approve -> execute round trip**, scoped to one authenticated user/session,
  with a short expiry, a canonical payload hash re-checked at every step, and
  an immutable audit trail. There is no "auto-approve", no batch approval,
  and no way for the model to trigger an action on its own.
- **Optional integrations are off unless you turn them on.** No local model
  is called unless you configure Ollama or an OpenAI-compatible endpoint. No
  web request is ever made unless you set `ALFRED_WEB_RESEARCH_ENABLED=true`.
- **General chat does not grant tools.** Ordinary safe questions reach the
  configured model even when they do not match a portfolio keyword. Requests
  to bypass approvals, execute arbitrary commands, destroy data, steal
  credentials, or create malware are refused before model or web use.

See [`ALFRED_STATUS.md`](../ALFRED_STATUS.md) at the repository root for the
full implementation checklist and threat model.

## Requirements

- Windows, with PowerShell 5.1 or later (PowerShell 7/`pwsh` also works).
- Python 3.11 or newer.
- (Optional) [Ollama](https://ollama.com) installed locally, or any other
  OpenAI-compatible server (LM Studio, llama.cpp, vLLM, ...) for model-assisted
  answers.
- (Optional) A [Brave Search API](https://brave.com/search/api/) key for
  broader web research; the keyless Wikipedia source works without one.

## Setup

Run these from the **repository root** (not this folder) the first time:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Then, from this folder (`alfred-assistant\`), create your local configuration
and an action token. **Never commit a real token or a real `.env` file** --
`.env` is already covered by the repository's root `.gitignore`.

```powershell
Set-Location alfred-assistant
Copy-Item .env.example .env

# Generate a high-entropy token yourself; do not reuse this example.
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Paste the printed value into `.env` as `ALFRED_ACTION_TOKEN=...`. This token
is required before any typed action or system-inspection endpoint will
authenticate; without it, those endpoints honestly report
`503 action token is not configured on the server` and only chat/research
remain reachable.

## Running

From this folder:

```powershell
.\start.ps1
```

`start.ps1`:

- Resolves its own folder, so it works whether you `Set-Location
  alfred-assistant` first or invoke it as `.\alfred-assistant\start.ps1`.
- Copies `.env.example` to `.env` on first run only, if `.env` is missing.
- Validates the effective bind host is a loopback address **before** Python
  is even started, and refuses to continue otherwise.
- Runs `python -m uvicorn alfred.main:app` bound to `127.0.0.1:8020` by
  default, in the foreground -- no background job, no persistence.

Optional parameters:

```powershell
.\start.ps1 -Port 8111          # a different loopback port
.\start.ps1 -BindHost "::1"     # bind IPv6 loopback instead
```

Once it is running, open **http://127.0.0.1:8020/** in a browser for the
built-in console (chat, action builder, live audit timeline), or call the API
directly:

```powershell
Invoke-RestMethod http://127.0.0.1:8020/health/live
Invoke-RestMethod http://127.0.0.1:8020/api/capabilities
```

Paste your token into the console's "Local action token" field (kept only in
that browser tab's `sessionStorage`, never persisted) before using system
inspection or the action builder.

To run it manually instead of via `start.ps1` (equivalent, without the
loopback pre-check):

```powershell
python -m uvicorn alfred.main:app --host 127.0.0.1 --port 8020
```

## Configuration reference

All settings are environment variables with the `ALFRED_` prefix, loaded from
`alfred-assistant\.env`. See [`.env.example`](.env.example) for the full,
commented list, including:

| Area | Key settings | Default |
|---|---|---|
| Networking | `ALFRED_HOST`, `ALFRED_PORT` | `127.0.0.1`, `8020` (non-loopback rejected) |
| Action auth | `ALFRED_ACTION_TOKEN` | unset (actions unavailable until set) |
| Desktop actions | `ALFRED_DESKTOP_ACTIONS_ENABLED`, `ALFRED_CLIPBOARD_ENABLED` | `false`, `false` |
| Filesystem allow-lists | `ALFRED_APPROVED_ROOTS`, `ALFRED_ALLOWED_EXECUTABLES`, `ALFRED_ALLOWED_URL_HOSTS` | all empty |
| Local model (optional) | `ALFRED_MODEL_PROVIDER` = `none`\|`ollama`\|`openai` | `none` (explicitly non-AI deterministic fallback) |
| Web research (optional) | `ALFRED_WEB_RESEARCH_ENABLED`, `ALFRED_WEB_SEARCH_PROVIDER`, `ALFRED_BRAVE_API_KEY` | `false`, `none`, unset |

Every filesystem action is confined to the resolved, real paths under
`ALFRED_APPROVED_ROOTS` -- absolute paths, UNC/device paths, `..` traversal,
and symlink/reparse escapes are all rejected. `open_app`/`open_url` only ever
launch an exact entry from `ALFRED_ALLOWED_EXECUTABLES`/`ALFRED_ALLOWED_URL_HOSTS`
(HTTPS, standard port, no embedded credentials).

For local Ollama general chat, install and start Ollama separately, make sure
the chosen model is present, then set values such as these in the ignored
`.env`:

```dotenv
ALFRED_MODEL_PROVIDER=ollama
ALFRED_OLLAMA_URL=http://127.0.0.1:11434
ALFRED_OLLAMA_MODEL=llama3.1:latest
```

Those are supported configuration examples, not a claim that Ollama is
installed or enabled on every machine. `/api/status` reports what is configured,
and each `/api/chat` response reports `provider.model_used`; a timeout or
unavailable provider is labeled and falls back deterministically.

## What Alfred is not

- Not a general browser, crawler, or arbitrary URL fetcher -- web research
  (when enabled) only ever calls a fixed Wikipedia API and, if configured, the
  Brave Search API, both through an SSRF-hardened fetch layer.
- Not a shell, script runner, or general automation tool -- there is no "run
  a command" action; the only typed actions are folder creation, single
  file move/rename, extension-based organizing, launching one allow-listed
  application with no arguments, opening one allow-listed HTTPS URL, and
  optionally writing the clipboard.
- Not a secrets/process inspector -- system inspection is read-only, returns
  metadata only (never file contents), and process command-line arguments
  are never collected at all (not merely redacted after the fact).
- Not an autonomous agent -- the model (if configured) can only compose an
  answer; it cannot see or trigger the action lifecycle, and any reply that
  violates the persona's safety policy (e.g. claiming to be human, claiming
  to have already executed something, or claiming web access that was not
  actually used) is discarded in favor of a deterministic, honest fallback.

## Development

Run from the **repository root**, with the virtual environment above active:

```powershell
python -m pytest alfred-assistant/tests -q
python -m ruff check alfred-assistant
python -m compileall -q alfred-assistant
node --check alfred-assistant/ui/console.js
python -m mypy --check-untyped-defs alfred-assistant/alfred
```

The test suite never calls a live network endpoint (HTTP is always exercised
through an injected `httpx.MockTransport` or a stub DNS resolver) and never
launches a real process, browser, or clipboard write (a recording launcher
double is injected instead); filesystem mutations are confined to pytest's
own temporary directories.

`alfred-assistant/alfred.db` and `__pycache__/` directories are local,
generated artifacts -- they are covered by the repository root
`.gitignore` (`*.db`, `__pycache__/`) and must never be committed.
