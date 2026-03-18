export default function ConfidenceBar({ value }) {
  const clamped = Math.max(0, Math.min(1, value || 0));
  const tone =
    clamped >= 0.75 ? "bg-emerald-400" : clamped >= 0.55 ? "bg-amber-300" : "bg-rose-300";

  return (
    <div className="flex items-center gap-3">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/10">
        <div
          className={`h-full rounded-full ${tone} transition-all`}
          style={{ width: `${Math.round(clamped * 100)}%` }}
        />
      </div>
      <span className="w-12 text-right text-xs text-mute">{Math.round(clamped * 100)}%</span>
    </div>
  );
}
