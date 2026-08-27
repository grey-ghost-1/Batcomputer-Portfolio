"use strict";

const apiBase = "/api/alfred-showcase";
const suggestionContainer = document.getElementById("showcase-suggestions");
const questionForm = document.getElementById("showcase-question-form");
const questionInput = document.getElementById("showcase-question");
const answerContainer = document.getElementById("showcase-answer");
const citationContainer = document.getElementById("showcase-citations");
const scenarioSelect = document.getElementById("showcase-scenario");
const proposeButton = document.getElementById("showcase-propose");
const previewContainer = document.getElementById("showcase-preview");
const approvalControls = document.getElementById("showcase-approval-controls");
const confirmationInput = document.getElementById("showcase-confirm");
const approveButton = document.getElementById("showcase-approve");
const rejectButton = document.getElementById("showcase-reject");
const resultContainer = document.getElementById("showcase-result");
const auditContainer = document.getElementById("showcase-audit");
const resetButton = document.getElementById("showcase-reset");

let pendingProposalId = null;

function clearNode(node) {
    node.replaceChildren();
}

function appendTextElement(parent, tagName, text, className = "") {
    const element = document.createElement(tagName);
    element.textContent = text;
    if (className) {
        element.className = className;
    }
    parent.appendChild(element);
    return element;
}

async function apiRequest(path, options = {}) {
    const response = await fetch(`${apiBase}${path}`, {
        ...options,
        headers: {
            Accept: "application/json",
            ...(options.body ? { "Content-Type": "application/json" } : {}),
        },
    });
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.error || "The controlled demonstration could not complete that request.");
    }
    return payload;
}

function renderCitations(citations) {
    clearNode(citationContainer);
    if (!Array.isArray(citations) || citations.length === 0) {
        return;
    }
    appendTextElement(citationContainer, "h3", "Evidence cited");
    const list = document.createElement("ol");
    citations.forEach((citation) => {
        const item = document.createElement("li");
        const link = document.createElement("a");
        link.href = citation.href;
        link.textContent = citation.label;
        item.appendChild(link);
        list.appendChild(item);
    });
    citationContainer.appendChild(list);
}

function renderAnswer(payload) {
    clearNode(answerContainer);
    appendTextElement(answerContainer, "p", payload.answer);
    appendTextElement(
        answerContainer,
        "p",
        "Source mode: curated deterministic evidence · Model: none · Network tools: not used",
        "answer-provenance",
    );
    renderCitations(payload.citations);
}

function renderPreview(proposal) {
    clearNode(previewContainer);
    appendTextElement(previewContainer, "h3", proposal.title);
    appendTextElement(previewContainer, "p", `Scope: ${proposal.preview.scope}`);
    for (const [label, values] of [
        ["Before", proposal.preview.before],
        ["Exact simulated change", proposal.preview.changes],
        ["After", proposal.preview.after],
    ]) {
        appendTextElement(previewContainer, "h4", label);
        const list = document.createElement("ul");
        values.forEach((value) => appendTextElement(list, "li", value));
        previewContainer.appendChild(list);
    }
    appendTextElement(
        previewContainer,
        "p",
        "Execution boundary: synthetic in-memory/sample data only; no desktop adapter is present.",
        "preview-boundary",
    );
}

function renderAudit(entries) {
    clearNode(auditContainer);
    if (!Array.isArray(entries) || entries.length === 0) {
        appendTextElement(auditContainer, "li", "No simulated actions recorded.");
        return;
    }
    entries.forEach((entry) => {
        const item = document.createElement("li");
        appendTextElement(item, "strong", entry.title);
        appendTextElement(
            item,
            "span",
            `${entry.outcome} · ${entry.action_type} · ${entry.recorded_at}`,
        );
        auditContainer.appendChild(item);
    });
}

function setPending(proposal) {
    pendingProposalId = proposal ? proposal.proposal_id : null;
    approvalControls.hidden = !proposal;
    confirmationInput.checked = false;
    approveButton.disabled = true;
    if (proposal) {
        renderPreview(proposal);
    }
}

async function loadState() {
    const state = await apiRequest("/state");
    clearNode(suggestionContainer);
    state.suggested_questions.forEach((question) => {
        const button = appendTextElement(suggestionContainer, "button", question);
        button.type = "button";
        button.addEventListener("click", () => {
            questionInput.value = question;
            questionInput.focus();
        });
    });
    clearNode(scenarioSelect);
    state.scenarios.forEach((scenario) => {
        const option = document.createElement("option");
        option.value = scenario.id;
        option.textContent = `${scenario.title} — ${scenario.summary}`;
        scenarioSelect.appendChild(option);
    });
    renderAudit(state.audit);
    if (state.pending_proposal) {
        setPending(state.pending_proposal);
    }
}

questionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearNode(answerContainer);
    appendTextElement(answerContainer, "p", "Consulting the bounded evidence set…");
    try {
        const payload = await apiRequest("/ask", {
            method: "POST",
            body: JSON.stringify({ question: questionInput.value }),
        });
        renderAnswer(payload);
    } catch (error) {
        clearNode(answerContainer);
        appendTextElement(answerContainer, "p", error.message);
        clearNode(citationContainer);
    }
});

proposeButton.addEventListener("click", async () => {
    clearNode(resultContainer);
    try {
        const payload = await apiRequest("/proposals", {
            method: "POST",
            body: JSON.stringify({ scenario_id: scenarioSelect.value }),
        });
        setPending(payload.proposal);
    } catch (error) {
        appendTextElement(resultContainer, "p", error.message);
    }
});

confirmationInput.addEventListener("change", () => {
    approveButton.disabled = !confirmationInput.checked;
});

approveButton.addEventListener("click", async () => {
    if (!pendingProposalId || !confirmationInput.checked) {
        return;
    }
    try {
        const payload = await apiRequest(`/proposals/${pendingProposalId}/approve`, {
            method: "POST",
            body: JSON.stringify({ approved: true }),
        });
        setPending(null);
        clearNode(resultContainer);
        appendTextElement(resultContainer, "h3", "Simulated execution result");
        appendTextElement(resultContainer, "p", payload.result);
        renderAudit(payload.audit);
    } catch (error) {
        clearNode(resultContainer);
        appendTextElement(resultContainer, "p", error.message);
    }
});

rejectButton.addEventListener("click", async () => {
    if (!pendingProposalId) {
        return;
    }
    try {
        const payload = await apiRequest(`/proposals/${pendingProposalId}/reject`, {
            method: "POST",
            body: JSON.stringify({ rejected: true }),
        });
        setPending(null);
        clearNode(previewContainer);
        appendTextElement(previewContainer, "p", payload.result);
    } catch (error) {
        clearNode(resultContainer);
        appendTextElement(resultContainer, "p", error.message);
    }
});

resetButton.addEventListener("click", async () => {
    try {
        const state = await apiRequest("/reset", {
            method: "POST",
            body: JSON.stringify({ reset: true }),
        });
        setPending(null);
        clearNode(previewContainer);
        appendTextElement(previewContainer, "p", "Demo reset. Choose a scenario to begin again.");
        clearNode(resultContainer);
        renderAudit(state.audit);
    } catch (error) {
        clearNode(resultContainer);
        appendTextElement(resultContainer, "p", error.message);
    }
});

loadState().catch((error) => {
    clearNode(answerContainer);
    appendTextElement(
        answerContainer,
        "p",
        `${error.message} The interactive showcase requires the Flask portfolio service.`,
    );
});

