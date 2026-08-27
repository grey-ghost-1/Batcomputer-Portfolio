from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=None)

CODE_PROPOSAL = None
HUD_PROPOSAL = None
RECENT_EVENTS = []

CATEGORY_PAGES = {
    "software-development": "software_development.html",
    "cybersecurity": "cybersecurity.html",
    "it-support": "it_support.html",
    "network-software": "network_software.html",
    "alfred-agent": "alfred_agent_console.html",
}
ROOT_PUBLIC_SUFFIXES = {".html", ".css", ".js"}
ROOT_PUBLIC_FILES = {"project-evidence.json"}
ASSET_PUBLIC_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
PREVIEW_TEXT_SUFFIXES = {".css", ".html", ".js", ".json", ".md", ".py", ".txt", ".yaml", ".yml"}


def record_event(event_type, task="", file_name=""):
    RECENT_EVENTS.append({"type": event_type, "task": task, "file": file_name})
    del RECENT_EVENTS[:-20]


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


def read_preview(file_name):
    path = resolve_workspace_path(file_name)
    if path is None or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")[:4000]


def project_inventory():
    return sorted(path.stem for path in (BASE_DIR / "projects").glob("*.html"))


def agent_state():
    return {
        "available": False,
        "model": None,
        "mode": "deterministic-review-only",
        "status": "ready",
        "executes_actions": False,
        "writes_files": False,
        "workspace_root": str(BASE_DIR),
        "pending_code_change": CODE_PROPOSAL,
        "recent_events": RECENT_EVENTS,
    }


def local_reply(message):
    normalized = " ".join(message.lower().split())
    compact = normalized.replace(" ", "")
    if compact in {"hi", "hii", "hiii", "hello", "hey", "hialfred", "helloalfred", "heyalfred"}:
        return "Hello. Alfred's deterministic local helper is ready."
    if "status" in normalized or "health" in normalized:
        return "The Batcomputer Flask server is online. Alfred is a deterministic helper, not an AI model."
    if "what can" in normalized or normalized in {"help", "commands", "capabilities"}:
        return "I can return predefined guidance about this portfolio and create review-only previews. I do not use an AI model, execute actions, or write files."
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
            "evidence_inventory": "project-evidence.json",
        }
    )


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
def coding_agent_state():
    return jsonify(agent_state())


@app.post("/api/coding-agent/proposals")
def create_code_proposal():
    global CODE_PROPOSAL
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
    target_path = resolve_workspace_path(target_file)
    if (
        target_path is None
        or target_path == BASE_DIR
        or target_path.is_dir()
        or target_path.suffix.lower() not in PREVIEW_TEXT_SUFFIXES
    ):
        return jsonify({"error": "target_file must be a safe relative text-file path."}), 400
    normalized_context = []
    for item in context_files:
        if not isinstance(item, str) or len(item) > 240 or resolve_workspace_path(item) is None:
            return jsonify({"error": "Each context file must be a safe relative path."}), 400
        normalized_context.append(item)
    old_preview = read_preview(target_file)
    CODE_PROPOSAL = {
        "task": task,
        "target_file": target_file,
        "context_files": normalized_context,
        "mode": "deterministic-review-only",
        "executes_actions": False,
        "writes_files": False,
        "workspace_root": str(BASE_DIR),
        "plan_steps": [
            "Review the requested target and context file names",
            "Inspect the current target preview without modifying it",
        ],
        "proposal": {
            "old_preview": old_preview,
            "new_preview": old_preview or "No existing file content is available to preview.",
        },
    }
    record_event("proposal-created", task, target_file)
    return jsonify(
        {
            "reply": "Review-only preview created. No code was generated and no file was changed.",
            "coding_agent": agent_state(),
        }
    )


@app.post("/api/coding-agent/proposals/<decision>")
def decide_code_proposal(decision):
    global CODE_PROPOSAL
    if decision not in {"approve", "reject"}:
        return jsonify({"error": "Unknown proposal decision."}), 404
    if CODE_PROPOSAL is None:
        return jsonify({"error": "There is no pending coding proposal."}), 409
    proposal = CODE_PROPOSAL
    record_event(f"proposal-{decision}d", proposal["task"], proposal["target_file"])
    CODE_PROPOSAL = None
    return jsonify(
        {
            "reply": f"Review-only coding preview {decision}d. No file was written and no command was executed.",
            "coding_agent": agent_state(),
        }
    )


@app.get("/api/hud-redesign/state")
def hud_state():
    return jsonify({"pending_hud_redesign": HUD_PROPOSAL})


@app.post("/api/hud-redesign/proposals")
def create_hud_proposal():
    global HUD_PROPOSAL
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
    current_preview = read_preview(target_file)
    HUD_PROPOSAL = {
        "task": task,
        "target_file": target_file,
        "explanation": "A deterministic copy of the current homepage was loaded for review. No redesign was generated.",
        "old_preview": current_preview,
        "new_preview": current_preview,
        "full_content": current_preview,
    }
    record_event("hud-proposal-created", task, target_file)
    return jsonify(
        {
            "reply": "Review-only homepage preview created. No redesign was generated and no file was changed.",
            "pending_hud_redesign": HUD_PROPOSAL,
        }
    )


@app.post("/api/hud-redesign/proposals/<decision>")
def decide_hud_proposal(decision):
    global HUD_PROPOSAL
    if decision not in {"approve", "reject"}:
        return jsonify({"error": "Unknown proposal decision."}), 404
    if HUD_PROPOSAL is None:
        return jsonify({"error": "There is no pending website redesign proposal."}), 409
    proposal = HUD_PROPOSAL
    record_event(f"hud-proposal-{decision}d", proposal["task"], proposal["target_file"])
    HUD_PROPOSAL = None
    response = {
        "reply": f"Review-only homepage preview {decision}d. No file was written and no command was executed."
    }
    if decision == "approve":
        response["final_content"] = proposal["full_content"]
    return jsonify(response)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
