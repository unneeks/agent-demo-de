import React from "react";
import { createRoot } from "react-dom/client";
import { analyzeMessage as requestAnalysis } from "../lib/api.js";
import { ResultCache } from "../lib/cache.js";
import { getConversationTitle, parseMessageNodes } from "../lib/parser.js";
import {
  closeAnalysisPane,
  getMessageViewModels,
  getState,
  hideTooltip,
  openAnalysisPane,
  setAnalysis,
  setBackendStatus,
  setConversationTitle,
  showTooltip,
  subscribe,
  upsertMessages
} from "../lib/store.js";
import { MessageDecorator } from "../ui/components/MessageDecorator.jsx";
import { TooltipCard } from "../ui/components/TooltipCard.jsx";
import { AnalysisPane } from "../ui/components/AnalysisPane.jsx";
import { SummaryBar } from "../ui/components/SummaryBar.jsx";

const cache = new ResultCache();
const decoratorRoots = new Map();
const analyzedHashes = new Set();

function ensureShadowShell() {
  let host = document.getElementById("signallayer-root");
  if (!host) {
    host = document.createElement("div");
    host.id = "signallayer-root";
    document.body.appendChild(host);
  }

  const shadow = host.shadowRoot || host.attachShadow({ mode: "open" });

  if (!shadow.getElementById("signallayer-styles")) {
    const link = document.createElement("link");
    link.id = "signallayer-styles";
    link.rel = "stylesheet";
    link.href = chrome.runtime.getURL("styles.css");
    shadow.appendChild(link);
  }

  let appRoot = shadow.getElementById("signallayer-app");
  if (!appRoot) {
    appRoot = document.createElement("div");
    appRoot.id = "signallayer-app";
    appRoot.className = "sl-shell";
    shadow.appendChild(appRoot);
  }

  return appRoot;
}

function App() {
  const snapshot = React.useSyncExternalStore(subscribe, getState, getState);
  const selectedMessage = getMessageViewModels().find((message) => message.id === snapshot.activeMessageId) || null;

  return (
    <>
      <SummaryBar
        title={snapshot.conversationTitle}
        totalMessages={snapshot.messages.length}
        analyzedMessages={Object.keys(snapshot.analysisById).length}
        backendStatus={snapshot.backendStatus}
      />
      <TooltipCard tooltip={snapshot.tooltip} />
      {snapshot.activeMessageId && (
        <AnalysisPane
          message={selectedMessage}
          analysis={selectedMessage?.analysis || null}
          onClose={() => closeAnalysisPane()}
        />
      )}
    </>
  );
}

function ensureDecoratorAnchor(message) {
  let anchor = message.node.querySelector(".sl-anchor");
  if (!anchor) {
    anchor = document.createElement("span");
    anchor.className = "sl-anchor";
    anchor.setAttribute("data-signallayer-anchor", "true");
    const target =
      message.node.querySelector("div.copyable-text") ||
      message.node.querySelector("span.selectable-text") ||
      message.node;
    target.appendChild(anchor);
  }
  return anchor;
}

function renderDecorator(message) {
  const anchor = ensureDecoratorAnchor(message);
  const existing = decoratorRoots.get(message.id);
  const root = existing || createRoot(anchor);
  if (!existing) {
    decoratorRoots.set(message.id, root);
  }

  const analysis = getState().analysisById[message.id] || null;

  root.render(
    <MessageDecorator
      analysis={analysis}
      onHover={(event) => {
        const rect = event.currentTarget.getBoundingClientRect();
        const claim = analysis?.claims?.[0];
        showTooltip({
          x: rect.left - 280,
          y: rect.top + window.scrollY - 8,
          title: analysis?.status === "ok" ? "Quick insight" : "Signal status",
          body:
            claim?.summary ||
            (analysis?.status === "error"
              ? "Backend unavailable. Using local signal only."
              : analysis?.status === "no_claims"
                ? "No strong claim detected."
                : "Fast pass detected a message worth reviewing.")
        });
      }}
      onLeave={() => hideTooltip()}
      onOpen={() => openAnalysisPane(message.id)}
    />
  );
}

async function analyzeAndRender(message, allMessages) {
  const cached = cache.get(message.messageHash);
  if (cached) {
    setAnalysis(message.id, cached);
    renderDecorator(message);
    return;
  }

  if (analyzedHashes.has(message.messageHash)) {
    renderDecorator(message);
    return;
  }

  analyzedHashes.add(message.messageHash);
  setBackendStatus("online");
  renderDecorator(message);

  try {
    const context = allMessages
      .filter((item) => item.id !== message.id)
      .slice(-5)
      .map((item) => ({
        id: item.id,
        text: item.text,
        author: item.author
      }));

    const analysis = await requestAnalysis({
      message: message.text,
      context,
      messageId: message.id,
      conversationId: message.conversationId,
      messageHash: message.messageHash
    });

    cache.set(message.messageHash, analysis);
    setAnalysis(message.id, analysis);
  } catch (error) {
    setBackendStatus("offline");
    setAnalysis(message.id, {
      messageId: message.id,
      messageHash: message.messageHash,
      status: "error",
      fastPass: {
        hasClaims: true,
        signal: "mixed",
        badges: ["error"]
      },
      claims: [],
      meta: {
        latencyMs: 0,
        cache: "miss",
        reasoningMode: "heuristic"
      }
    });
  }

  renderDecorator(message);
}

function scanMessages() {
  const messages = parseMessageNodes();

  setConversationTitle(getConversationTitle());
  upsertMessages(messages);

  const viewModels = getMessageViewModels();
  for (const message of viewModels) {
    renderDecorator(message);
    void analyzeAndRender(message, viewModels);
  }
}

function initObserver() {
  const observer = new MutationObserver(() => {
    window.requestAnimationFrame(scanMessages);
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true
  });
}

function bootstrap() {
  const appRoot = ensureShadowShell();
  createRoot(appRoot).render(<App />);
  scanMessages();
  initObserver();
}

bootstrap();
