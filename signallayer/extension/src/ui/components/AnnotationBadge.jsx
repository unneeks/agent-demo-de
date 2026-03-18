import React from "react";

const badgeMap = {
  neutral: { icon: "○", tone: "bg-white/10 text-slate-200 border-white/10" },
  claim: { icon: "⚠", tone: "bg-warning/20 text-warning border-warning/40" },
  prediction: { icon: "📊", tone: "bg-accent-500/20 text-accent-300 border-accent-400/40" },
  reasoning: { icon: "🧠", tone: "bg-success/20 text-success border-success/40" },
  error: { icon: "!", tone: "bg-danger/20 text-danger border-danger/40" }
};

export function AnnotationBadge({ tone = "neutral", label, onHover, onLeave, onClick }) {
  const config = badgeMap[tone] || badgeMap.neutral;
  return (
    <button
      type="button"
      className={`sl-inline-flex sl-h-6 sl-w-6 sl-items-center sl-justify-center sl-rounded-full sl-border sl-text-[12px] sl-shadow-sm sl-transition hover:sl-scale-105 ${config.tone}`}
      aria-label={label}
      onMouseEnter={onHover}
      onMouseLeave={onLeave}
      onClick={onClick}
    >
      <span>{config.icon}</span>
    </button>
  );
}
