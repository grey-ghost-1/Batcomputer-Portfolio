"use strict";

/* Alfred Assistant local console.
 * Token is kept in this tab only (sessionStorage). No external assets are used.
 * The session id isolates this tab from other clients of the same server.
 */

const SESSION_KEY = "alfred.session";
const TOKEN_KEY = "alfred.token";

const state = {
  token: sessionStorage.getItem(TOKEN_KEY) || "",
  session: ensureSession(),
  activeProposal: null,
  expiryTimer: null,
};

function ensureSession() {
  let existing = sessionStorage.getItem(SESSION_KEY);
  if (existing && existing.length >= 16) {
    return existing;
  }
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  existing = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  sessionStorage.setItem(SESSION_KEY, existing);
  return existing;
}

function authHeaders(extra) {
  const headers = Object.assign({ "Content-Type": "application/json" }, extra || {});
  if (state.token) {
    headers["Authorization"] = "Bearer " + state.token;
    headers["X-Alfred-Session"] = state.session;
  }
  return headers;
}

async function getJSON(path, authed) {
  const response = await fetch(path, {
    headers: authed ? authHeaders() : { "Content-Type": "application/json" },
  });
  return unwrap(response);
}

async function postJSON(path, body, authed) {
  const response = await fetch(path, {
    method: "POST",
    headers: authed ? authHeaders() : { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return unwrap(response);
}

async function unwrap(response) {
  let data = null;
  try {
    data = await response.json();
  } catch (err) {
    data = { error: "non-JSON response" };
  }
  if (!response.ok) {
    const detail = data && data.detail ? data.detail : "request failed (" + response.status + ")";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function el(tag, attrs, children) {
  const node = document.createElement(tag);
  if (attrs) {
    Object.keys(attrs).forEach((key) => {
      if (key === "class") {
        node.className = attrs[key];
      } else if (key === "text") {
        node.textContent = attrs[key];
      } else {
        node.setAttribute(key, attrs[key]);
      }
    });
  }
  (children || []).forEach((child) => {
    if (child) {
      node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    }
  });
  return node;
}

/* ---- status & capabilities ---- */

async function loadStatus() {
  const badges = document.getElementById("statusBadges");
  const grid = document.getElementById("statusGrid");
  const safety = document.getElementById("safetyPolicy");
  const modes = document.getElementById("answerModes");
  try {
    const [status, caps] = await Promise.all([
      getJSON("/api/status", false),
      getJSON("/api/capabilities", false),
    ]);
    document.getElementById("tagline").textContent = caps.persona.tagline;
    badges.innerHTML = "";
    badges.appendChild(badge("Local only", true));
    badges.appendChild(
      badge("Desktop " + (status.config.desktop_actions_enabled ? "on" : "off"),
        status.config.desktop_actions_enabled)
    );
    badges.appendChild(badge("Provider: " + status.provider.name, status.provider.available));
    badges.appendChild(badge("Web " + (status.web.enabled ? "on" : "off"), status.web.enabled));
    badges.appendChild(badge("Docs: " + status.index.document_count, status.index.document_count > 0));

    grid.innerHTML = "";
    addRow(grid, "Persona", caps.persona.name + " — " + caps.persona.role);
    addRow(grid, "Policy version", caps.persona_policy_version);
    addRow(grid, "Provider", status.provider.name + " (" + status.provider.status + ")");
    addRow(grid, "Model", status.provider.model || "none");
    addRow(grid, "Context", status.provider.context_chars + " chars");
    addRow(grid, "Web research", status.web.enabled ? status.web.broad_provider : "disabled");
    addRow(grid, "Keyless source", status.web.keyless_source || "none");
    addRow(grid, "Index sources", (status.index.sources || []).join(", ") || "none");
    addRow(grid, "Approved roots", String(status.config.approved_root_count));
    addRow(grid, "Token", status.config.action_token_configured ? "configured" : "not configured");

    safety.innerHTML = "";
    (caps.safety_policy || []).forEach((item) => safety.appendChild(el("li", { text: item })));
    modes.textContent = "Answer modes: " + (caps.answer_modes || []).join(", ") +
      " · Research: " + (caps.research_modes || []).join(", ");

    populateActionTypes(caps.actions || []);
  } catch (err) {
    badges.innerHTML = "";
    badges.appendChild(badge("status error", false));
  }
}

function badge(label, on) {
  return el("span", { class: "badge " + (on ? "on" : "off"), text: label });
}

function addRow(grid, term, value) {
  grid.appendChild(el("dt", { text: term }));
  grid.appendChild(el("dd", { text: value }));
}

/* ---- token ---- */

function refreshTokenState() {
  const stateEl = document.getElementById("tokenState");
  if (state.token) {
    stateEl.textContent = "Token set for this tab (session " + state.session.slice(0, 8) + "…).";
    stateEl.className = "muted status-ok";
  } else {
    stateEl.textContent = "No token set.";
    stateEl.className = "muted";
  }
}

function wireToken() {
  const form = document.getElementById("tokenForm");
  const input = document.getElementById("tokenInput");
  input.value = state.token;
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    state.token = input.value.trim();
    if (state.token) {
      sessionStorage.setItem(TOKEN_KEY, state.token);
    } else {
      sessionStorage.removeItem(TOKEN_KEY);
    }
    refreshTokenState();
  });
  document.getElementById("tokenClear").addEventListener("click", () => {
    state.token = "";
    input.value = "";
    sessionStorage.removeItem(TOKEN_KEY);
    refreshTokenState();
  });
  refreshTokenState();
}

/* ---- chat ---- */

function wireChat() {
  const form = document.getElementById("chatForm");
  const answer = document.getElementById("chatAnswer");
  const citations = document.getElementById("chatCitations");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = document.getElementById("chatMessage").value.trim();
    if (!message) {
      return;
    }
    answer.textContent = "Consulting the records…";
    citations.innerHTML = "";
    try {
      const payload = {
        message: message,
        mode: document.getElementById("chatMode").value,
        use_web: document.getElementById("chatWeb").checked,
        research_depth: document.getElementById("chatDepth").value,
      };
      const data = await postJSON("/api/chat", payload, false);
      renderAnswer(answer, citations, data);
    } catch (err) {
      answer.textContent = "";
      answer.appendChild(el("p", { class: "status-error", text: "Error: " + err.message }));
    }
  });
}

function renderAnswer(answer, citations, data) {
  answer.innerHTML = "";
  answer.appendChild(el("p", { text: data.reply }));
  const provider = data.provider || {};
  const meta =
    "Answer: " + data.answer_kind +
    " · Reasoning: " + data.reasoning_source +
    " · Model used: " + (provider.model_used ? "yes" : "no") +
    " · Web used: " + (data.web_used ? "yes" : "no") +
    (data.uncertainty ? " · candidly uncertain" : "");
  answer.appendChild(el("p", { class: "meta", text: meta }));

  citations.innerHTML = "";
  (data.citations || []).forEach((cite) => {
    const head = el("div", { class: "cite-head" }, [
      el("strong", { text: "[" + cite.index + "] " + cite.title }),
      el("span", { class: "provenance", text: cite.provenance }),
    ]);
    const card = el("div", { class: "citation" }, [head]);
    if (cite.excerpt) {
      card.appendChild(el("p", { class: "muted", text: cite.excerpt }));
    }
    if (cite.url) {
      card.appendChild(
        el("a", { href: cite.url, target: "_blank", rel: "noopener noreferrer", text: cite.url })
      );
    } else {
      card.appendChild(el("span", { class: "muted", text: "source: " + cite.source }));
    }
    if (cite.retrieved_at) {
      card.appendChild(el("p", { class: "expiry", text: "retrieved " + cite.retrieved_at }));
    }
    citations.appendChild(card);
  });
}

/* ---- system inspection ---- */

function wireSystem() {
  const output = document.getElementById("systemOutput");
  document.querySelectorAll("[data-system]").forEach((button) => {
    button.addEventListener("click", async () => {
      const kind = button.getAttribute("data-system");
      if (!state.token) {
        output.textContent = "Set the action token first.";
        return;
      }
      output.textContent = "Loading " + kind + "…";
      try {
        let path = "/api/system/" + kind;
        if (kind === "directory") {
          path = "/api/system/directory?root=0&path=.";
        }
        const data = await getJSON(path, true);
        output.textContent = JSON.stringify(data, null, 2);
      } catch (err) {
        output.textContent = "Error: " + err.message;
      }
    });
  });
}

/* ---- action builder ---- */

const ACTION_FIELDS = {
  create_folder: [
    { name: "root", label: "Approved root index", type: "number", value: "0" },
    { name: "parent", label: "Parent (relative)", type: "text", value: "." },
    { name: "name", label: "New folder name", type: "text", value: "" },
  ],
  move_file: [
    { name: "root", label: "Approved root index", type: "number", value: "0" },
    { name: "source", label: "Source (relative)", type: "text", value: "" },
    { name: "destination", label: "Destination (relative)", type: "text", value: "" },
  ],
  organize_folder: [
    { name: "root", label: "Approved root index", type: "number", value: "0" },
    { name: "folder", label: "Folder (relative)", type: "text", value: "." },
    {
      name: "rules",
      label: 'Rules (JSON: [{"extension":".txt","subfolder":"text"}])',
      type: "json",
      value: '[{"extension":".txt","subfolder":"text"}]',
    },
  ],
  open_app: [{ name: "executable", label: "Executable (allow-listed)", type: "text", value: "" }],
  open_url: [{ name: "url", label: "HTTPS URL (allow-listed host)", type: "text", value: "" }],
  set_clipboard: [{ name: "text", label: "Clipboard text", type: "text", value: "" }],
};

function populateActionTypes(actions) {
  const select = document.getElementById("actionType");
  select.innerHTML = "";
  actions.forEach((action) => {
    const label = action.action_type + (action.execution_enabled ? "" : " (execution disabled)");
    select.appendChild(el("option", { value: action.action_type, text: label }));
  });
  renderActionFields(select.value);
}

function renderActionFields(actionType) {
  const container = document.getElementById("actionFields");
  container.innerHTML = "";
  (ACTION_FIELDS[actionType] || []).forEach((field) => {
    const id = "field_" + field.name;
    container.appendChild(el("label", { for: id, text: field.label }));
    if (field.type === "json") {
      const area = el("textarea", { id: id, rows: "3" });
      area.value = field.value;
      container.appendChild(area);
    } else {
      const input = el("input", {
        id: id,
        type: field.type === "number" ? "number" : "text",
      });
      input.value = field.value;
      container.appendChild(input);
    }
  });
}

function collectPayload(actionType) {
  const payload = {};
  (ACTION_FIELDS[actionType] || []).forEach((field) => {
    const node = document.getElementById("field_" + field.name);
    if (!node) {
      return;
    }
    if (field.type === "number") {
      payload[field.name] = parseInt(node.value, 10) || 0;
    } else if (field.type === "json") {
      payload[field.name] = JSON.parse(node.value);
    } else {
      payload[field.name] = node.value;
    }
  });
  return payload;
}

function wireActions() {
  const form = document.getElementById("actionForm");
  const select = document.getElementById("actionType");
  select.addEventListener("change", () => renderActionFields(select.value));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const preview = document.getElementById("actionPreview");
    if (!state.token) {
      preview.innerHTML = "";
      preview.appendChild(el("p", { class: "status-error", text: "Set the action token first." }));
      return;
    }
    try {
      const payload = collectPayload(select.value);
      const proposal = await postJSON(
        "/api/actions/propose",
        { action_type: select.value, payload: payload },
        true
      );
      state.activeProposal = proposal;
      renderPreview(proposal);
    } catch (err) {
      preview.innerHTML = "";
      preview.appendChild(el("p", { class: "status-error", text: "Error: " + err.message }));
    }
  });
  document.getElementById("refreshAudit").addEventListener("click", loadAudit);
}

function renderPreview(proposal) {
  const container = document.getElementById("actionPreview");
  container.innerHTML = "";
  const preview = proposal.preview || {};
  const card = el("div", { class: "card" }, [
    el("h3", { text: proposal.action_type + " — " + proposal.status }),
    el("p", { text: preview.summary || "" }),
  ]);

  (preview.effects || []).forEach((effect) => {
    card.appendChild(el("p", { class: "muted", text: "• " + effect }));
  });
  (preview.path_diff || []).forEach((diff) => {
    const line = el("div", { class: "diff" }, [
      diff.from ? el("span", { class: "from", text: "- " + diff.from + " " }) : null,
      el("span", { class: "to", text: "+ " + (diff.to || "") }),
    ]);
    card.appendChild(line);
  });
  (preview.warnings || []).forEach((warn) => {
    card.appendChild(el("p", { class: "warn", text: "⚠ " + warn }));
  });

  card.appendChild(el("p", { class: "muted", text: "hash: " + proposal.payload_hash.slice(0, 24) + "…" }));
  const expiry = el("p", { class: "expiry", id: "expiryLine" });
  card.appendChild(expiry);

  const buttons = el("div", { class: "row" });
  const approveBtn = el("button", { class: "approve", type: "button", text: "Approve" });
  const executeBtn = el("button", { type: "button", text: "Execute" });
  const rejectBtn = el("button", { class: "danger", type: "button", text: "Reject" });
  executeBtn.disabled = true;

  approveBtn.addEventListener("click", async () => {
    try {
      const approved = await postJSON(
        "/api/actions/" + proposal.id + "/approve",
        { payload_hash: proposal.payload_hash },
        true
      );
      state.activeProposal = approved;
      approveBtn.disabled = true;
      executeBtn.disabled = !approved.execution_enabled;
      card.appendChild(el("p", { class: "status-ok", text: "Approved. Ready to execute once." }));
      if (!approved.execution_enabled) {
        card.appendChild(el("p", { class: "warn", text: "Execution is disabled in this configuration." }));
      }
      loadAudit();
    } catch (err) {
      card.appendChild(el("p", { class: "status-error", text: "Approve failed: " + err.message }));
    }
  });

  executeBtn.addEventListener("click", async () => {
    try {
      const executed = await postJSON("/api/actions/" + proposal.id + "/execute", {}, true);
      executeBtn.disabled = true;
      card.appendChild(
        el("pre", { class: "output", text: JSON.stringify(executed.result, null, 2) })
      );
      card.appendChild(el("p", { class: "status-ok", text: "Executed once. Recorded in audit." }));
      stopExpiryTimer();
      loadAudit();
    } catch (err) {
      card.appendChild(el("p", { class: "status-error", text: "Execute failed: " + err.message }));
      loadAudit();
    }
  });

  rejectBtn.addEventListener("click", async () => {
    try {
      await postJSON("/api/actions/" + proposal.id + "/reject", {}, true);
      container.innerHTML = "";
      stopExpiryTimer();
      loadAudit();
    } catch (err) {
      card.appendChild(el("p", { class: "status-error", text: "Reject failed: " + err.message }));
    }
  });

  buttons.appendChild(approveBtn);
  buttons.appendChild(executeBtn);
  buttons.appendChild(rejectBtn);
  card.appendChild(buttons);
  container.appendChild(card);

  startExpiryTimer(proposal.expires_at, [approveBtn, executeBtn]);
}

function startExpiryTimer(expiresAt, buttons) {
  stopExpiryTimer();
  const line = document.getElementById("expiryLine");
  const target = new Date(expiresAt).getTime();
  const tick = () => {
    const remaining = Math.round((target - Date.now()) / 1000);
    if (!line) {
      return;
    }
    if (remaining <= 0) {
      line.textContent = "Expired.";
      line.className = "expiry soon";
      buttons.forEach((button) => {
        button.disabled = true;
      });
      stopExpiryTimer();
      return;
    }
    line.textContent = "Expires in " + remaining + "s.";
    line.className = remaining <= 20 ? "expiry soon" : "expiry";
  };
  tick();
  state.expiryTimer = setInterval(tick, 1000);
}

function stopExpiryTimer() {
  if (state.expiryTimer) {
    clearInterval(state.expiryTimer);
    state.expiryTimer = null;
  }
}

/* ---- audit ---- */

async function loadAudit() {
  const timeline = document.getElementById("auditTimeline");
  if (!state.token) {
    timeline.innerHTML = "";
    timeline.appendChild(el("li", { class: "muted", text: "Set the action token to view the audit." }));
    return;
  }
  try {
    const data = await getJSON("/api/actions/audit", true);
    timeline.innerHTML = "";
    (data.audit || []).forEach((entry) => {
      const tagClass = "tag " + entry.event;
      timeline.appendChild(
        el("li", {}, [
          el("span", { class: tagClass, text: entry.event }),
          el("span", { text: entry.action_type + " · " + entry.created_at }),
        ])
      );
    });
    if (!data.audit || data.audit.length === 0) {
      timeline.appendChild(el("li", { class: "muted", text: "No audit entries yet." }));
    }
  } catch (err) {
    timeline.innerHTML = "";
    timeline.appendChild(el("li", { class: "status-error", text: "Audit error: " + err.message }));
  }
}

/* ---- boot ---- */

function boot() {
  wireToken();
  wireChat();
  wireSystem();
  wireActions();
  loadStatus();
  loadAudit();
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", boot);
}
