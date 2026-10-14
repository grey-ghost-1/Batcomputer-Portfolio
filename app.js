const panelButtons = Array.from(document.querySelectorAll(".hud-btn[data-panel]"));
const panels = Array.from(document.querySelectorAll(".panel"));
const panelIds = new Set(panels.map((panel) => panel.id));
const redesignConsoleStatusElement = document.getElementById("redesignConsoleStatus");
const startVoiceInputButton = document.getElementById("startVoiceInput");
const zChatLogElement = document.getElementById("z-chat-log");
const zChatInputElement = document.getElementById("z-chat-input");
const zChatSendButton = document.getElementById("z-chat-send");
const zApiBase = window.location.port === "8080" ? "http://127.0.0.1:5000" : "";

function normalizePanelId(panelId) {
    return panelIds.has(panelId) ? panelId : null;
}

function showPanel(panelId, options = {}) {
    const resolvedPanelId = normalizePanelId(panelId);
    const updateHash = options.updateHash !== false;

    panels.forEach((panel) => {
        const isMatch = resolvedPanelId !== null && panel.id === resolvedPanelId;
        panel.classList.toggle("hidden", !isMatch);
    });

    panelButtons.forEach((button) => {
        const isActive = resolvedPanelId !== null && button.dataset.panel === resolvedPanelId;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-expanded", isActive ? "true" : "false");
    });

    if (updateHash && resolvedPanelId) {
        window.location.hash = resolvedPanelId;
    }

    if (resolvedPanelId && options.focus) {
        document.getElementById(resolvedPanelId)?.focus();
    }
}

panelButtons.forEach((button) => {
    button.addEventListener("click", () => {
        showPanel(button.dataset.panel || "", { focus: true });
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
    if (!zChatLogElement) {
        return;
    }

    const entry = document.createElement("div");
    entry.className = `chat-entry ${role}`;

    const label = document.createElement("span");
    label.className = "chat-entry-label";
    label.textContent = role === "user" ? "You" : "Z";
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

    zChatLogElement.appendChild(entry);
    zChatLogElement.scrollTop = zChatLogElement.scrollHeight;
    return entry;
}

function appendPendingAssistantEntry(message = "Checking deterministic responses…") {
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

function buildLocalZReply(message) {
    const normalized = message.toLowerCase();
    if (normalized.includes("status") || normalized.includes("health")) {
        return "Standalone mode is loaded, but the Flask service is not connected. Z remains a deterministic helper.";
    }
    if (normalized.includes("help") || normalized.includes("what can")) {
        return "I can return a small set of predefined portfolio and status responses. I do not use a model or perform system actions.";
    }
    return "This deterministic helper can answer predefined questions about the portfolio, software, cybersecurity, IT support, networking, automation, or system status.";
}

async function sendZMessage(message) {
    setRedesignStatus("Checking deterministic responses…");
    const pendingEntry = appendPendingAssistantEntry();
    try {
        const response = await fetch(`${zApiBase}/z`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message }),
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || "Unable to reach Z.");
        }
        updateChatEntry(pendingEntry, payload.reply || "Z is standing by.");
        setRedesignStatus("Deterministic helper connected. No model or actions are available.");
        speakAssistantResponse(payload.reply || "The deterministic helper is standing by.");
    } catch (error) {
        const reply = buildLocalZReply(message);
        updateChatEntry(pendingEntry, reply);
        setRedesignStatus("Standalone mode: Flask service unavailable.", true);
        speakAssistantResponse(reply);
    }
}

async function submitChatMessage() {
    if (!zChatInputElement) {
        return;
    }

    const message = zChatInputElement.value.trim();
    if (!message) {
        return;
    }

    appendChatEntry("user", message);
    zChatInputElement.value = "";

    const normalized = message.toLowerCase();
    if (normalized === "approve" || normalized === "reject" || normalized === "refresh" || normalized === "refresh state") {
        const guidance = "The optional local proposal metadata utility is at /z_agent_console.html. It is disabled by default and never reads repository files.";
        appendChatEntry("assistant", guidance);
        setRedesignStatus("Local proposal metadata is disabled by default.");
        speakAssistantResponse(guidance);
        return;
    }

    await sendZMessage(message);
}

function setupVoiceInput() {
    if (!startVoiceInputButton || !zChatInputElement) {
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
        setRedesignStatus("Listening for a portfolio question…");
        recognition.start();
    });

    recognition.addEventListener("result", (event) => {
        const transcript = event.results[0][0].transcript.trim();
        zChatInputElement.value = transcript;
        setRedesignStatus("Voice input captured. Checking deterministic responses.");
        submitChatMessage().catch((error) => {
            setRedesignStatus(error.message, true);
        });
    });

    recognition.addEventListener("error", (event) => {
        setRedesignStatus(`Voice input error: ${event.error}`, true);
    });
}

if (zChatSendButton) {
    zChatSendButton.addEventListener("click", () => {
        submitChatMessage().catch((error) => {
            setRedesignStatus(error.message, true);
        });
    });
}

if (zChatInputElement) {
    zChatInputElement.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            submitChatMessage().catch((error) => {
                setRedesignStatus(error.message, true);
            });
        }
    });
}

setupVoiceInput();

if (zChatLogElement) {
    zChatLogElement.innerHTML = '<div class="chat-empty">Z is a deterministic local helper. Ask about this portfolio or use browser voice input; no AI model or action execution is connected.</div>';
}

async function loadPublicSiteConfig() {
    const optionalLinks = document.getElementById("optional-application-links");
    const demoLinks = Array.from(document.querySelectorAll("[data-demo-link]"));
    const sourceLinks = Array.from(document.querySelectorAll("[data-public-source-path]"));
    if (!optionalLinks && demoLinks.length === 0 && sourceLinks.length === 0) {
        return;
    }

    try {
        const response = await fetch("/api/site/config", { headers: { Accept: "application/json" } });
        if (!response.ok) {
            return;
        }
        const config = await response.json();

        if (optionalLinks && Array.isArray(config.optional_links)) {
            config.optional_links.forEach((link) => {
                if (!link || typeof link.label !== "string" || typeof link.href !== "string") {
                    return;
                }
                const anchor = document.createElement("a");
                anchor.className = "secondary-cta";
                anchor.href = link.href;
                anchor.textContent = link.label;
                if (link.href.startsWith("https://")) {
                    anchor.rel = "noreferrer";
                }
                optionalLinks.appendChild(anchor);
            });
        }

        demoLinks.forEach((anchor) => {
            const demoUrl = config.demos?.[anchor.dataset.demoLink];
            if (typeof demoUrl === "string" && demoUrl.startsWith("https://")) {
                anchor.href = demoUrl;
                anchor.rel = "noreferrer";
                anchor.hidden = false;
            }
        });

        if (config.public_source_urls && typeof config.public_source_urls === "object") {
            sourceLinks.forEach((anchor) => {
                const sourceUrl = config.public_source_urls[anchor.dataset.publicSourcePath];
                if (typeof sourceUrl === "string" && sourceUrl.startsWith("https://")) {
                    anchor.href = sourceUrl;
                    anchor.rel = "noreferrer";
                    anchor.hidden = false;
                }
            });
        }
    } catch (error) {
        // Static hosting has no Flask configuration endpoint; optional links remain omitted.
    }
}

loadPublicSiteConfig();
showPanel(window.location.hash.slice(1), { updateHash: false });
