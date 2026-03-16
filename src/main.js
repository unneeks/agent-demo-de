import { traditions } from "./data/traditions.js";
import { runTraditionQuery } from "./domain/queryEngine.js";
import {
  getTraditionEndYear,
  scaleYear,
  sortTraditionsForTimeline,
  TIMELINE_END,
  TIMELINE_START
} from "./domain/timeline.js";
import { buildSynchronologyBands, getSynchronologyLayout } from "./domain/synchronology.js";
import { summarizeTradition, validateTradition } from "./domain/traditionModel.js";

const timelineRoot = document.getElementById("timeline-root");
const detailPanel = document.getElementById("detail-panel");
const queryInput = document.getElementById("query-input");
const querySummary = document.getElementById("query-summary");
const runQueryButton = document.getElementById("run-query-button");
const presetButtons = Array.from(document.querySelectorAll(".preset-chip"));
const viewButtons = Array.from(document.querySelectorAll(".view-toggle"));
const vizTitle = document.getElementById("viz-title");
const vizDescription = document.getElementById("viz-description");

let currentView = "timeline";
let currentResults = traditions;

const layerColors = {
  "local-ritual": "#6f8f72",
  vedic: "#d68c45",
  brahmanical: "#b55d3d",
  sramana: "#4f7ca8",
  temple: "#8e6bbf",
  "regional-devotional": "#c05c7a",
  tantric: "#6a4c93",
  bhakti: "#d94f70",
  modern: "#2a7f62"
};

const viewConfig = {
  timeline: {
    title: "Timeline River",
    description:
      "Each row is a tradition stream, plotted from approximate origin to decline or present. Colors encode civilizational layer.",
    render: renderTimeline
  },
  synchronology: {
    title: "Synchronological Chart",
    description:
      "A scrollable parallel-history view inspired by nineteenth-century synchronological charts: category bands run against the same time axis.",
    render: renderSynchronology
  }
};

function bootstrap() {
  const invalid = traditions.flatMap((tradition) =>
    validateTradition(tradition).map((message) => `${tradition.id}: ${message}`)
  );

  if (invalid.length > 0) {
    timelineRoot.innerHTML = `<p class="error">${invalid.join("<br />")}</p>`;
    return;
  }

  applyQuery("");
  bindEvents();
}

function bindEvents() {
  runQueryButton.addEventListener("click", () => applyQuery(queryInput.value));
  queryInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      applyQuery(queryInput.value);
    }
  });

  presetButtons.forEach((button) => {
    button.addEventListener("click", () => {
      queryInput.value = button.dataset.query ?? "";
      applyQuery(queryInput.value);
    });
  });

  viewButtons.forEach((button) => {
    button.addEventListener("click", () => {
      setCurrentView(button.dataset.view ?? "timeline");
    });
  });
}

function applyQuery(query) {
  const { results, summary } = runTraditionQuery(traditions, query);
  currentResults = results;
  querySummary.textContent = summary;
  renderActiveView();

  if (results.length > 0) {
    renderDetail(results[0]);
  } else {
    detailPanel.innerHTML = "<p>No traditions matched the current query.</p>";
  }
}

function setCurrentView(view) {
  currentView = viewConfig[view] ? view : "timeline";
  viewButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === currentView);
  });
  renderActiveView();
}

function renderActiveView() {
  const config = viewConfig[currentView];
  vizTitle.textContent = config.title;
  vizDescription.textContent = config.description;
  config.render(currentResults);
}

function renderTimeline(filteredTraditions) {
  const ordered = sortTraditionsForTimeline(filteredTraditions);
  const width = 960;
  const rowHeight = 48;
  const topPadding = 64;
  const leftLabelWidth = 220;
  const height = topPadding + ordered.length * rowHeight + 24;
  const chartWidth = width - leftLabelWidth - 48;

  const ticks = [-1500, -1000, -500, 0, 500, 1000, 1500, 2026];
  const axis = ticks
    .map((tick) => {
      const x = leftLabelWidth + scaleYear(tick, chartWidth);
      return `
        <line x1="${x}" y1="30" x2="${x}" y2="${height - 24}" class="axis-line" />
        <text x="${x}" y="20" text-anchor="middle" class="axis-label">${formatYear(tick)}</text>
      `;
    })
    .join("");

  const rows = ordered
    .map((tradition, index) => {
      const y = topPadding + index * rowHeight;
      const startX = leftLabelWidth + scaleYear(tradition.originTime, chartWidth);
      const endX = leftLabelWidth + scaleYear(getTraditionEndYear(tradition), chartWidth);
      const color = layerColors[tradition.civilizationalLayer] ?? "#888";
      const widthValue = Math.max(12, endX - startX);

      return `
        <g class="timeline-row" data-id="${tradition.id}">
          <text x="12" y="${y + 18}" class="row-label">${tradition.name}</text>
          <text x="12" y="${y + 34}" class="row-meta">${tradition.category}</text>
          <rect
            x="${startX}"
            y="${y}"
            width="${widthValue}"
            height="22"
            rx="11"
            fill="${color}"
            opacity="0.92"
          />
          <text x="${startX + 10}" y="${y + 15}" class="stream-label">${formatCompactRange(tradition)}</text>
        </g>
      `;
    })
    .join("");

  timelineRoot.innerHTML = `
    <svg
      class="timeline-svg"
      viewBox="0 0 ${width} ${height}"
      role="img"
      aria-label="Civilization timeline"
    >
      <rect x="0" y="0" width="${width}" height="${height}" class="timeline-bg" />
      ${axis}
      ${rows}
    </svg>
  `;

  timelineRoot.querySelectorAll(".timeline-row").forEach((row) => {
    row.addEventListener("click", () => {
      const selected = filteredTraditions.find((item) => item.id === row.dataset.id);
      if (selected) renderDetail(selected);
    });
  });
}

function renderSynchronology(filteredTraditions) {
  const bands = buildSynchronologyBands(filteredTraditions);
  const pixelsPerYear = 0.42;
  const axisTicks = [-1500, -1000, -500, 0, 500, 1000, 1500, 2026];
  const chartWidth = Math.round((TIMELINE_END - TIMELINE_START) * pixelsPerYear);

  const axis = axisTicks
    .map((tick) => {
      const offset = Math.round((tick - TIMELINE_START) * pixelsPerYear);
      return `
        <div class="sync-axis-tick" style="left:${offset}px">
          <span>${formatYear(tick)}</span>
        </div>
      `;
    })
    .join("");

  const rows = bands
    .map((band) => {
      const cards = band.items
        .map((tradition) => {
          const layout = getSynchronologyLayout(tradition, pixelsPerYear);
          const color = layerColors[tradition.civilizationalLayer] ?? "#888";

          return `
            <button
              class="sync-card"
              data-id="${tradition.id}"
              type="button"
              style="left:${layout.left}px;width:${layout.width}px;border-color:${color};background:${withAlpha(color, 0.15)}"
            >
              <span class="sync-card-name">${tradition.name}</span>
              <span class="sync-card-range">${formatCompactRange(tradition)}</span>
            </button>
          `;
        })
        .join("");

      return `
        <section class="sync-band">
          <div class="sync-band-label">
            <p class="sync-band-title">${band.title}</p>
            <p class="sync-band-meta">${band.items.length} traditions</p>
          </div>
          <div class="sync-band-chart">
            <div class="sync-axis">${axis}</div>
            <div class="sync-cards" style="width:${chartWidth}px">${cards}</div>
          </div>
        </section>
      `;
    })
    .join("");

  timelineRoot.innerHTML = `
    <div class="sync-chart-shell">
      <div class="sync-intro">
        <p>
          Scroll horizontally to compare category bands against the same chronology.
          Click any card to inspect the selected tradition.
        </p>
      </div>
      <div class="sync-grid">${rows}</div>
    </div>
  `;

  timelineRoot.querySelectorAll(".sync-card").forEach((card) => {
    card.addEventListener("click", () => {
      const selected = filteredTraditions.find((item) => item.id === card.dataset.id);
      if (selected) renderDetail(selected);
    });
  });
}

function renderDetail(tradition) {
  detailPanel.innerHTML = `
    <h3>${tradition.name}</h3>
    <p class="detail-summary">${summarizeTradition(tradition)}</p>
    <dl class="detail-grid">
      <div>
        <dt>Origin</dt>
        <dd>${tradition.geographicOrigin}</dd>
      </div>
      <div>
        <dt>Vedic Relation</dt>
        <dd>${tradition.vedicRelation}</dd>
      </div>
      <div>
        <dt>Ritual</dt>
        <dd>${tradition.ritualStructure}</dd>
      </div>
      <div>
        <dt>Institutions</dt>
        <dd>${tradition.institutionalStrength.start} to ${tradition.institutionalStrength.end}</dd>
      </div>
      <div>
        <dt>Regions</dt>
        <dd>${tradition.regions.join(", ")}</dd>
      </div>
      <div>
        <dt>Confidence</dt>
        <dd>${tradition.confidence}</dd>
      </div>
    </dl>
    <p class="detail-note">${tradition.notes}</p>
  `;
}

function formatYear(year) {
  if (year < 0) return `${Math.abs(year)} BCE`;
  if (year === 0) return "0";
  return `${year} CE`;
}

function formatCompactRange(tradition) {
  return `${formatShortYear(tradition.originTime)} - ${formatShortYear(
    getTraditionEndYear(tradition)
  )}`;
}

function formatShortYear(year) {
  if (year === TIMELINE_END) return "present";
  if (year < 0) return `${Math.abs(year)} BCE`;
  return `${year} CE`;
}

function withAlpha(hex, alpha) {
  const normalized = hex.replace("#", "");
  const parts =
    normalized.length === 3
      ? normalized.split("").map((value) => parseInt(`${value}${value}`, 16))
      : [
          parseInt(normalized.slice(0, 2), 16),
          parseInt(normalized.slice(2, 4), 16),
          parseInt(normalized.slice(4, 6), 16)
        ];

  return `rgba(${parts[0]}, ${parts[1]}, ${parts[2]}, ${alpha})`;
}

bootstrap();
