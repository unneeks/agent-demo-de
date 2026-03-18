import React from "react";
import { ClaimCard } from "./ClaimCard.jsx";

export function AnalysisPane({ message, analysis, onClose }) {
  return (
    <aside className="sl-fixed sl-right-0 sl-top-0 sl-z-[2147483646] sl-flex sl-h-screen sl-w-[380px] sl-flex-col sl-border-l sl-border-white/10 sl-bg-ink-950/95 sl-p-5 sl-text-white sl-shadow-signal sl-backdrop-blur">
      <div className="sl-flex sl-items-start sl-justify-between sl-gap-3">
        <div>
          <p className="sl-text-[11px] sl-uppercase sl-tracking-[0.18em] sl-text-accent-300">SignalLayer</p>
          <h2 className="sl-mt-2 sl-text-lg sl-font-semibold">Message analysis</h2>
        </div>
        <button type="button" className="sl-rounded-full sl-border sl-border-white/10 sl-px-3 sl-py-1 sl-text-sm sl-text-slate-300" onClick={onClose}>
          Close
        </button>
      </div>

      <div className="sl-mt-5 sl-rounded-[28px] sl-border sl-border-white/10 sl-bg-white/5 sl-p-4">
        <p className="sl-text-[11px] sl-uppercase sl-tracking-[0.18em] sl-text-slate-400">Original message</p>
        <p className="sl-mt-3 sl-text-sm sl-leading-6 sl-text-slate-200">{message?.text || "No message selected."}</p>
      </div>

      <div className="sl-mt-4 sl-flex-1 sl-space-y-4 sl-overflow-y-auto sl-pr-1">
        {!analysis && <p className="sl-text-sm sl-text-slate-400">Deep analysis is loading.</p>}
        {analysis?.status === "error" && (
          <div className="sl-rounded-[24px] sl-border sl-border-danger/30 sl-bg-danger/10 sl-p-4 sl-text-sm sl-text-slate-200">
            SignalLayer could not reach the analysis backend. Keep the badge as a hint and retry when the service is available.
          </div>
        )}
        {analysis?.status === "no_claims" && (
          <div className="sl-rounded-[24px] sl-border sl-border-white/10 sl-bg-white/5 sl-p-4 sl-text-sm sl-text-slate-200">
            No strong claim candidates were detected in this message.
          </div>
        )}
        {analysis?.claims?.map((claim) => <ClaimCard key={claim.id} claim={claim} />)}
      </div>
    </aside>
  );
}
