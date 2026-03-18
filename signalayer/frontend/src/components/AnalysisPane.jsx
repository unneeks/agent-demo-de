import ClaimCard from "./ClaimCard.jsx";

export default function AnalysisPane({ message, analysis, onRetry }) {
  if (!message) {
    return (
      <aside className="rounded-[32px] border border-white/10 bg-panel/80 p-6">
        <p className="text-sm text-mute">Select a message badge to inspect its claim analysis.</p>
      </aside>
    );
  }

  return (
    <aside className="h-full rounded-[32px] border border-white/10 bg-panel/80 p-6 shadow-glow backdrop-blur">
      <div className="mb-6">
        <p className="text-[10px] uppercase tracking-[0.24em] text-mute">Analysis Pane</p>
        <h2 className="mt-2 font-display text-2xl text-text">Message reasoning</h2>
        <p className="mt-3 text-sm leading-6 text-mute">{message.text}</p>
      </div>

      <div className="mb-6 rounded-[24px] border border-white/10 bg-white/5 p-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold text-text">
              {analysis?.status === "loading" ? "Deep analysis in progress" : "Reasoning summary"}
            </p>
            <p className="mt-1 text-sm text-mute">{analysis?.summary}</p>
          </div>
          {analysis?.status === "error" ? (
            <button
              type="button"
              className="rounded-full border border-rose-300/30 bg-rose-300/10 px-3 py-2 text-xs text-rose-100"
              onClick={onRetry}
            >
              Retry
            </button>
          ) : null}
        </div>
      </div>

      <div className="space-y-4 overflow-auto pb-6">
        {analysis?.status === "loading" && !analysis?.claims?.length ? (
          <div className="rounded-2xl border border-dashed border-white/10 p-4 text-sm text-mute">
            Running claim extraction, retrieval, and counter-argument generation.
          </div>
        ) : null}

        {analysis?.claims?.length ? (
          analysis.claims.map((claim) => <ClaimCard key={claim.id} claim={claim} />)
        ) : (
          <div className="rounded-2xl border border-dashed border-white/10 p-4 text-sm text-mute">
            No claims to display for this message.
          </div>
        )}
      </div>
    </aside>
  );
}
