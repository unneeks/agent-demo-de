import React from "react";

export function TooltipCard({ tooltip }) {
  if (!tooltip) {
    return null;
  }

  return (
    <div
      className="sl-fixed sl-z-[2147483647] sl-w-72 sl-rounded-[24px] sl-border sl-border-white/10 sl-bg-ink-900/95 sl-p-4 sl-text-white sl-shadow-signal sl-backdrop-blur"
      style={{
        top: `${tooltip.y}px`,
        left: `${tooltip.x}px`
      }}
    >
      <p className="sl-text-[11px] sl-uppercase sl-tracking-[0.18em] sl-text-accent-300">
        {tooltip.title}
      </p>
      <p className="sl-mt-2 sl-text-sm sl-leading-6 sl-text-slate-200">{tooltip.body}</p>
    </div>
  );
}
