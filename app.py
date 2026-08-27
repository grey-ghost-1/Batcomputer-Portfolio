import os
import secrets
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, session

from site_config import public_site_config

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=None)


def _enabled(value):
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _session_secret(environ=None):
    environment = os.environ if environ is None else environ
    configured = environment.get("SITE_SESSION_SECRET", "")
    if configured and (len(configured) < 32 or len(set(configured)) < 8):
        raise RuntimeError(
            "SITE_SESSION_SECRET must contain at least 32 characters with sufficient variety"
        )
    return configured or secrets.token_hex(32)


app.config.update(
    SECRET_KEY=_session_secret(),
    PROPOSALS_ENABLED=_enabled(os.getenv("SITE_PROPOSALS_ENABLED", "false")),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SITE_ENVIRONMENT", "development") == "production",
)

CODE_PROPOSAL_KEY = "code_proposal"
HUD_PROPOSAL_KEY = "hud_proposal"
RECENT_EVENTS_KEY = "proposal_events"
SESSION_TASK_LIMIT = 120
SESSION_PATH_LIMIT = 160
SESSION_CONTEXT_LIMIT = 3
SESSION_CONTEXT_PATH_LIMIT = 100
SESSION_EVENT_LIMIT = 5

CATEGORY_PAGES = {
    "software-development": "software_development.html",
    "cybersecurity": "cybersecurity.html",
    "it-support": "it_support.html",
    "network-software": "network_software.html",
    "alfred-agent": "alfred_agent_console.html",
}
PRIMARY_PROJECTS = (
    "operations-platform",
    "orbital-data-lab",
    "algorithm-quality-lab",
    "alfred-ai-assistant",
)
ROOT_PUBLIC_SUFFIXES = {".html", ".css", ".js"}
ROOT_PUBLIC_FILES = {"project-evidence.json", "ALFRED_STATUS.md"}
ASSET_PUBLIC_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".pdf"}
PROPOSAL_TEXT_SUFFIXES = {".css", ".html", ".js", ".json", ".md", ".py", ".txt", ".yaml", ".yml"}


def truncate_metadata(value, byte_limit):
    encoded = value.encode("utf-8")
    if len(encoded) <= byte_limit:
        return value
    return encoded[:byte_limit].decode("utf-8", errors="ignore")


def record_event(event_type, task="", file_name=""):
    events = list(session.get(RECENT_EVENTS_KEY, []))
    events.append({"type": event_type, "file": truncate_metadata(file_name, 60)})
    session[RECENT_EVENTS_KEY] = events[-SESSION_EVENT_LIMIT:]


def resolve_workspace_path(file_name):
    if not file_name or "\x00" in file_name:
        return None
    candidate = Path(file_name)
    if candidate.is_absolute():
        return None
    path = (BASE_DIR / candidate).resolve()
    try:
        path.relative_to(BASE_DIR)
    except ValueError:
        return None
    return path


def normalize_proposal_path(file_name):
    if not file_name or "\x00" in file_name or "\\" in file_name:
        return None
    candidate = Path(file_name)
    if candidate.is_absolute() or candidate.drive or ".." in candidate.parts:
        return None
    if candidate.suffix.lower() not in PROPOSAL_TEXT_SUFFIXES:
        return None
    return candidate.as_posix()


def project_inventory():
    return sorted(path.stem for path in (BASE_DIR / "projects").glob("*.html"))


def agent_state():
    pending = session.get(CODE_PROPOSAL_KEY)
    return {
        "available": False,
        "proposals_enabled": app.config["PROPOSALS_ENABLED"],
        "model": None,
        "mode": "deterministic-review-only",
        "status": "ready",
        "executes_actions": False,
        "writes_files": False,
        "reads_repository_files": False,
        "pending_code_change": pending if isinstance(pending, dict) else None,
        "recent_events": session.get(RECENT_EVENTS_KEY, []),
    }


def require_proposals(function):
    @wraps(function)
    def protected(*args, **kwargs):
        if not app.config["PROPOSALS_ENABLED"]:
            return jsonify({"error": "Review-only proposals are disabled."}), 404
        return function(*args, **kwargs)

    return protected


def local_reply(message):
    normalized = " ".join(message.lower().split())
    compact = normalized.replace(" ", "")
    if compact in {"hi", "hii", "hiii", "hello", "hey", "hialfred", "helloalfred", "heyalfred"}:
        return "Hello. Alfred's deterministic local helper is ready."
    if "status" in normalized or "health" in normalized:
        return "The Batcomputer Flask server is online. Alfred is a deterministic helper, not an AI model."
    if "what can" in normalized or normalized in {"help", "commands", "capabilities"}:
        return "I can return predefined portfolio guidance. Optional local proposal metadata never reads repository files, generates code, executes actions, or writes files."
    if "who are you" in normalized or "what are you" in normalized:
        return "I am Alfred, a deterministic local portfolio helper with predefined responses. I am not an AI model and do not execute workspace tasks."
    if "website" in normalized or "portfolio" in normalized:
        return "You are viewing Justin Wimmer's Batcomputer portfolio. Use the navigation panel to explore software, cybersecurity, IT support, and network work."
    if "software" in normalized or "automation" in normalized:
        return "The software section covers deterministic text routing, dry-run file planning, local disk metrics, HTML inventory, item validation, and the root Flask HUD."
    if "cyber" in normalized or "security" in normalized:
        return "The cybersecurity section covers bounded TCP checks, failed-login parsing, offline advisory matching, training-hash comparison, and a local reflection check."
    if "network" in normalized:
        return "The network section covers subnet calculation, bounded ping checks, static telemetry summaries, local SQLite inventory, and review-only configuration plans."
    if "it support" in normalized or "troubleshoot" in normalized:
        return "The IT Support section covers supplied-metric classification, disk-space status, bounded DNS and ping checks, messaging fallback simulation, and dry-run log planning."
    return "This deterministic helper can answer predefined questions about the portfolio, software, cybersecurity, IT support, networking, automation, or system status."


@app.get("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "batcomputer-website", "projects": len(project_inventory())})


@app.get("/api/site/summary")
def site_summary():
    return jsonify(
        {
            "categories": CATEGORY_PAGES,
            "projects": project_inventory(),
            "project_count": len(project_inventory()),
            "primary_projects": PRIMARY_PROJECTS,
            "labs_count": len(project_inventory()) - len(PRIMARY_PROJECTS),
            "labs_page": "labs.html",
            "evidence_inventory": "project-evidence.json",
        }
    )


@app.get("/api/site/config")
def site_configuration():
    return jsonify(public_site_config(BASE_DIR))


@app.get("/<path:page>")
def static_page(page):
    if page in CATEGORY_PAGES:
        page = CATEGORY_PAGES[page]
    if page.startswith("projects/") and "." not in Path(page).name:
        page = f"{page}.html"
    if "\\" in page:
        return jsonify({"error": "Page not found."}), 404
    path = resolve_workspace_path(page)
    if path is None or not path.is_file():
        return jsonify({"error": "Page not found."}), 404
    relative = path.relative_to(BASE_DIR)
    is_root_public = len(relative.parts) == 1 and (
        path.suffix.lower() in ROOT_PUBLIC_SUFFIXES or relative.name in ROOT_PUBLIC_FILES
    )
    is_project_page = (
        len(relative.parts) == 2
        and relative.parts[0] == "projects"
        and path.suffix.lower() == ".html"
    )
    is_asset = (
        len(relative.parts) >= 2
        and relative.parts[0] in {"assets", "images"}
        and path.suffix.lower() in ASSET_PUBLIC_SUFFIXES
    )
    if not (is_root_public or is_project_page or is_asset):
        return jsonify({"error": "Page not found."}), 404
    return send_from_directory(BASE_DIR, relative.as_posix())


@app.post("/alfred")
def alfred():
    payload = request.get_json(silent=True) or {}
    raw_message = payload.get("message", "")
    if not isinstance(raw_message, str):
        return jsonify({"error": "Message must be a string."}), 400
    message = raw_message.strip()
    if not message:
        return jsonify({"error": "Message is required."}), 400
    return jsonify(
        {
            "reply": local_reply(message),
            "mode": "deterministic",
            "model": None,
            "executes_actions": False,
        }
    )


@app.get("/api/coding-agent/state")
@require_proposals
def coding_agent_state():
    return jsonify(agent_state())


@app.post("/api/coding-agent/proposals")
@require_proposals
def create_code_proposal():
    payload = request.get_json(silent=True) or {}
    raw_task = payload.get("task", "")
    raw_target_file = payload.get("target_file", "")
    context_files = payload.get("context_files", [])
    if not isinstance(raw_task, str) or not isinstance(raw_target_file, str):
        return jsonify({"error": "Task and target_file must be strings."}), 400
    task = raw_task.strip()
    target_file = raw_target_file.strip()
    if not task or not target_file:
        return jsonify({"error": "Task and target_file are required."}), 400
    if len(task) > 2000 or len(target_file) > 240:
        return jsonify({"error": "Task or target_file is too long."}), 400
    if not isinstance(context_files, list):
        return jsonify({"error": "context_files must be a list."}), 400
    if len(context_files) > 20:
        return jsonify({"error": "No more than 20 context files are allowed."}), 400
    normalized_target = normalize_proposal_path(target_file)
    if normalized_target is None:
        return jsonify({"error": "target_file must be a safe relative text-file path."}), 400
    normalized_context = []
    for item in context_files:
        normalized_item = normalize_proposal_path(item) if isinstance(item, str) else None
        if normalized_item is None or len(item) > 240:
            return jsonify({"error": "Each context file must be a safe relative path."}), 400
        normalized_context.append(normalized_item)
    stored_task = truncate_metadata(task, SESSION_TASK_LIMIT)
    stored_target = truncate_metadata(normalized_target, SESSION_PATH_LIMIT)
    stored_context = [
        truncate_metadata(item, SESSION_CONTEXT_PATH_LIMIT)
        for item in normalized_context[:SESSION_CONTEXT_LIMIT]
    ]
    proposal = {
        "proposal_id": secrets.token_urlsafe(24),
        "task": stored_task,
        "target_file": stored_target,
        "context_files": stored_context,
        "context_file_count": len(normalized_context),
        "metadata_truncated": (
            stored_task != task
            or stored_target != normalized_target
            or len(normalized_context) > SESSION_CONTEXT_LIMIT
            or stored_context != normalized_context
        ),
        "mode": "deterministic-review-only",
        "executes_actions": False,
        "writes_files": False,
        "reads_repository_files": False,
        "plan_steps": [
            "Record the requested target and context file names",
            "Require a separate authenticated development workflow for any source review",
        ],
    }
    session[CODE_PROPOSAL_KEY] = proposal
    record_event("proposal-created", task, normalized_target)
    return jsonify(
        {
            "reply": "Review-only metadata recorded. No repository file was read or returned.",
            "coding_agent": agent_state(),
        }
    )


@app.post("/api/coding-agent/proposals/<proposal_id>/<decision>")
@require_proposals
def decide_code_proposal(proposal_id, decision):
    if decision not in {"approve", "reject"}:
        return jsonify({"error": "Unknown proposal decision."}), 404
    proposal = session.get(CODE_PROPOSAL_KEY)
    if not isinstance(proposal, dict) or not secrets.compare_digest(
        str(proposal.get("proposal_id", "")), proposal_id
    ):
        return jsonify({"error": "Proposal not found for this session."}), 404
    record_event(f"proposal-{decision}d", proposal["task"], proposal["target_file"])
    session.pop(CODE_PROPOSAL_KEY, None)
    return jsonify(
        {
            "reply": f"Review-only proposal {decision}d. No file was read or written and no command was executed.",
            "coding_agent": agent_state(),
        }
    )


@app.get("/api/hud-redesign/state")
@require_proposals
def hud_state():
    proposal = session.get(HUD_PROPOSAL_KEY)
    return jsonify({"pending_hud_redesign": proposal if isinstance(proposal, dict) else None})


@app.post("/api/hud-redesign/proposals")
@require_proposals
def create_hud_proposal():
    payload = request.get_json(silent=True) or {}
    raw_task = payload.get("task", "")
    if not isinstance(raw_task, str):
        return jsonify({"error": "Task must be a string."}), 400
    task = raw_task.strip()
    if not task:
        return jsonify({"error": "Task is required."}), 400
    if len(task) > 2000:
        return jsonify({"error": "Task is too long."}), 400
    target_file = "batcomputer_console.html"
    stored_task = truncate_metadata(task, SESSION_TASK_LIMIT)
    proposal = {
        "proposal_id": secrets.token_urlsafe(24),
        "task": stored_task,
        "target_file": target_file,
        "explanation": "Review-only metadata. No homepage source was read, generated, or returned.",
        "metadata_truncated": stored_task != task,
        "reads_repository_files": False,
        "writes_files": False,
    }
    session[HUD_PROPOSAL_KEY] = proposal
    record_event("hud-proposal-created", task, target_file)
    return jsonify(
        {
            "reply": "Review-only homepage metadata recorded. No repository file was read or returned.",
            "pending_hud_redesign": proposal,
        }
    )


@app.post("/api/hud-redesign/proposals/<proposal_id>/<decision>")
@require_proposals
def decide_hud_proposal(proposal_id, decision):
    if decision not in {"approve", "reject"}:
        return jsonify({"error": "Unknown proposal decision."}), 404
    proposal = session.get(HUD_PROPOSAL_KEY)
    if not isinstance(proposal, dict) or not secrets.compare_digest(
        str(proposal.get("proposal_id", "")), proposal_id
    ):
        return jsonify({"error": "Proposal not found for this session."}), 404
    record_event(f"hud-proposal-{decision}d", proposal["task"], proposal["target_file"])
    session.pop(HUD_PROPOSAL_KEY, None)
    return jsonify(
        {
            "reply": f"Review-only homepage proposal {decision}d. No file was read or written and no command was executed."
        }
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
