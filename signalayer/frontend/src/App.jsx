import { useEffect, useRef, useState } from "react";
import AnalysisPane from "./components/AnalysisPane.jsx";
import ConversationSummaryBar from "./components/ConversationSummaryBar.jsx";
import MessageDecorator from "./components/MessageDecorator.jsx";
import { conversationFixture } from "../../shared/chatFixtures.js";
import { createInitialAnalysisState } from "../../shared/analysisState.js";
import { quickAnalyzeMessage } from "../../shared/localAnalysis.js";
import { analyzeMessage } from "./lib/api.js";
import { hashMessage } from "../../shared/hash.js";

function createDraftMessage(text, index) {
  return {
    id: `msg-live-${index}`,
    author: "You",
    text,
    timestamp: new Date().toISOString()
  };
}

function mergeAnalysis(previous, payload) {
  return {
    ...previous,
    status: "ready",
    summary: payload.summary,
    claims: payload.claims,
    latencyMs: payload.meta?.latencyMs ?? 0,
    source: payload.meta?.cacheHit ? "cache" : "backend"
  };
}

export default function App() {
  const [messages, setMessages] = useState(conversationFixture.messages);
  const [analysisByMessage, setAnalysisByMessage] = useState(() =>
    createInitialAnalysisState(conversationFixture.messages)
  );
  const [selectedMessageId, setSelectedMessageId] = useState(conversationFixture.messages[0]?.id ?? null);
  const [hoveredMessageId, setHoveredMessageId] = useState(null);
  const [draft, setDraft] = useState("");
  const inFlight = useRef(new Set());

  useEffect(() => {
    messages.forEach((message) => {
      const analysis = analysisByMessage[message.id];

      if (!analysis || analysis.status !== "loading" || inFlight.current.has(message.id)) {
        return;
      }

      inFlight.current.add(message.id);

      analyzeMessage(message, messages)
        .then((payload) => {
          setAnalysisByMessage((current) => ({
            ...current,
            [message.id]: mergeAnalysis(current[message.id], payload)
          }));
        })
        .catch(() => {
          setAnalysisByMessage((current) => ({
            ...current,
            [message.id]: {
              ...current[message.id],
              status: "error",
              summary: "The backend analysis failed. Local badge signals are still available."
            }
          }));
        })
        .finally(() => {
          inFlight.current.delete(message.id);
        });
    });
  }, [analysisByMessage, messages]);

  function retryMessageAnalysis(messageId) {
    const message = messages.find((item) => item.id === messageId);

    if (!message) {
      return;
    }

    const local = quickAnalyzeMessage(message.text);
    setAnalysisByMessage((current) => ({
      ...current,
      [messageId]: {
        ...current[messageId],
        hash: hashMessage(message.text),
        status: local.claims.length > 0 ? "loading" : "idle",
        summary: local.summary,
        claims: local.claims
      }
    }));
  }

  function sendMessage(event) {
    event.preventDefault();

    if (!draft.trim()) {
      return;
    }

    const message = createDraftMessage(draft.trim(), messages.length + 1);
    const localState = createInitialAnalysisState([message])[message.id];

    setMessages((current) => [...current, message]);
    setAnalysisByMessage((current) => ({
      ...current,
      [message.id]: localState
    }));
    setSelectedMessageId(message.id);
    setDraft("");
  }

  const selectedMessage = messages.find((item) => item.id === selectedMessageId) ?? null;
  const selectedAnalysis = selectedMessage ? analysisByMessage[selectedMessage.id] : null;

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(101,215,196,0.18),_transparent_28%),linear-gradient(180deg,_#08111f_0%,_#0f1728_55%,_#08111f_100%)] text-text">
      <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col gap-6 px-4 py-6 lg:px-8">
        <header className="rounded-[34px] border border-white/10 bg-white/5 p-6">
          <p className="text-[10px] uppercase tracking-[0.24em] text-mute">SignalLayer MVP</p>
          <div className="mt-3 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h1 className="font-display text-4xl text-text">Conversation augmentation, built into chat.</h1>
              <p className="mt-3 max-w-3xl text-sm leading-7 text-mute">
                This version replaces the WhatsApp overlay with a first-party chat surface while preserving inline badges,
                hover insights, a summary rail, and a right-side reasoning pane.
              </p>
            </div>
            <div className="rounded-[24px] border border-white/10 bg-ink/70 px-4 py-3 text-sm text-mute">
              Two-pass pipeline: local detection first, async backend reasoning second.
            </div>
          </div>
        </header>

        <ConversationSummaryBar analyses={Object.values(analysisByMessage)} />

        <div className="grid flex-1 gap-6 lg:grid-cols-[minmax(0,1.1fr)_420px]">
          <section className="rounded-[34px] border border-white/10 bg-white/5 p-5">
            <div className="mb-5 flex items-center justify-between gap-4">
              <div>
                <p className="text-[10px] uppercase tracking-[0.24em] text-mute">{conversationFixture.title}</p>
                <h2 className="mt-2 font-display text-2xl text-text">Live annotated chat</h2>
              </div>
              <div className="rounded-full border border-white/10 px-3 py-2 text-xs text-mute">
                {messages.length} messages
              </div>
            </div>

            <div className="space-y-4">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className="block w-full cursor-pointer text-left"
                  onClick={() => setSelectedMessageId(message.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedMessageId(message.id);
                    }
                  }}
                  role="button"
                  tabIndex={0}
                >
                  <MessageDecorator
                    message={message}
                    analysis={analysisByMessage[message.id]}
                    active={selectedMessageId === message.id}
                    tooltipVisible={hoveredMessageId === message.id}
                    onOpen={() => setSelectedMessageId(message.id)}
                    onHoverChange={(visible) => setHoveredMessageId(visible ? message.id : null)}
                  />
                </div>
              ))}
            </div>

            <form className="mt-6 rounded-[28px] border border-white/10 bg-ink/70 p-4" onSubmit={sendMessage}>
              <label className="mb-3 block text-[10px] uppercase tracking-[0.24em] text-mute" htmlFor="composer">
                New message
              </label>
              <div className="flex flex-col gap-3 md:flex-row">
                <textarea
                  id="composer"
                  className="min-h-24 flex-1 rounded-[22px] border border-white/10 bg-white/5 px-4 py-3 text-sm text-text outline-none transition placeholder:text-mute focus:border-accent/40"
                  placeholder="Type a message with a fact, opinion, or prediction to see SignalLayer annotate it."
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                />
                <button
                  type="submit"
                  className="rounded-[22px] bg-accent px-5 py-3 text-sm font-semibold text-ink transition hover:brightness-110"
                >
                  Send and analyze
                </button>
              </div>
            </form>
          </section>

          <AnalysisPane
            message={selectedMessage}
            analysis={selectedAnalysis}
            onRetry={() => retryMessageAnalysis(selectedMessageId)}
          />
        </div>
      </div>
    </div>
  );
}
