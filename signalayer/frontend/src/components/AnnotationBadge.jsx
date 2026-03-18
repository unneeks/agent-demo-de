const iconByType = {
  factual: "✔",
  opinion: "🧠",
  prediction: "📊",
  error: "⚠"
};

const toneByType = {
  factual: "border-emerald-400/35 bg-emerald-400/15 text-emerald-100",
  opinion: "border-cyan-400/35 bg-cyan-400/15 text-cyan-100",
  prediction: "border-amber-400/35 bg-amber-400/15 text-amber-100",
  error: "border-rose-400/35 bg-rose-400/15 text-rose-100"
};

export default function AnnotationBadge({ claim, active, onClick, onHoverChange }) {
  const type = claim?.type ?? "error";

  return (
    <button
      type="button"
      className={`inline-flex h-7 min-w-7 items-center justify-center rounded-full border px-2 text-xs font-semibold transition ${
        toneByType[type]
      } ${active ? "scale-105 shadow-glow" : "opacity-90 hover:opacity-100"}`}
      onClick={onClick}
      onMouseEnter={() => onHoverChange(true)}
      onMouseLeave={() => onHoverChange(false)}
      onFocus={() => onHoverChange(true)}
      onBlur={() => onHoverChange(false)}
      aria-label={`Open ${type} claim analysis`}
      title={claim?.summary ?? "Open analysis"}
    >
      <span aria-hidden="true">{iconByType[type]}</span>
    </button>
  );
}
