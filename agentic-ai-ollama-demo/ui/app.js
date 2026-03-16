const heroStatusCard = document.getElementById("hero-status-card");
const heroStatus = document.getElementById("hero-status");
const heroSubstatus = document.getElementById("hero-substatus");
const alarmBanner = document.getElementById("alarm-banner");
const alarmTitle = document.getElementById("alarm-title");
const alarmDetails = document.getElementById("alarm-details");
const pipelineStatus = document.getElementById("pipeline-status");
const pipelineSummary = document.getElementById("pipeline-summary");
const scenarioName = document.getElementById("scenario-name");
const scenarioDescription = document.getElementById("scenario-description");
const approvalStatus = document.getElementById("approval-status");
const approvalSummary = document.getElementById("approval-summary");
const timelineCount = document.getElementById("timeline-count");
const activePhaseSummary = document.getElementById("active-phase-summary");
const timelineStrip = document.getElementById("timeline-strip");
const activePhasePill = document.getElementById("active-phase-pill");
const agentAvatar = document.getElementById("agent-avatar");
const agentFace = document.getElementById("agent-face");
const agentStateTitle = document.getElementById("agent-state-title");
const agentStateText = document.getElementById("agent-state-text");
const approvalPill = document.getElementById("approval-pill");
const approvalBody = document.getElementById("approval-body");
const remediationContext = document.getElementById("remediation-context");
const approvalPanel = document.getElementById("approval-panel");
const remediationContextPanel = document.getElementById("remediation-context-panel");
const approveButton = document.getElementById("approve-button");
const rejectButton = document.getElementById("reject-button");
const resetButton = document.getElementById("reset-button");
const eventCount = document.getElementById("event-count");
const eventStream = document.getElementById("event-stream");
const logView = document.getElementById("log-view");
const liveModeButton = document.getElementById("live-mode-button");
const liveModeLabel = document.getElementById("live-mode-label");
const scenarioButtons = Array.from(document.querySelectorAll(".scenario-button"));
const tabButtons = Array.from(document.querySelectorAll(".tab-button"));
const tabPanels = Array.from(document.querySelectorAll(".tab-panel"));

let liveModeEnabled = true;
let refreshTimer = null;
let timelinePlaybackTimer = null;
let recoverySleepTimer = null;
let playbackTimeline = [];
let playbackIndex = -1;
let playbackSignature = "";
let rawPlaybackSignature = "";
let dismissedPlaybackSignature = "";

const agentIcons = {
  idle: `
    <svg viewBox="0 0 48 48" fill="none">
      <circle cx="24" cy="24" r="17" fill="#F3F8FE" stroke="#7EA2C8" stroke-width="2"/>
      <path d="M16 21c2.5 1.8 5 1.8 7.5 0" stroke="#5D7898" stroke-width="2.2" stroke-linecap="round"/>
      <path d="M24.5 21c2.5 1.8 5 1.8 7.5 0" stroke="#5D7898" stroke-width="2.2" stroke-linecap="round"/>
      <path d="M18 30c4.5 2.5 9.5 2.5 14 0" stroke="#5D7898" stroke-width="2.2" stroke-linecap="round"/>
      <path class="sleep-glyph" d="M32 12h6l-5 5h6" stroke="#7EA2C8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  `,
  waking: `
    <svg viewBox="0 0 48 48" fill="none">
      <circle class="wake-ring" cx="24" cy="24" r="17" fill="#E7F5FF" stroke="#3F95DD" stroke-width="2"/>
      <circle cx="18" cy="22" r="2" fill="#0C69B7"/>
      <circle cx="30" cy="22" r="2" fill="#0C69B7"/>
      <path d="M18 31c4 2.2 8 2.2 12 0" stroke="#0C69B7" stroke-width="2.4" stroke-linecap="round"/>
      <path d="M10 14l4-2" stroke="#65C8FF" stroke-width="2.2" stroke-linecap="round"/>
      <path d="M34 12l3 3" stroke="#65C8FF" stroke-width="2.2" stroke-linecap="round"/>
    </svg>
  `,
  active: `
    <svg viewBox="0 0 48 48" fill="none">
      <circle cx="18" cy="24" r="5" fill="#0C69B7"/>
      <circle cx="24" cy="24" r="5" fill="#2A86D4"/>
      <circle cx="30" cy="24" r="5" fill="#65C8FF"/>
      <circle class="run-dot" cx="18" cy="24" r="5" fill="#0C69B7"/>
      <circle class="run-dot" cx="24" cy="24" r="5" fill="#2A86D4"/>
      <circle class="run-dot" cx="30" cy="24" r="5" fill="#65C8FF"/>
    </svg>
  `,
};

const phaseStates = {
  understand_request: "waking",
  create_plan: "waking",
  execute_tools: "active",
  reflect_on_results: "active",
  generate_fix: "active",
  verify_fix: "settling",
};

async function fetchDashboard() {
  const response = await fetch("/api/dashboard");
  if (!response.ok) {
    throw new Error("Failed to load dashboard state.");
  }
  return response.json();
}

async function postPayload(path) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ operator: "web_operator" }),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(payload.detail || "Action failed.");
  }
}

async function postJson(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorPayload = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(errorPayload.detail || "Action failed.");
  }
}

function escapeHtml(value = "") {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderMarkdown(source = "") {
  let html = escapeHtml(source);
  html = html.replace(/^### (.*)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.*)$/gm, "<h3>$1</h3>");
  html = html.replace(/^# (.*)$/gm, "<h3>$1</h3>");
  html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/^- (.*)$/gm, "<li>$1</li>");
  html = html.replace(/<\/li>\n<li>/g, "</li><li>");
  html = html.replace(/(<li>.*<\/li>)/gs, "<ul>$1</ul>");
  html = html
    .split(/\n{2,}/)
    .map((block) => {
      if (block.startsWith("<h3>") || block.startsWith("<ul>")) {
        return block;
      }
      return `<p>${block.replace(/\n/g, "<br />")}</p>`;
    })
    .join("");
  return html;
}

function formatTimestamp(value) {
  if (!value) {
    return "n/a";
  }
  const date = new Date(value);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function renderHero(data) {
  const pipeline = data.pipeline || {};
  const approval = data.approval || {};
  heroStatusCard.classList.remove("danger", "warning");

  if (pipeline.status === "failed") {
    heroStatusCard.classList.add("danger");
    heroStatus.textContent = approval.status === "pending" ? "Approval Required" : "Critical Failure";
    heroSubstatus.textContent = pipeline.summary || "The latest dbt run failed.";
    alarmBanner.classList.remove("hidden");
    alarmTitle.textContent = approval.status === "pending" ? "Remediation Waiting For Human Approval" : "dbt Pipeline Failure";
    alarmDetails.textContent = pipeline.summary || "The system is in a degraded state.";
  } else if (pipeline.status === "succeeded") {
    heroStatus.textContent = "Recovered";
    heroSubstatus.textContent = "The banking pipeline is healthy and the loop is stable.";
    alarmBanner.classList.add("hidden");
  } else if (approval.status === "approved") {
    heroStatusCard.classList.add("warning");
    heroStatus.textContent = "Remediation Armed";
    heroSubstatus.textContent = "A human-approved fix is staged for the next pipeline cycle.";
    alarmBanner.classList.add("hidden");
  } else {
    heroStatus.textContent = "Monitoring";
    heroSubstatus.textContent = "Waiting for the next pipeline run and sensor evaluation.";
    alarmBanner.classList.add("hidden");
  }
}

function getPlayableTimeline(fullTimeline, approval) {
  const filteredTimeline = (fullTimeline || []).filter((item) => item.phase !== "return_final_answer");
  if (approval?.status !== "pending") {
    return filteredTimeline;
  }
  const fixIndex = filteredTimeline.findIndex((item) => item.phase === "generate_fix");
  return fixIndex >= 0 ? filteredTimeline.slice(0, fixIndex + 1) : filteredTimeline;
}

function isTimelinePrefix(previousTimeline, nextTimeline) {
  if (!previousTimeline.length || previousTimeline.length > nextTimeline.length) {
    return false;
  }
  return previousTimeline.every((item, index) => {
    const nextItem = nextTimeline[index];
    return (
      nextItem &&
      item.phase === nextItem.phase &&
      item.title === nextItem.title &&
      item.details === nextItem.details
    );
  });
}

function renderSummary(data) {
  const pipeline = data.pipeline || {};
  const scenario = data.scenario || {};
  const approval = data.approval || {};
  const timeline = playbackTimeline.slice(0, Math.max(playbackIndex + 1, 0));
  const latestPhase = timeline[timeline.length - 1];

  pipelineStatus.textContent = pipeline.status || "idle";
  pipelineSummary.textContent = pipeline.summary || "No pipeline run has been observed yet.";
  scenarioName.textContent = scenario.scenario || "not loaded";
  scenarioDescription.textContent = scenario.description || "Generate a banking scenario to populate the dbt seeds.";
  approvalStatus.textContent = approval.status || "idle";
  timelineCount.textContent = `${timeline.length} phase${timeline.length === 1 ? "" : "s"}`;
  activePhaseSummary.textContent = latestPhase ? latestPhase.title : "The next agent run will paint its workflow here.";

  if (approval.status === "pending") {
    approvalSummary.textContent = "The sensor has proposed a fix and is waiting for a human decision.";
  } else if (approval.status === "approved") {
    approvalSummary.textContent = "A fix was approved and the next cycle should incorporate the remediation.";
  } else if (approval.status === "rejected") {
    approvalSummary.textContent = "The recommendation was rejected. The next failure cycle will generate a new proposal.";
  } else {
    approvalSummary.textContent = "The agent has not requested operator approval yet.";
  }
}

function renderTimeline(data) {
  const timeline = playbackTimeline.slice(0, Math.max(playbackIndex + 1, 0));
  const latest = timeline[timeline.length - 1];

  activePhasePill.textContent = latest ? latest.title : "Idle";

  if (!timeline.length) {
    timelineStrip.innerHTML = '<p class="empty-state">The next agent run will paint its workflow here.</p>';
    agentAvatar.className = "agent-avatar idle";
    agentFace.innerHTML = agentIcons.idle;
    agentStateTitle.textContent = "Sleeping";
    agentStateText.textContent = "The agent is idle and waiting for the next failure signal.";
    return;
  }

  const visualState = phaseStates[latest.phase] || "active";
  agentAvatar.className = `agent-avatar ${visualState === "settling" ? "waking" : visualState}`;
  agentFace.innerHTML = visualState === "active" ? agentIcons.active : agentIcons.waking;
  agentStateTitle.textContent = latest.title;
  agentStateText.innerHTML = renderMarkdown(latest.details);

  timelineStrip.innerHTML = timeline
    .map((item, index) => {
      const activeClass = index === timeline.length - 1 ? "active-phase" : "";
      return `
        <div class="timeline-step ${activeClass}">
          <strong>${index + 1}. ${item.title}</strong>
          <div class="timeline-step-copy">${renderMarkdown(item.details)}</div>
        </div>
      `;
    })
    .join("");
}

function startTimelinePlayback(fullTimeline, approval, pipeline) {
  const rawTimeline = (fullTimeline || []).filter((item) => item.phase !== "return_final_answer");
  const rawSignature = JSON.stringify(rawTimeline.map((item) => [item.phase, item.title, item.details]));
  const playableTimeline = getPlayableTimeline(fullTimeline, approval);
  const playableSignature = JSON.stringify(playableTimeline.map((item) => [item.phase, item.title, item.details]));
  const rawTimelineExtended = isTimelinePrefix(playbackTimeline, playableTimeline);
  const fixStageIndex = playableTimeline.findIndex((item) => item.phase === "generate_fix");

  if (recoverySleepTimer) {
    clearTimeout(recoverySleepTimer);
    recoverySleepTimer = null;
  }

  if (pipeline?.status === "succeeded" && approval?.status !== "pending") {
    playbackTimeline = [];
    playbackIndex = -1;
    playbackSignature = "";
    rawPlaybackSignature = rawSignature;
    dismissedPlaybackSignature = rawSignature;
    return;
  }

  if (
    rawSignature &&
    rawSignature === dismissedPlaybackSignature &&
    pipeline?.status === "succeeded" &&
    approval?.status !== "pending"
  ) {
    playbackTimeline = [];
    playbackIndex = -1;
    playbackSignature = playableSignature;
    rawPlaybackSignature = rawSignature;
    return;
  }

  if (rawSignature !== rawPlaybackSignature && !rawTimelineExtended) {
    rawPlaybackSignature = rawSignature;
    playbackIndex = playableTimeline.length ? 0 : -1;
  } else {
    rawPlaybackSignature = rawSignature;
  }

  if (playableTimeline.length - 1 < playbackIndex) {
    playbackIndex = playableTimeline.length - 1;
  }

  if (approval?.status === "pending" && fixStageIndex >= 0) {
    playbackIndex = Math.max(playbackIndex, fixStageIndex);
  }

  playbackTimeline = playableTimeline;
  playbackSignature = playableSignature;

  if (timelinePlaybackTimer) {
    clearInterval(timelinePlaybackTimer);
    timelinePlaybackTimer = null;
  }

  if (playableTimeline.length <= 1 || playbackIndex >= playableTimeline.length - 1) {
    playbackIndex = playableTimeline.length - 1;
  } else {
    timelinePlaybackTimer = setInterval(() => {
      if (playbackIndex >= playbackTimeline.length - 1) {
        clearInterval(timelinePlaybackTimer);
        timelinePlaybackTimer = null;
        return;
      }
      playbackIndex += 1;
      renderSummary({ pipeline: currentDashboard.pipeline, scenario: currentDashboard.scenario, approval: currentDashboard.approval });
      renderTimeline({ agent_run: { timeline: playbackTimeline } });
    }, 3500);
  }

  if (pipeline?.status === "succeeded" && approval?.status !== "pending" && playableTimeline.length) {
    recoverySleepTimer = setTimeout(() => {
      dismissedPlaybackSignature = rawSignature;
      playbackTimeline = [];
      playbackIndex = -1;
      renderSummary({ pipeline: currentDashboard.pipeline, scenario: currentDashboard.scenario, approval: currentDashboard.approval });
      renderTimeline({ agent_run: { timeline: [] } });
    }, 4500);
  }
}

let currentDashboard = {
  pipeline: {},
  scenario: {},
  approval: {},
};

function renderApproval(data) {
  const approval = data.approval || {};
  const recommendation = approval.recommendation;
  const isPending = approval.status === "pending" && recommendation;
  const visibleTimeline = playbackTimeline.slice(0, Math.max(playbackIndex + 1, 0));
  const hasReachedFixStage = visibleTimeline.some((item) => item.phase === "generate_fix" || item.phase === "verify_fix");
  const showApproval = isPending && hasReachedFixStage;
  approveButton.disabled = !isPending;
  rejectButton.disabled = !isPending;
  approvalPill.textContent = approval.status || "idle";

  approvalPanel.classList.toggle("hidden-panel", !showApproval);
  remediationContextPanel.classList.toggle("hidden-panel", !showApproval);

  if (!showApproval) {
    approvalBody.innerHTML = '<p class="empty-state">No recommendation is waiting for approval.</p>';
    remediationContext.innerHTML = '<p class="empty-state">When the agent proposes a fix, the rationale and actions will appear here.</p>';
    return;
  }

  approvalBody.innerHTML = `
    <div class="approval-card">
      <h3>${recommendation.summary}</h3>
      <p>${recommendation.rationale || "The agent has identified a safe remediation candidate."}</p>
      <ul class="approval-list">
        ${(recommendation.actions || []).map((item) => `<li>${item}</li>`).join("")}
      </ul>
      <p><strong>Requested:</strong> ${formatTimestamp(approval.requested_at)}</p>
      <p><strong>Run ID:</strong> ${approval.run_id || "n/a"}</p>
    </div>
  `;

  remediationContext.innerHTML = renderMarkdown(
    `### Recommended Change\n- Summary: ${recommendation.summary}\n- Rationale: ${recommendation.rationale}\n\n### Actions\n${(recommendation.actions || [])
      .map((item) => `- ${item}`)
      .join("\n")}`
  );
}

function renderEvents(data) {
  const events = data.events || [];
  eventCount.textContent = `${events.length} events`;

  if (!events.length) {
    eventStream.innerHTML = '<p class="empty-state">No runtime events have been recorded yet.</p>';
    return;
  }

  eventStream.innerHTML = events
    .slice()
    .reverse()
    .map(
      (event) => `
        <div class="event-item ${event.severity || "info"}">
          <div class="event-title">
            <strong>${event.title}</strong>
            <span class="event-time">${formatTimestamp(event.timestamp)}</span>
          </div>
          <p>${event.details}</p>
        </div>
      `
    )
    .join("");
}

function renderLogs(data) {
  const lines = data.log_tail || [];
  const hasUserScrolledUp = logView.scrollTop < logView.scrollHeight - logView.clientHeight - 24;
  const focusLines = lines.slice(-10);
  logView.textContent = focusLines.length ? focusLines.join("\n") : "No log lines captured yet.";
  if (!hasUserScrolledUp) {
    logView.scrollTop = logView.scrollHeight;
  }
}

async function refresh() {
  try {
    const data = await fetchDashboard();
    currentDashboard = {
      pipeline: data.pipeline || {},
      scenario: data.scenario || {},
      approval: data.approval || {},
    };
    startTimelinePlayback(data.agent_run?.timeline || [], data.approval || {}, data.pipeline || {});
    renderHero(data);
    renderSummary(data);
    renderTimeline(data);
    renderApproval(data);
    renderEvents(data);
    renderLogs(data);
  } catch (error) {
    console.error(error);
    heroStatus.textContent = "Disconnected";
    heroSubstatus.textContent = "The dashboard could not reach the backend API.";
  }
}

function syncLiveModeButton() {
  liveModeButton.classList.toggle("live-on", liveModeEnabled);
  liveModeButton.classList.toggle("live-off", !liveModeEnabled);
  liveModeLabel.textContent = liveModeEnabled ? "Live Mode: ON" : "Live Mode: PAUSED";
}

function startPolling() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
  }
  refreshTimer = setInterval(refresh, 2500);
}

function stopPolling() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

function setActiveTab(tabName) {
  tabButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tabName);
  });
  tabPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.panel === tabName);
  });
}

approveButton.addEventListener("click", async () => {
  approveButton.disabled = true;
  rejectButton.disabled = true;
  try {
    await postPayload("/api/approval/approve");
    await refresh();
  } catch (error) {
    alert(error.message);
  }
});

rejectButton.addEventListener("click", async () => {
  approveButton.disabled = true;
  rejectButton.disabled = true;
  try {
    await postPayload("/api/approval/reject");
    await refresh();
  } catch (error) {
    alert(error.message);
  }
});

resetButton.addEventListener("click", async () => {
  try {
    await postPayload("/api/reset");
    await refresh();
    setActiveTab("overview");
  } catch (error) {
    alert(error.message);
  }
});

scenarioButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    try {
      await postJson("/api/scenario/load", {
        scenario: button.dataset.scenario,
        reset_incident: true,
        trigger_now: true,
        operator: "web_operator",
      });
      await refresh();
      setActiveTab("overview");
    } catch (error) {
      alert(error.message);
    }
  });
});

liveModeButton.addEventListener("click", async () => {
  liveModeEnabled = !liveModeEnabled;
  syncLiveModeButton();

  if (liveModeEnabled) {
    await refresh();
    startPolling();
  } else {
    stopPolling();
  }
});

tabButtons.forEach((button) => {
  button.addEventListener("click", () => setActiveTab(button.dataset.tab));
});

setActiveTab("overview");
syncLiveModeButton();
refresh();
startPolling();
