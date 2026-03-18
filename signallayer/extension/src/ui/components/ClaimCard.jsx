import React from "react";
import { ConfidenceBar } from "./ConfidenceBar.jsx";
import { EvidenceList } from "./EvidenceList.jsx";

export function ClaimCard({ claim }) {
  return (
    <article className="sl-space-y-4 sl-rounded-[28px] sl-border sl-border-white/10 sl-bg-white/5 sl-p-5">
      <div className="sl-flex sl-items-start sl-justify-between sl-gap-3">
        <div>
          <p className="sl-text-[11px] sl-uppercase sl-tracking-[0.2em] sl-text-accent-300">{claim.type}</p>
          <h3 className="sl-mt-2 sl-text-base sl-font-semibold sl-text-white">{claim.text}</h3>
        </div>
      </div>
      <p className="sl-text-sm sl-leading-6 sl-text-slate-300">{claim.summary}</p>
      <div className="sl-rounded-2xl sl-border sl-border-warning/20 sl-bg-warning/10 sl-p-3">
        <p className="sl-text-xs sl-uppercase sl-tracking-[0.18em] sl-text-warning">Counterpoint</p>
        <p className="sl-mt-2 sl-text-sm sl-leading-6 sl-text-slate-200">{claim.counter}</p>
      </div>
      <ConfidenceBar confidence={claim.confidence} />
      <EvidenceList evidence={claim.evidence} />
    </article>
  );
}
