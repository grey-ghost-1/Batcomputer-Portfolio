# Batcomputer Portfolio

A neon/HUD portfolio that presents 20 compact Python prototypes without overstating their current scope. Every project page maps to a source folder and documents the exact command, implemented behavior, limitations, and validation status in [`project-evidence.json`](project-evidence.json).

## Architecture

- `app.py` is a small Flask server for the static site, health and inventory APIs, deterministic Alfred responses, and review-only proposal state.
- `batcomputer_console.html`, `style.css`, and `app.js` provide the main HUD.
- The four category HTML files summarize only behavior demonstrated by the paired source.
- `projects/` contains 20 evidence-led project pages.
- `Cybersecurity/`, `IT Support/`, `Network/`, and `Software Automation/` contain the 20 paired Python entry points and project notes.
- `alfred_agent_console.html` and `alfred_agent.js` expose deterministic preview/review controls. Approval records a decision and returns preview content; it never executes commands or writes files.
- `tests/` verifies Flask behavior, route boundaries, Alfred semantics, proposal review behavior, evidence mappings, and local-link integrity.

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
```

CI runs this command without ignored failures.

## Current scope

- The root site is a Flask-served static portfolio, not a production application platform.
- Alfred is a deterministic local helper with predefined responses. It has no language model, retrieval, memory, autonomous tools, or action execution.
- Coding and homepage proposal endpoints are review-only previews held in process memory. Approve/reject calls do not generate or write content.
- Most paired projects are dependency-free learning prototypes. Some read local fixture files, two invoke bounded loopback-friendly ping/TCP checks, and one writes a local SQLite database when explicitly run.
- There is no hosted demo, authentication system, cloud deployment, resume download, email address, or LinkedIn profile configured in this repository.

## Next flagship roadmap

The next flagship is the network inventory prototype. The planned sequence is to add committed sample data and schema validation, isolate SQLite persistence behind a tested service boundary, expose read-only Flask inventory endpoints, add a real inventory view to the HUD, and only then evaluate an authenticated network-data adapter. Each step should land with tests and updated evidence before its capability is advertised.
