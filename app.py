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


def record_event(event_type, task="", file_name=""):
    RECENT_EVENTS.append({"type": event_type, "task": task, "file": file_name})
    del RECENT_EVENTS[:-20]


def read_preview(file_name):
    path = (BASE_DIR / file_name).resolve()
    if BASE_DIR not in path.parents or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")[:4000]


def project_inventory():
    return sorted(path.stem for path in (BASE_DIR / "projects").glob("*.html"))


def agent_state():
    return {
        "available": True,
        "model": "local-demo",
        "host": "Flask server",
        "workspace_root": str(BASE_DIR),
        "pending_code_change": CODE_PROPOSAL,
        "recent_events": RECENT_EVENTS,
    }


def local_reply(message):
    normalized = " ".join(message.lower().split())
    compact = normalized.replace(" ", "")
    if compact in {"hi", "hii", "hiii", "hello", "hey", "hialfred", "helloalfred", "heyalfred"}:
        return "Hello. Alfred is online and ready to help."
    if "status" in normalized or "health" in normalized:
        return "All systems nominal, sir. The Batcomputer Flask server is online."
    if "what can" in normalized or normalized in {"help", "commands", "capabilities"}:
        return "I can discuss software, cybersecurity, IT support, networking, automation, and this portfolio. I can also guide you to the Coding Agent for approved workspace changes."
    if "who are you" in normalized or "what are you" in normalized:
        return "I am Alfred, the Batcomputer assistant. I help with technical questions, system guidance, and approved workspace tasks."
    if "website" in normalized or "portfolio" in normalized:
        return "You are viewing Justin Wimmer's Batcomputer portfolio. Use the navigation panel to explore software, cybersecurity, IT support, and network work."
    if "software" in normalized or "automation" in normalized:
        return "The software and automation section covers Python, Flask, local assistant workflows, dashboards, and repeatable tools for technical work."
    if "cyber" in normalized or "security" in normalized:
        return "The cybersecurity section covers defensive workflows, approval gates, state boundaries, vulnerability assessment, and authorized lab tooling."
    if "network" in normalized:
        return "The network section covers diagnostics, monitoring, inventory, subnetting, and infrastructure automation."
    if "it support" in normalized or "troubleshoot" in normalized:
        return "The IT Support section focuses on diagnostics, system health, launcher reliability, and practical troubleshooting workflows."
    return "I am ready to help. Ask me about the portfolio, software, cybersecurity, IT support, networking, automation, or system status."


@app.get("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "batcomputer-website", "projects": len(project_inventory())})


@app.get("/api/site/summary")
def site_summary():
    return jsonify({"categories": CATEGORY_PAGES, "projects": project_inventory()})


@app.get("/<path:page>")
def static_page(page):
    if page in CATEGORY_PAGES:
        page = CATEGORY_PAGES[page]
    if page.startswith("projects/") and "." not in Path(page).name:
        page = f"{page}.html"
    path = (BASE_DIR / page).resolve()
    if BASE_DIR not in path.parents or not path.is_file():
        return jsonify({"error": "Page not found."}), 404
    if path.suffix in {".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
        return send_from_directory(BASE_DIR, page)
    return send_from_directory(BASE_DIR, page)


@app.post("/alfred")
def alfred():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    if not message:
        return jsonify({"error": "Message is required."}), 400
    return jsonify({"reply": local_reply(message)})


@app.get("/api/coding-agent/state")
def coding_agent_state():
    return jsonify(agent_state())


@app.post("/api/coding-agent/proposals")
def create_code_proposal():
    global CODE_PROPOSAL
    payload = request.get_json(silent=True) or {}
    task = str(payload.get("task", "")).strip()
    target_file = str(payload.get("target_file", "")).strip()
    context_files = payload.get("context_files", [])
    if not task or not target_file:
        return jsonify({"error": "Task and target_file are required."}), 400
    if len(task) > 2000 or len(target_file) > 240:
        return jsonify({"error": "Task or target_file is too long."}), 400
    if not isinstance(context_files, list):
        context_files = []
    old_preview = read_preview(target_file)
    CODE_PROPOSAL = {
        "task": task,
        "target_file": target_file,
        "context_files": [str(item) for item in context_files],
        "model": "local-demo",
        "workspace_root": str(BASE_DIR),
        "plan_steps": ["Review the requested target and context files", "Prepare a proposed change for explicit approval"],
        "proposal": {
            "old_preview": old_preview,
            "new_preview": old_preview or "New file content will be prepared here.",
        },
    }
    record_event("proposal-created", task, target_file)
    return jsonify({"reply": "Coding proposal ready for review.", "coding_agent": agent_state()})


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
    return jsonify({"reply": f"Coding proposal {decision}d.", "coding_agent": agent_state()})


@app.get("/api/hud-redesign/state")
def hud_state():
    return jsonify({"pending_hud_redesign": HUD_PROPOSAL})


@app.post("/api/hud-redesign/proposals")
def create_hud_proposal():
    global HUD_PROPOSAL
    payload = request.get_json(silent=True) or {}
    task = str(payload.get("task", "")).strip()
    if not task:
        return jsonify({"error": "Task is required."}), 400
    target_file = "batcomputer_console.html"
    HUD_PROPOSAL = {
        "task": task,
        "target_file": target_file,
        "explanation": "A local preview proposal was created for explicit review.",
        "old_preview": read_preview(target_file),
        "new_preview": read_preview(target_file),
        "full_content": read_preview(target_file),
    }
    record_event("hud-proposal-created", task, target_file)
    return jsonify({"reply": "Website redesign proposal ready for review.", "pending_hud_redesign": HUD_PROPOSAL})


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
    response = {"reply": f"Website redesign proposal {decision}d."}
    if decision == "approve":
        response["final_content"] = proposal["full_content"]
    return jsonify(response)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
