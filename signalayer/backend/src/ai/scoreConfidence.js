import { clampConfidence } from "../../../shared/contracts.js";

export function scoreConfidence(claim, evidence) {
  const typeBase =
    claim.type === "factual" ? 0.62 : claim.type === "prediction" ? 0.5 : 0.46;
  const evidenceBoost = Math.min(0.24, evidence.length * 0.08);
  const retrievalBoost = evidence.reduce((total, item) => total + item.score, 0) * 0.15;
  return clampConfidence(typeBase + evidenceBoost + retrievalBoost);
}
