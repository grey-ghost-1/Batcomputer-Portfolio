const form = document.getElementById("simulation");
const runButton = document.getElementById("runSimulation");
const runButtonLabel = document.getElementById("runButtonLabel");
const runStatus = document.getElementById("runStatus");
const pauseButton = document.getElementById("pauseAnimation");
const replayButton = document.getElementById("replayAnimation");
const canvas = document.getElementById("orbitCanvas");
const context = canvas.getContext("2d");
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

const metrics = {
  scenario: document.getElementById("scenarioMetric"),
  samples: document.getElementById("sampleMetric"),
  rk4Drift: document.getElementById("rk4DriftMetric"),
  verletDrift: document.getElementById("verletDriftMetric"),
  positionDelta: document.getElementById("positionDeltaMetric"),
  time: document.getElementById("timeMetric"),
};

const links = {
  container: document.getElementById("resultLinks"),
  json: document.getElementById("jsonLink"),
  csv: document.getElementById("csvLink"),
  share: document.getElementById("shareLink"),
};

const animation = {
  frame: null,
  lastTimestamp: null,
  progress: 1,
  playing: false,
  paused: false,
  durationMs: 7000,
};

let viewport = { width: 960, height: 600, dpr: 1 };
let trajectories = null;

function setRunState(state, message) {
  runButton.dataset.state = state;
  runButton.disabled = state === "running";
  runButton.setAttribute("aria-busy", String(state === "running"));
  runButtonLabel.textContent = {
    idle: "Run simulation",
    running: "Running simulation…",
    success: "Run another simulation",
    error: "Try simulation again",
  }[state];
  runStatus.className = `run-status ${state === "idle" || state === "running" ? "" : state}`;
  runStatus.textContent = message;
}

function parseNumber(id, label) {
  const value = Number(document.getElementById(id).value);
  if (!Number.isFinite(value)) {
    throw new Error(`${label} must be a valid number.`);
  }
  return value;
}

function buildRequest() {
  if (!form.reportValidity()) {
    throw new Error("Correct the highlighted scenario fields before running.");
  }
  const radiusKm = parseNumber("radiusKm", "Initial radius");
  const speedKmS = parseNumber("speedKmS", "Tangential speed");
  const durationSeconds = parseNumber("durationSeconds", "Duration");
  const stepSeconds = parseNumber("stepSeconds", "Step size");
  if (durationSeconds / stepSeconds > 20000) {
    throw new Error("Duration divided by step size must not exceed 20,000 steps.");
  }
  return {
    central_body: document.getElementById("centralBody").value.trim(),
    initial_position: [radiusKm * 1000, 0],
    initial_velocity: [0, speedKmS * 1000],
    duration_seconds: durationSeconds,
    step_seconds: stepSeconds,
    integrators: ["rk4", "velocity_verlet"],
  };
}

function apiError(payload, status) {
  const detail = payload && payload.detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || "Invalid scenario value.").join(" ");
  }
  if (typeof detail === "string") {
    return detail;
  }
  return `Simulation request failed with HTTP ${status}.`;
}

function assertSavedScenario(saved) {
  const rk4 = saved?.result?.runs?.rk4;
  const verlet = saved?.result?.runs?.velocity_verlet;
  if (
    typeof saved?.scenario_id !== "string"
    || !saved.share_path
    || !Array.isArray(rk4?.samples)
    || rk4.samples.length < 2
    || !Array.isArray(verlet?.samples)
    || verlet.samples.length < 2
    || !Number.isFinite(rk4.max_relative_energy_drift)
    || !Number.isFinite(verlet.max_relative_energy_drift)
  ) {
    throw new Error("The service returned an incomplete simulation result.");
  }
  return { rk4, verlet };
}

function formatDrift(value) {
  return Number(value).toExponential(3);
}

function formatDistance(value) {
  return Number.isFinite(value) ? `${(value / 1000).toFixed(3)} km` : "Not compared";
}

function renderMetrics(saved, runs) {
  const request = saved.request;
  metrics.scenario.textContent = saved.scenario_id;
  metrics.samples.textContent = runs.rk4.samples.length.toLocaleString();
  metrics.rk4Drift.textContent = formatDrift(runs.rk4.max_relative_energy_drift);
  metrics.verletDrift.textContent = formatDrift(runs.verlet.max_relative_energy_drift);
  metrics.positionDelta.textContent = formatDistance(
    saved.result.comparison.final_position_delta_m
  );
  metrics.time.textContent = `${request.duration_seconds.toLocaleString()} s / ${request.step_seconds.toLocaleString()} s`;
  document.getElementById("resultsHint").textContent = saved.created
    ? "Scenario saved with deterministic lineage and export paths."
    : "Matching scenario already existed; the content-derived ID was reused.";

  links.json.href = `/api/v1/scenarios/${encodeURIComponent(saved.scenario_id)}/export.json`;
  links.csv.href = `/api/v1/scenarios/${encodeURIComponent(saved.scenario_id)}/export.csv`;
  links.share.href = saved.share_path;
  links.container.hidden = false;
}

function starPosition(index, size, offset) {
  return ((index * 73 + offset) % 997) / 997 * size;
}

function drawBackground(width, height) {
  const gradient = context.createRadialGradient(
    width * 0.5,
    height * 0.48,
    0,
    width * 0.5,
    height * 0.48,
    Math.max(width, height) * 0.7
  );
  gradient.addColorStop(0, "#071827");
  gradient.addColorStop(0.58, "#020912");
  gradient.addColorStop(1, "#000307");
  context.fillStyle = gradient;
  context.fillRect(0, 0, width, height);

  for (let index = 0; index < 90; index += 1) {
    const x = starPosition(index, width, 19);
    const y = starPosition(index, height, 211);
    const radius = index % 11 === 0 ? 1.25 : 0.65;
    context.globalAlpha = 0.28 + (index % 5) * 0.1;
    context.fillStyle = "#d9f4ff";
    context.fillRect(x, y, radius, radius);
  }
  context.globalAlpha = 1;
}

function drawAxes(width, height, centerX, centerY, radius) {
  context.save();
  context.strokeStyle = "rgba(130, 190, 219, 0.16)";
  context.lineWidth = 1;
  context.setLineDash([4, 7]);
  context.beginPath();
  context.moveTo(centerX - radius, centerY);
  context.lineTo(centerX + radius, centerY);
  context.moveTo(centerX, centerY - radius);
  context.lineTo(centerX, centerY + radius);
  context.stroke();
  context.setLineDash([]);
  context.fillStyle = "rgba(188, 224, 240, 0.65)";
  context.font = "12px ui-monospace, Consolas, monospace";
  context.fillText("+X", Math.min(width - 28, centerX + radius - 20), centerY - 8);
  context.fillText("+Y", centerX + 9, Math.max(16, centerY - radius + 16));
  context.fillText("km", width - 28, height - 14);
  context.restore();
}

function drawCentralBody(centerX, centerY, sceneRadius) {
  const bodyRadius = Math.max(13, Math.min(24, sceneRadius * 0.055));
  const glow = context.createRadialGradient(
    centerX - bodyRadius * 0.3,
    centerY - bodyRadius * 0.3,
    2,
    centerX,
    centerY,
    bodyRadius * 2.8
  );
  glow.addColorStop(0, "#f6fbff");
  glow.addColorStop(0.18, "#6bc5ff");
  glow.addColorStop(0.48, "#176daa");
  glow.addColorStop(1, "rgba(10, 67, 111, 0)");
  context.fillStyle = glow;
  context.beginPath();
  context.arc(centerX, centerY, bodyRadius * 2.8, 0, Math.PI * 2);
  context.fill();

  context.fillStyle = "#1978b5";
  context.strokeStyle = "#9de4ff";
  context.lineWidth = 1.5;
  context.beginPath();
  context.arc(centerX, centerY, bodyRadius, 0, Math.PI * 2);
  context.fill();
  context.stroke();
}

function sampleScale(runs) {
  if (!runs) {
    return 7000000;
  }
  return Math.max(
    1,
    ...runs.rk4.samples.flatMap((sample) => sample.position.map(Math.abs)),
    ...runs.verlet.samples.flatMap((sample) => sample.position.map(Math.abs))
  );
}

function mapSamples(samples, centerX, centerY, pixelRadius, scale) {
  return samples.map((sample) => ({
    x: centerX + sample.position[0] / scale * pixelRadius,
    y: centerY - sample.position[1] / scale * pixelRadius,
  }));
}

function strokeTrajectory(points, color, dashed = false, progress = 1) {
  const endIndex = Math.max(1, Math.floor((points.length - 1) * progress));
  context.save();
  context.strokeStyle = color;
  context.lineWidth = 2;
  context.shadowColor = color;
  context.shadowBlur = 7;
  context.setLineDash(dashed ? [7, 6] : []);
  context.beginPath();
  points.slice(0, endIndex + 1).forEach((point, index) => {
    if (index === 0) {
      context.moveTo(point.x, point.y);
    } else {
      context.lineTo(point.x, point.y);
    }
  });
  context.stroke();
  context.restore();
}

function drawSpacecraft(point) {
  context.save();
  context.translate(point.x, point.y);
  context.shadowColor = "#ffffff";
  context.shadowBlur = 14;
  context.fillStyle = "#ffffff";
  context.strokeStyle = "#5dd2ff";
  context.lineWidth = 2;
  context.beginPath();
  context.moveTo(9, 0);
  context.lineTo(-6, -5);
  context.lineTo(-3, 0);
  context.lineTo(-6, 5);
  context.closePath();
  context.fill();
  context.stroke();
  context.restore();
}

function drawScene(progress = animation.progress) {
  const { width, height } = viewport;
  const centerX = width / 2;
  const centerY = height / 2;
  const sceneRadius = Math.min(width, height) * 0.39;
  drawBackground(width, height);
  drawAxes(width, height, centerX, centerY, sceneRadius);

  if (!trajectories) {
    context.save();
    context.strokeStyle = "rgba(93, 210, 255, 0.48)";
    context.lineWidth = 2;
    context.setLineDash([7, 7]);
    context.beginPath();
    context.arc(centerX, centerY, sceneRadius * 0.82, 0, Math.PI * 2);
    context.stroke();
    context.restore();
    drawCentralBody(centerX, centerY, sceneRadius);
    drawSpacecraft({ x: centerX + sceneRadius * 0.82, y: centerY });
    return;
  }

  const scale = sampleScale(trajectories) * 1.12;
  const rk4Points = mapSamples(
    trajectories.rk4.samples,
    centerX,
    centerY,
    sceneRadius,
    scale
  );
  const verletPoints = mapSamples(
    trajectories.verlet.samples,
    centerX,
    centerY,
    sceneRadius,
    scale
  );
  strokeTrajectory(verletPoints, "#c28cff", true, progress);
  strokeTrajectory(rk4Points, "#5dd2ff", false, progress);
  drawCentralBody(centerX, centerY, sceneRadius);
  const markerIndex = Math.min(
    rk4Points.length - 1,
    Math.floor((rk4Points.length - 1) * progress)
  );
  drawSpacecraft(rk4Points[markerIndex]);
}

function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  const cssWidth = Math.max(320, Math.round(rect.width));
  const cssHeight = Math.max(300, Math.round(rect.height || cssWidth * 0.625));
  const dpr = Math.min(window.devicePixelRatio || 1, 2.5);
  canvas.width = Math.round(cssWidth * dpr);
  canvas.height = Math.round(cssHeight * dpr);
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  viewport = { width: cssWidth, height: cssHeight, dpr };
  drawScene();
}

function stopAnimation() {
  if (animation.frame !== null) {
    cancelAnimationFrame(animation.frame);
  }
  animation.frame = null;
  animation.playing = false;
  animation.paused = false;
  animation.lastTimestamp = null;
}

function animationStep(timestamp) {
  if (!animation.playing || animation.paused) {
    return;
  }
  if (animation.lastTimestamp === null) {
    animation.lastTimestamp = timestamp;
  } else {
    animation.progress = Math.min(
      1,
      animation.progress + (timestamp - animation.lastTimestamp) / animation.durationMs
    );
    animation.lastTimestamp = timestamp;
  }
  drawScene(animation.progress);
  if (animation.progress < 1) {
    animation.frame = requestAnimationFrame(animationStep);
  } else {
    animation.playing = false;
    animation.frame = null;
    pauseButton.disabled = true;
    setRunState("success", "Simulation complete. Metrics and exports are ready.");
  }
}

function replayTrajectory() {
  if (!trajectories) {
    return;
  }
  stopAnimation();
  pauseButton.textContent = "Pause";
  replayButton.disabled = false;
  if (reducedMotion.matches) {
    animation.progress = 1;
    drawScene(1);
    pauseButton.disabled = true;
    setRunState("success", "Reduced motion is enabled; the complete trajectory is shown.");
    return;
  }
  animation.progress = 0;
  animation.playing = true;
  pauseButton.disabled = false;
  setRunState("success", "Simulation saved. Playing the RK4 spacecraft trajectory.");
  drawScene(0);
  animation.frame = requestAnimationFrame(animationStep);
}

pauseButton.addEventListener("click", () => {
  if (!trajectories || (!animation.playing && !animation.paused)) {
    return;
  }
  if (animation.paused) {
    animation.paused = false;
    animation.playing = true;
    animation.lastTimestamp = null;
    pauseButton.textContent = "Pause";
    setRunState("success", "Trajectory playback resumed.");
    animation.frame = requestAnimationFrame(animationStep);
  } else {
    animation.paused = true;
    animation.playing = false;
    if (animation.frame !== null) {
      cancelAnimationFrame(animation.frame);
    }
    animation.frame = null;
    pauseButton.textContent = "Resume";
    setRunState("success", "Trajectory playback paused.");
  }
});

replayButton.addEventListener("click", replayTrajectory);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  stopAnimation();
  pauseButton.disabled = true;
  replayButton.disabled = true;
  pauseButton.textContent = "Pause";

  let request;
  try {
    request = buildRequest();
  } catch (error) {
    setRunState("error", error.message);
    return;
  }

  setRunState("running", "Computing RK4 and velocity-Verlet trajectories…");
  try {
    const response = await fetch("/api/v1/scenarios", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(request),
    });
    const responseText = await response.text();
    let saved;
    try {
      saved = JSON.parse(responseText);
    } catch (error) {
      throw new Error(`The service returned an unreadable response (HTTP ${response.status}).`);
    }
    if (!response.ok) {
      throw new Error(apiError(saved, response.status));
    }
    const runs = assertSavedScenario(saved);
    trajectories = runs;
    renderMetrics(saved, runs);
    replayTrajectory();
  } catch (error) {
    drawScene();
    setRunState(
      "error",
      error instanceof Error ? error.message : "The simulation could not be completed."
    );
  }
});

reducedMotion.addEventListener?.("change", () => {
  if (trajectories) {
    replayTrajectory();
  }
});

if ("ResizeObserver" in window) {
  new ResizeObserver(resizeCanvas).observe(canvas);
} else {
  window.addEventListener("resize", resizeCanvas);
}

resizeCanvas();
