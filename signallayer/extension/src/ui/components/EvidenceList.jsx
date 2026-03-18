import React from "react";

const stanceTone = {
  supporting: "sl-text-success",
  conflicting: "sl-text-danger",
  context: "sl-text-accent-300"
};

export function EvidenceList({ evidence = [] }) {
  if (!evidence.length) {
    return <p className="sl-text-sm sl-text-slate-400">No evidence retrieved yet.</p>;
  }

  return (
    <div className="sl-space-y-2">
      {evidence.map((item, index) => (
        <div key={`${item.title}-${index}`} className="sl-rounded-2xl sl-border sl-border-white/10 sl-bg-white/5 sl-p-3">
          <div className="sl-flex sl-items-center sl-justify-between sl-gap-3">
            <p className="sl-text-sm sl-font-medium sl-text-white">{item.title}</p>
            <span className={`sl-text-[11px] sl-uppercase sl-tracking-[0.18em] ${stanceTone[item.stance] || stanceTone.context}`}>
              {item.stance}
            </span>
          </div>
          <p className="sl-mt-2 sl-text-sm sl-leading-6 sl-text-slate-300">{item.snippet}</p>
        </div>
      ))}
    </div>
  );
}
