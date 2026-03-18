export default function EvidenceList({ evidence }) {
  if (!evidence?.length) {
    return (
      <div className="rounded-2xl border border-dashed border-white/10 bg-white/5 p-4 text-sm text-mute">
        No supporting evidence was retrieved for this claim yet.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {evidence.map((item, index) => (
        <article
          key={`${item.title}-${index}`}
          className="rounded-2xl border border-white/10 bg-white/5 p-4"
        >
          <div className="mb-2 flex items-center justify-between gap-3">
            <h4 className="text-sm font-semibold text-text">{item.title}</h4>
            <span className="rounded-full border border-white/10 px-2 py-1 text-[10px] uppercase tracking-[0.18em] text-mute">
              {item.sourceType}
            </span>
          </div>
          <p className="text-sm leading-6 text-mute">{item.snippet}</p>
        </article>
      ))}
    </div>
  );
}
