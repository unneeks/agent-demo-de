import AnnotationBadge from "./AnnotationBadge.jsx";
import TooltipCard from "./TooltipCard.jsx";

export default function MessageDecorator({
  message,
  analysis,
  active,
  tooltipVisible,
  onOpen,
  onHoverChange
}) {
  const bubbleTone =
    message.author === "Maya"
      ? "bg-accent/15 border-accent/20"
      : message.author === "Jon"
        ? "bg-cyan-400/10 border-cyan-400/15"
        : "bg-white/5 border-white/10";

  return (
    <article className="relative">
      <div className={`rounded-[28px] border ${bubbleTone} px-4 py-3`}>
        <div className="mb-2 flex items-center justify-between gap-3">
          <span className="text-sm font-semibold text-text">{message.author}</span>
          <time className="text-xs text-mute">
            {new Date(message.timestamp).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit"
            })}
          </time>
        </div>
        <p className="text-sm leading-7 text-text">{message.text}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {(analysis?.claims?.length ? analysis.claims : [{ type: "error", summary: analysis?.summary }]).map(
            (claim, index) => (
              <AnnotationBadge
                key={claim.id ?? `${message.id}-${index}`}
                claim={claim}
                active={active}
                onClick={onOpen}
                onHoverChange={onHoverChange}
              />
            )
          )}
        </div>
      </div>
      {tooltipVisible ? <TooltipCard analysis={analysis} /> : null}
    </article>
  );
}
