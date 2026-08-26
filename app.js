const panelButtons = Array.from(document.querySelectorAll(".hud-btn[data-panel]"));
const panels = Array.from(document.querySelectorAll(".panel"));
const panelIds = new Set(panels.map((panel) => panel.id));
const redesignConsoleStatusElement = document.getElementById("redesignConsoleStatus");
const startVoiceInputButton = document.getElementById("startVoiceInput");
const alfredChatLogElement = document.getElementById("alfred-chat-log");
const alfredChatInputElement = document.getElementById("alfred-chat-input");
const alfredChatSendButton = document.getElementById("alfred-chat-send");
const alfredApiBase = window.location.port === "8080" ? "http://127.0.0.1:5000" : "";

function normalizePanelId(panelId) {
    return panelIds.has(panelId) ? panelId : "about";
}

function showPanel(panelId, options = {}) {
    const resolvedPanelId = normalizePanelId(panelId);
    const updateHash = options.updateHash !== false;

    panels.forEach((panel) => {
        const isMatch = panel.id === resolvedPanelId;
        panel.classList.toggle("hidden", !isMatch);
    });

    panelButtons.forEach((button) => {
        const isActive = button.dataset.panel === resolvedPanelId;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-expanded", isActive ? "true" : "false");
    });

    if (updateHash) {
        window.location.hash = resolvedPanelId;
    }
}

panelButtons.forEach((button) => {
    button.addEventListener("click", () => {
        showPanel(button.dataset.panel || "");
    });
});

window.addEventListener("hashchange", () => {
    showPanel(window.location.hash.slice(1), { updateHash: false });
});

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function setRedesignStatus(message, isError = false) {
    if (!redesignConsoleStatusElement) {
        return;
    }
    redesignConsoleStatusElement.classList.toggle("runtime-error", isError);
    redesignConsoleStatusElement.classList.toggle("runtime-ok", !isError);
    redesignConsoleStatusElement.textContent = message;
}

function appendChatEntry(role, content, preformatted = false) {
    if (!alfredChatLogElement) {
        return;
    }

    const entry = document.createElement("div");
    entry.className = `chat-entry ${role}`;

    const label = document.createElement("span");
    label.className = "chat-entry-label";
    label.textContent = role === "user" ? "You" : "Alfred";
    entry.appendChild(label);

    if (preformatted) {
        const block = document.createElement("pre");
        block.textContent = content;
        entry.appendChild(block);
    } else {
        const body = document.createElement("div");
        body.textContent = content;
        entry.appendChild(body);
    }

    alfredChatLogElement.appendChild(entry);
    alfredChatLogElement.scrollTop = alfredChatLogElement.scrollHeight;
    return entry;
}

function appendPendingAssistantEntry(message = "Alfred is responding…") {
    return appendChatEntry("assistant", message);
}

function updateChatEntry(entry, content, preformatted = false) {
    if (!entry) {
        return;
    }

    const existingBody = entry.querySelector("div, pre");
    if (existingBody) {
        existingBody.remove();
    }

    if (preformatted) {
        const block = document.createElement("pre");
        block.textContent = content;
        entry.appendChild(block);
    } else {
        const body = document.createElement("div");
        body.textContent = content;
        entry.appendChild(body);
    }
}

function renderProposalObject(proposal) {
    return JSON.stringify(
        {
            target_file: proposal.target_file,
            explanation: proposal.explanation,
            full_replacement_content: proposal.full_content,
        },
        null,
        2
    );
}

function renderRedesignProposal(proposal) {
    return proposal && typeof proposal === "object" ? proposal : null;
}

function speakAssistantResponse(message) {
    if (!("speechSynthesis" in window) || !message) {
        return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(message);
    utterance.rate = 1;
    utterance.pitch = 1;
    window.speechSynthesis.speak(utterance);
}

function buildLocalAlfredReply(message) {
    const normalized = message.toLowerCase();
    if (normalized.includes("status") || normalized.includes("health")) {
        return "Standalone mode is online. The HUD is loaded, but the Flask service is not connected.";
    }
    if (normalized.includes("help") || normalized.includes("what can")) {
        return "I can answer basic status questions in standalone mode. Start the Flask server for live system actions, weather, and coding-agent features.";
    }
    return "I am ready to help. Ask me about the portfolio, software, cybersecurity, IT support, networking, automation, or system status.";
}

async function sendAlfredMessage(message) {
    setRedesignStatus("Alfred is responding…");
    const pendingEntry = appendPendingAssistantEntry();
    try {
        const response = await fetch(`${alfredApiBase}/alfred`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message }),
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || "Unable to reach Alfred.");
        }
        updateChatEntry(pendingEntry, payload.reply || "Alfred is standing by.");
        setRedesignStatus("Alfred is live and ready.");
        speakAssistantResponse(payload.reply || "Alfred is standing by.");
    } catch (error) {
        const reply = buildLocalAlfredReply(message);
        updateChatEntry(pendingEntry, reply);
        setRedesignStatus("Standalone mode: Flask service unavailable.", true);
        speakAssistantResponse(reply);
    }
}

async function submitChatMessage() {
    if (!alfredChatInputElement) {
        return;
    }

    const message = alfredChatInputElement.value.trim();
    if (!message) {
        return;
    }

    appendChatEntry("user", message);
    alfredChatInputElement.value = "";

    const normalized = message.toLowerCase();
    if (normalized === "approve" || normalized === "reject" || normalized === "refresh" || normalized === "refresh state") {
        appendChatEntry("assistant", "Website redesign controls now live on the Coding Agent tab, sir. Use that page for proposal approval, rejection, and redesign state.");
        setRedesignStatus("Use the Coding Agent tab for website redesign proposals.");
        speakAssistantResponse("Use the Coding Agent tab for website redesign proposals.");
        return;
    }

    await sendAlfredMessage(message);
}

function setupVoiceInput() {
    if (!startVoiceInputButton || !alfredChatInputElement) {
        return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        startVoiceInputButton.disabled = true;
        startVoiceInputButton.textContent = "Voice unavailable";
        return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    startVoiceInputButton.addEventListener("click", () => {
        setRedesignStatus("Listening for HUD redesign request…");
        recognition.start();
    });

    recognition.addEventListener("result", (event) => {
        const transcript = event.results[0][0].transcript.trim();
        alfredChatInputElement.value = transcript;
        setRedesignStatus("Voice input captured. Sending it to Alfred.");
        submitChatMessage().catch((error) => {
            setRedesignStatus(error.message, true);
        });
    });

    recognition.addEventListener("error", (event) => {
        setRedesignStatus(`Voice input error: ${event.error}`, true);
    });
}

if (alfredChatSendButton) {
    alfredChatSendButton.addEventListener("click", () => {
        submitChatMessage().catch((error) => {
            setRedesignStatus(error.message, true);
        });
    });
}

if (alfredChatInputElement) {
    alfredChatInputElement.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            submitChatMessage().catch((error) => {
                setRedesignStatus(error.message, true);
            });
        }
    });
}

setupVoiceInput();

if (alfredChatLogElement) {
    alfredChatLogElement.innerHTML = '<div class="chat-empty">Alfred is online. Ask a question, request a HUD redesign, or use voice input for live conversation.</div>';
}

showPanel(window.location.hash.slice(1) || "about", { updateHash: false });
