const agentStatusElement = document.getElementById("agentStatus");
const proposalStateElement = document.getElementById("proposalState");
const agentEventsElement = document.getElementById("agentEvents");
const proposalForm = document.getElementById("proposalForm");
const taskInput = document.getElementById("taskInput");
const targetFileInput = document.getElementById("targetFileInput");
const contextFilesInput = document.getElementById("contextFilesInput");
const refreshAgentStateButton = document.getElementById("refreshAgentState");
const approveProposalButton = document.getElementById("approveProposal");
const rejectProposalButton = document.getElementById("rejectProposal");
const hudProposalForm = document.getElementById("hudProposalForm");
const hudTaskInput = document.getElementById("hudTaskInput");
const refreshHudStateButton = document.getElementById("refreshHudState");
const hudProposalStateElement = document.getElementById("hudProposalState");
const approveHudProposalButton = document.getElementById("approveHudProposal");
const rejectHudProposalButton = document.getElementById("rejectHudProposal");
let codeProposalId = null;
let hudProposalId = null;

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function setStatusMessage(message, isError = false) {
    agentStatusElement.innerHTML = `<p class="${isError ? "agent-error" : "agent-note"}">${escapeHtml(message)}</p>`;
}

function renderEvents(events) {
    if (!Array.isArray(events) || !events.length) {
        agentEventsElement.innerHTML = '<div class="agent-empty">No recent agent events.</div>';
        return;
    }

    const items = events
        .slice()
        .reverse()
        .map((event) => {
            const type = escapeHtml(event.type || "event");
            const task = escapeHtml(event.task || "");
            const file = escapeHtml(event.file || "");
            return `<li><strong>${type}</strong>${task ? ` — ${task}` : ""}${file ? ` <span class="agent-meta">(${file})</span>` : ""}</li>`;
        })
        .join("");
    agentEventsElement.innerHTML = `<ul class="panel-list">${items}</ul>`;
}

function renderPendingProposal(pendingChange) {
    const hasPending = pendingChange && typeof pendingChange === "object";
    codeProposalId = hasPending ? pendingChange.proposal_id : null;
    approveProposalButton.disabled = !hasPending;
    rejectProposalButton.disabled = !hasPending;

    if (!hasPending) {
        proposalStateElement.innerHTML = '<div class="agent-empty">No pending review.</div>';
        return;
    }

    const planSteps = Array.isArray(pendingChange.plan_steps) ? pendingChange.plan_steps : [];
    const contextFiles = Array.isArray(pendingChange.context_files) ? pendingChange.context_files : [];
    const omittedContextCount = Math.max(
        0,
        Number(pendingChange.context_file_count || contextFiles.length) - contextFiles.length
    );
    proposalStateElement.innerHTML = `
        <div class="agent-proposal">
            <p><strong>Proposal ID:</strong> ${escapeHtml(pendingChange.proposal_id || "")}</p>
            <p><strong>Task:</strong> ${escapeHtml(pendingChange.task || "")}</p>
            <p><strong>Target file:</strong> ${escapeHtml(pendingChange.target_file || "")}</p>
            <p><strong>Mode:</strong> ${escapeHtml(pendingChange.mode || "deterministic-review-only")}</p>
            <p><strong>Boundary:</strong> Metadata only; no repository reads, commands, or file writes.</p>
            <div class="agent-split">
                <div>
                    <h3>Plan</h3>
                    <ul class="panel-list">
                        ${planSteps.map((step) => `<li>${escapeHtml(step)}</li>`).join("") || "<li>No plan steps returned.</li>"}
                    </ul>
                </div>
                <div>
                    <h3>Context</h3>
                    <ul class="panel-list">
                        ${contextFiles.map((file) => `<li>${escapeHtml(file)}</li>`).join("") || "<li>No context files.</li>"}
                        ${omittedContextCount ? `<li>${omittedContextCount} additional path(s) not retained in the session cookie.</li>` : ""}
                    </ul>
                </div>
            </div>
        </div>
    `;
}

function renderHudProposal(pendingProposal) {
    const hasPending = pendingProposal && typeof pendingProposal === "object";
    hudProposalId = hasPending ? pendingProposal.proposal_id : null;
    approveHudProposalButton.disabled = !hasPending;
    rejectHudProposalButton.disabled = !hasPending;

    if (!hasPending) {
        hudProposalStateElement.innerHTML = '<div class="agent-empty">No pending homepage review.</div>';
        return;
    }

    hudProposalStateElement.innerHTML = `
        <div class="agent-proposal">
            <p><strong>Proposal ID:</strong> ${escapeHtml(pendingProposal.proposal_id || "")}</p>
            <p><strong>Explanation:</strong> ${escapeHtml(pendingProposal.explanation || "")}</p>
            <p><strong>Target file:</strong> ${escapeHtml(pendingProposal.target_file || "")}</p>
        </div>
    `;
}

function renderState(state) {
    const message = state.status === "ready"
        ? "Local review metadata utility ready. No repository reads, AI model, command execution, or file writes are available."
        : "Deterministic review utility is unavailable.";
    setStatusMessage(message, state.status !== "ready");
    renderPendingProposal(state.pending_code_change);
    renderEvents(state.recent_events);
}

async function loadAgentState() {
    const response = await fetch("/api/coding-agent/state");
    if (!response.ok) {
        throw new Error("Unable to load coding agent state.");
    }
    const state = await response.json();
    renderState(state);
}

async function loadHudState() {
    const response = await fetch("/api/hud-redesign/state");
    if (!response.ok) {
        throw new Error("Unable to load website redesign state.");
    }
    const state = await response.json();
    renderHudProposal(state.pending_hud_redesign);
    return state;
}

function parseContextFiles(value) {
    return value
        .split(",")
        .map((item) => item.trim())
        .filter((item) => item.length > 0);
}

async function createProposal(event) {
    event.preventDefault();
    setStatusMessage("Recording session-owned review metadata…");

    const response = await fetch("/api/coding-agent/proposals", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            task: taskInput.value.trim(),
            target_file: targetFileInput.value.trim(),
            context_files: parseContextFiles(contextFilesInput.value),
        }),
    });
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.error || "Unable to record review metadata.");
    }
    setStatusMessage(payload.reply || "Review metadata ready.");
    renderState(payload.coding_agent || payload);
}

async function decideProposal(url, successMessage) {
    const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
    });
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.reply || payload.error || "Unable to update proposal.");
    }
    setStatusMessage(payload.reply || successMessage);
    renderState(payload.coding_agent || payload);
}

async function createHudProposal(event) {
    event.preventDefault();
    setStatusMessage("Recording session-owned homepage review metadata…");
    const response = await fetch("/api/hud-redesign/proposals", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            task: hudTaskInput.value.trim(),
        }),
    });
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.error || "Unable to record the homepage review.");
    }
    setStatusMessage(payload.reply || "Homepage review metadata ready.");
    renderHudProposal(payload.pending_hud_redesign || payload.proposal);
}

async function decideHudProposal(url, successMessage) {
    const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
    });
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.error || payload.reply || "Unable to update the homepage review.");
    }
    setStatusMessage(payload.reply || successMessage);
    return payload;
}

proposalForm.addEventListener("submit", (event) => {
    createProposal(event).catch((error) => {
        setStatusMessage(error.message, true);
    });
});

refreshAgentStateButton.addEventListener("click", () => {
    loadAgentState().catch((error) => {
        setStatusMessage(error.message, true);
    });
});

approveProposalButton.addEventListener("click", () => {
    decideProposal(`/api/coding-agent/proposals/${encodeURIComponent(codeProposalId)}/approve`, "Approval recorded; no file was read or written.").catch((error) => {
        setStatusMessage(error.message, true);
    });
});

rejectProposalButton.addEventListener("click", () => {
    decideProposal(`/api/coding-agent/proposals/${encodeURIComponent(codeProposalId)}/reject`, "Rejection recorded; no file was read or written.").catch((error) => {
        setStatusMessage(error.message, true);
    });
});

hudProposalForm.addEventListener("submit", (event) => {
    createHudProposal(event).catch((error) => {
        setStatusMessage(error.message, true);
    });
});

refreshHudStateButton.addEventListener("click", () => {
    loadHudState().catch((error) => {
        setStatusMessage(error.message, true);
    });
});

approveHudProposalButton.addEventListener("click", () => {
    decideHudProposal(`/api/hud-redesign/proposals/${encodeURIComponent(hudProposalId)}/approve`, "Homepage review approved; no file was read or written.")
        .then(() => {
            renderHudProposal(null);
        })
        .catch((error) => {
            setStatusMessage(error.message, true);
        });
});

rejectHudProposalButton.addEventListener("click", () => {
    decideHudProposal(`/api/hud-redesign/proposals/${encodeURIComponent(hudProposalId)}/reject`, "Homepage review rejected; no file was read or written.")
        .then(() => {
            renderHudProposal(null);
        })
        .catch((error) => {
            setStatusMessage(error.message, true);
        });
});

loadAgentState().catch((error) => {
    setStatusMessage(error.message, true);
});

loadHudState().catch((error) => {
    setStatusMessage(error.message, true);
});
