import ConfidenceBar from "./ConfidenceBar.jsx";
import EvidenceList from "./EvidenceList.jsx";

export default function ClaimCard({ claim }) {
  return (
    <article className="rounded-[28px] border border-white/10 bg-white/5 p-5">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <span className="rounded-full border border-white/10 px-2 py-1 text-[10px] uppercase tracking-[0.18em] text-mute">
              {claim.type}
            </span>
            <span className="rounded-full border border-white/10 px-2 py-1 text-[10px] uppercase tracking-[0.18em] text-mute">
              {claim.status}
            </span>
          </div>
          <h3 className="text-base font-semibold leading-7 text-text">{claim.text}</h3>
        </div>
      </div>

      <div className="mb-4">
        <ConfidenceBar value={claim.confidence} />
      </div>

      <p className="mb-4 text-sm leading-6 text-mute">{claim.summary}</p>

      <div className="mb-5 rounded-2xl border border-amber-300/15 bg-amber-300/10 p-4">
        <p className="text-xs uppercase tracking-[0.18em] text-amber-100/75">Counterpoint</p>
        <p className="mt-2 text-sm leading-6 text-amber-50">{claim.counter}</p>
      </div>

      <EvidenceList evidence={claim.evidence} />
    </article>
  );
}
