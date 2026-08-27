const categories = [
  "software_automation", "defensive_cybersecurity", "it_support",
  "data_engineering_analytics", "cloud_network_platform", "quality_engineering"
];
let token = sessionStorage.getItem("platform-token");
const message = document.querySelector("#message");
for (const id of ["asset-category", "work-category"]) {
  document.querySelector(`#${id}`).innerHTML = categories.map(value => `<option>${value}</option>`).join("");
}

async function api(path, options = {}) {
  const headers = {"Content-Type": "application/json", ...(options.headers || {})};
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(path, {...options, headers});
  const body = response.status === 204 ? null : await response.json();
  if (!response.ok) throw new Error(body?.error?.message || "Request failed");
  return body;
}

function showError(error) { message.textContent = error.message; }
function addCell(row, value) {
  const cell = document.createElement("td");
  cell.textContent = value;
  row.append(cell);
}
function renderAssets(items) {
  const body = document.querySelector("#assets");
  body.replaceChildren();
  for (const item of items) {
    const row = document.createElement("tr");
    addCell(row, item.name); addCell(row, item.category); addCell(row, item.status);
    body.append(row);
  }
}
function renderWorkItems(items) {
  const body = document.querySelector("#work-items");
  body.replaceChildren();
  for (const item of items) {
    const row = document.createElement("tr");
    addCell(row, item.title); addCell(row, item.category); addCell(row, item.status);
    const action = document.createElement("td");
    if (item.status === "planned") {
      const button = document.createElement("button");
      button.dataset.start = item.id; button.textContent = "Start"; action.append(button);
    }
    row.append(action); body.append(row);
  }
}
async function load() {
  document.querySelector("#auth").hidden = true;
  document.querySelector("#operator").hidden = false;
  const [assets, work, alfred] = await Promise.all([
    api("/api/v1/assets"), api("/api/v1/work-items"), api("/api/v1/alfred/status")
  ]);
  renderAssets(assets.items);
  renderWorkItems(work.items);
  document.querySelector("#alfred-status").textContent =
    `${alfred.status}; generation=${alfred.generates_content}; execution=${alfred.executes_actions}`;
}

document.querySelector("#auth-form").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    const action = event.submitter.value;
    const body = {
      workspace_name: document.querySelector("#workspace").value,
      email: document.querySelector("#email").value,
      password: document.querySelector("#password").value
    };
    const result = await api(`/api/v1/auth/${action}`, {method:"POST", body:JSON.stringify(body)});
    token = result.access_token; sessionStorage.setItem("platform-token", token); await load();
  } catch (error) { showError(error); }
});
document.querySelector("#asset-form").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    await api("/api/v1/assets", {method:"POST", body:JSON.stringify({
      name:document.querySelector("#asset-name").value,
      category:document.querySelector("#asset-category").value,
      description:document.querySelector("#asset-description").value
    })}); event.target.reset(); await load();
  } catch (error) { showError(error); }
});
document.querySelector("#work-form").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    await api("/api/v1/work-items", {method:"POST", body:JSON.stringify({
      title:document.querySelector("#work-title").value,
      category:document.querySelector("#work-category").value
    })}); event.target.reset(); await load();
  } catch (error) { showError(error); }
});
document.querySelector("#work-items").addEventListener("click", async event => {
  if (!event.target.dataset.start) return;
  try {
    await api(`/api/v1/work-items/${event.target.dataset.start}/transitions`, {
      method:"POST", body:JSON.stringify({status:"in_progress"})
    }); await load();
  } catch (error) { showError(error); }
});
document.querySelector("#alfred-form").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    const intent = await api("/api/v1/alfred/intents", {method:"POST", body:JSON.stringify({
      prompt:document.querySelector("#alfred-prompt").value
    })}); message.textContent = `Intent ${intent.id}: ${intent.status}; executed=${intent.executed}`;
    event.target.reset();
  } catch (error) { showError(error); }
});
if (token) load().catch(showError);
