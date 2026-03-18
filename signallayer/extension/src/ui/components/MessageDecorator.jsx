import React from "react";
import { AnnotationBadge } from "./AnnotationBadge.jsx";

export function MessageDecorator({ analysis, onHover, onLeave, onOpen }) {
  const tone =
    analysis?.status === "error"
      ? "error"
      : analysis?.status === "ok"
        ? analysis.fastPass?.badges?.includes("prediction")
          ? "prediction"
          : "claim"
        : analysis?.status === "no_claims"
          ? "neutral"
          : "reasoning";

  const label =
    analysis?.status === "ok"
      ? "Claim analysis available"
      : analysis?.status === "error"
        ? "Analysis unavailable"
        : analysis?.status === "no_claims"
          ? "No strong claims"
          : "Analysis in progress";

  return <AnnotationBadge tone={tone} label={label} onHover={onHover} onLeave={onLeave} onClick={onOpen} />;
}
