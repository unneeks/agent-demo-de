export default function TooltipCard({ analysis }) {
  const topClaim = analysis?.claims?.[0];

  if (!topClaim) {
    return (
      <div className="absolute right-0 top-10 z-20 w-72 rounded-2xl border border-white/10 bg-shell/95 p-4 shadow-glow backdrop-blur">
        <p className="text-sm text-mute">{analysis?.summary ?? "No quick insights available."}</p>
      </div>
    );
  }

  return (
    <div className="absolute right-0 top-10 z-20 w-80 rounded-2xl border border-white/10 bg-shell/95 p-4 shadow-glow backdrop-blur">
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="rounded-full border border-white/10 px-2 py-1 text-[10px] uppercase tracking-[0.18em] text-mute">
          {topClaim.type}
        </span>
        <span className="text-xs text-mute">{Math.round(topClaim.confidence * 100)}% confidence</span>
      </div>
      <p className="text-sm font-medium leading-6 text-text">{topClaim.text}</p>
      <p className="mt-2 text-sm leading-6 text-mute">{topClaim.summary}</p>
    </div>
  );
}
