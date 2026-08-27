"""Bounded data and deterministic behavior for the public Alfred showcase."""

from __future__ import annotations

from dataclasses import dataclass

MAX_QUESTION_LENGTH = 400
MAX_AUDIT_ENTRIES = 6


@dataclass(frozen=True)
class Citation:
    label: str
    href: str


EVIDENCE = {
    "case-study": Citation(
        "Alfred case study",
        "projects/alfred-ai-assistant.html",
    ),
    "status": Citation(
        "Alfred implementation status and threat model",
        "ALFRED_STATUS.md",
    ),
    "inventory": Citation(
        "Project evidence inventory",
        "project-evidence.json",
    ),
}

SUGGESTED_QUESTIONS = (
    "Which projects best demonstrate backend engineering?",
    "How does Alfred keep desktop actions safe?",
    "How was Alfred tested?",
    "What can the full local edition do?",
)

ANSWERS = {
    "backend": {
        "terms": ("backend", "api", "fastapi", "database", "sqlalchemy", "postgres"),
        "answer": (
            "A sensible place to begin is the Operations Platform: it demonstrates typed FastAPI "
            "endpoints, relational modeling, migrations, authentication, tenant isolation, guarded "
            "workflows, and immutable audit events. Orbital Data Lab adds deterministic numerical "
            "APIs and content-addressed SQLite storage, while Alfred shows policy boundaries around "
            "local providers and desktop adapters."
        ),
        "citations": ("inventory",),
    },
    "safety": {
        "terms": ("safe", "safety", "approve", "approval", "desktop", "action", "security"),
        "answer": (
            "The local edition separates conversation from typed actions. Every real desktop effect "
            "must be proposed, shown as an exact preview, explicitly approved for that single payload, "
            "revalidated, executed once, and audited. This hosted showcase preserves the workflow but "
            "permanently replaces every adapter with a simulation over fixed sample data."
        ),
        "citations": ("case-study", "status"),
    },
    "testing": {
        "terms": ("test", "tested", "quality", "ci", "validation"),
        "answer": (
            "Alfred's dedicated suite covers API contracts, provider failures, citations, prompt "
            "injection, SSRF controls, redaction, path confinement, ownership, expiry, tampering, "
            "replay, disabled execution, allowlists, and temporary-directory-only mutations. The "
            "public showcase adds route, state-isolation, approval, simulated-audit, XSS, accessibility, "
            "link, and no-real-adapter checks."
        ),
        "citations": ("case-study", "inventory"),
    },
    "local": {
        "terms": ("local", "ollama", "model", "full edition", "full version", "provider"),
        "answer": (
            "The full edition is a separate loopback-only FastAPI service for a trusted Windows user. "
            "It can optionally use Ollama or a deliberately configured compatible model and can enable "
            "narrow, approval-gated desktop adapters. Neither the model boundary nor those adapters is "
            "connected to this public site; this demonstration is deterministic and non-executing."
        ),
        "citations": ("case-study", "status"),
    },
    "portfolio": {
        "terms": ("portfolio", "project", "work", "recruiter", "stack", "technology"),
        "answer": (
            "The portfolio's four primary case studies cover a tenant-isolated operations platform, "
            "a deterministic orbital simulation service, an algorithms and quality lab, and Alfred's "
            "local-first assistant architecture. Together they provide evidence across Python APIs, "
            "data modeling, browser interfaces, security boundaries, numerical work, and automated tests."
        ),
        "citations": ("inventory",),
    },
}

SCENARIOS = {
    "create-project-folder": {
        "title": "Create a project folder",
        "summary": "Simulate creating one folder inside a synthetic demo workspace.",
        "action_type": "create_folder",
        "preview": {
            "scope": "Synthetic workspace only",
            "before": ["Demo Workspace/", "Demo Workspace/notes.txt"],
            "changes": ["CREATE Demo Workspace/Recruiter Brief/"],
            "after": [
                "Demo Workspace/",
                "Demo Workspace/notes.txt",
                "Demo Workspace/Recruiter Brief/",
            ],
        },
        "result": "Simulation complete: Recruiter Brief/ was added to the sample tree.",
    },
    "organize-sample-downloads": {
        "title": "Organize sample downloads",
        "summary": "Simulate sorting three invented files by extension.",
        "action_type": "organize_files",
        "preview": {
            "scope": "Three synthetic filenames only",
            "before": ["Downloads/demo.pdf", "Downloads/diagram.png", "Downloads/notes.txt"],
            "changes": [
                "MOVE Downloads/demo.pdf -> Downloads/Documents/demo.pdf",
                "MOVE Downloads/diagram.png -> Downloads/Images/diagram.png",
                "MOVE Downloads/notes.txt -> Downloads/Documents/notes.txt",
            ],
            "after": [
                "Downloads/Documents/demo.pdf",
                "Downloads/Documents/notes.txt",
                "Downloads/Images/diagram.png",
            ],
        },
        "result": "Simulation complete: three sample files were organized in memory.",
    },
    "open-approved-docs": {
        "title": "Open approved documentation",
        "summary": "Simulate opening one fixed, reviewed HTTPS documentation URL.",
        "action_type": "open_url",
        "preview": {
            "scope": "Fixed showcase allowlist",
            "before": ["No simulated browser tab"],
            "changes": ["OPEN https://docs.ollama.com/"],
            "after": ["Simulated tab: Ollama documentation"],
        },
        "result": (
            "Simulation complete: the approved documentation URL was recorded as opened. "
            "No browser navigation or network request occurred."
        ),
    },
}


def answer_question(question: str) -> dict:
    normalized = " ".join(question.lower().split())
    selected = max(
        ANSWERS.values(),
        key=lambda item: sum(term in normalized for term in item["terms"]),
    )
    if not any(term in normalized for term in selected["terms"]):
        selected = {
            "answer": (
                "I should not improvise beyond the evidence prepared for this demonstration. "
                "Please choose one of the suggested portfolio, testing, safety, or local-edition questions."
            ),
            "citations": ("case-study", "inventory"),
        }
    return {
        "answer": selected["answer"],
        "citations": [
            {"label": EVIDENCE[key].label, "href": EVIDENCE[key].href}
            for key in selected["citations"]
        ],
        "mode": "curated-deterministic",
        "model": None,
        "network_used": False,
    }


def public_scenarios() -> list[dict]:
    return [
        {
            "id": scenario_id,
            "title": scenario["title"],
            "summary": scenario["summary"],
        }
        for scenario_id, scenario in SCENARIOS.items()
    ]

