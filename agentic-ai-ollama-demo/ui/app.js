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
const timelineStrip = document.getElementById("timeline-strip");
const timelineDetail = document.getElementById("timeline-detail");
const approvalPill = document.getElementById("approval-pill");
const approvalBody = document.getElementById("approval-body");
const approveButton = document.getElementById("approve-button");
const rejectButton = document.getElementById("reject-button");
const eventCount = document.getElementById("event-count");
const eventStream = document.getElementById("event-stream");
const logView = document.getElementById("log-view");

async function fetchDashboard() {
  const response = await fetch("/api/dashboard");
  if (!response.ok) {
    throw new Error("Failed to load dashboard state.");
  }
  return response.json();
}

async function postApproval(path) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ operator: "web_operator" }),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(payload.detail || "Approval action failed.");
  }
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
    alarmTitle.textContent = approval.status === "pending" ? "Agent Fix Waiting For Human Approval" : "dbt Pipeline Failure";
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

function renderStats(data) {
  const pipeline = data.pipeline || {};
  const scenario = data.scenario || {};
  const approval = data.approval || {};

  pipelineStatus.textContent = pipeline.status || "idle";
  pipelineSummary.textContent = pipeline.summary || "No pipeline run has been observed yet.";
  scenarioName.textContent = scenario.scenario || "not loaded";
  scenarioDescription.textContent = scenario.description || "Generate a banking scenario to populate the dbt seeds.";
  approvalStatus.textContent = approval.status || "idle";

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
  const timeline = data.agent_run?.timeline || [];
  timelineCount.textContent = `${timeline.length} phase${timeline.length === 1 ? "" : "s"}`;

  if (!timeline.length) {
    timelineStrip.innerHTML = "";
    timelineDetail.innerHTML = '<p class="empty-state">The next agent run will paint its workflow here.</p>';
    return;
  }

  timelineStrip.innerHTML = timeline
    .map(
      (item, index) => `
        <div class="timeline-step">
          <strong>${index + 1}. ${item.title}</strong>
          <p>${item.details}</p>
        </div>
      `
    )
    .join("");

  const latest = timeline[timeline.length - 1];
  timelineDetail.innerHTML = `
    <p class="muted-label">Latest Phase</p>
    <h3>${latest.title}</h3>
    <p>${latest.details}</p>
  `;
}

function renderApproval(data) {
  const approval = data.approval || {};
  const recommendation = approval.recommendation;
  const isPending = approval.status === "pending" && recommendation;
  approveButton.disabled = !isPending;
  rejectButton.disabled = !isPending;
  approvalPill.textContent = approval.status || "idle";

  if (!recommendation) {
    approvalBody.innerHTML = '<p class="empty-state">No recommendation is waiting for approval.</p>';
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
  logView.textContent = lines.length ? lines.join("\n") : "No log lines captured yet.";
}

async function refresh() {
  try {
    const data = await fetchDashboard();
    renderHero(data);
    renderStats(data);
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

approveButton.addEventListener("click", async () => {
  approveButton.disabled = true;
  rejectButton.disabled = true;
  try {
    await postApproval("/api/approval/approve");
    await refresh();
  } catch (error) {
    alert(error.message);
  }
});

rejectButton.addEventListener("click", async () => {
  approveButton.disabled = true;
  rejectButton.disabled = true;
  try {
    await postApproval("/api/approval/reject");
    await refresh();
  } catch (error) {
    alert(error.message);
  }
});

refresh();
setInterval(refresh, 2500);
