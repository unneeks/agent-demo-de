import React from "react";

export function SummaryBar({ title, totalMessages, analyzedMessages, backendStatus }) {
  return (
    <div className="sl-fixed sl-right-5 sl-top-5 sl-z-[2147483645] sl-w-[320px] sl-rounded-[28px] sl-border sl-border-white/10 sl-bg-ink-900/92 sl-p-4 sl-text-white sl-shadow-signal sl-backdrop-blur">
      <p className="sl-text-[11px] sl-uppercase sl-tracking-[0.2em] sl-text-accent-300">SignalLayer</p>
      <h1 className="sl-mt-2 sl-text-base sl-font-semibold">{title}</h1>
      <div className="sl-mt-4 sl-grid sl-grid-cols-3 sl-gap-3 sl-text-center">
        <div className="sl-rounded-2xl sl-bg-white/5 sl-p-3">
          <p className="sl-text-xl sl-font-semibold">{totalMessages}</p>
          <p className="sl-text-[10px] sl-uppercase sl-tracking-[0.18em] sl-text-slate-400">Messages</p>
        </div>
        <div className="sl-rounded-2xl sl-bg-white/5 sl-p-3">
          <p className="sl-text-xl sl-font-semibold">{analyzedMessages}</p>
          <p className="sl-text-[10px] sl-uppercase sl-tracking-[0.18em] sl-text-slate-400">Analyzed</p>
        </div>
        <div className="sl-rounded-2xl sl-bg-white/5 sl-p-3">
          <p className="sl-text-xs sl-font-semibold sl-uppercase sl-tracking-[0.18em]">{backendStatus}</p>
          <p className="sl-text-[10px] sl-uppercase sl-tracking-[0.18em] sl-text-slate-400">Backend</p>
        </div>
      </div>
    </div>
  );
}
