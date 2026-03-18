import React from "react";

export function ConfidenceBar({ confidence = 0 }) {
  const pct = Math.max(0, Math.min(100, Math.round(confidence * 100)));
  const tone = pct >= 70 ? "bg-success" : pct >= 40 ? "bg-warning" : "bg-danger";

  return (
    <div className="sl-space-y-1">
      <div className="sl-flex sl-items-center sl-justify-between sl-text-[11px] sl-uppercase sl-tracking-[0.18em] sl-text-slate-400">
        <span>Confidence</span>
        <span>{pct}%</span>
      </div>
      <div className="sl-h-2 sl-overflow-hidden sl-rounded-full sl-bg-white/10">
        <div className={`sl-h-full sl-rounded-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
