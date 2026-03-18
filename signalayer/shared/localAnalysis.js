import { clampConfidence } from "./contracts.js";

const factualMarkers = [/[\d%]/, /\baccording to\b/i, /\bdropped\b/i, /\bincreased\b/i];
const opinionMarkers = [/\bi think\b/i, /\bfeels\b/i, /\bseems\b/i, /\bbelieve\b/i];
const predictionMarkers = [/\bwill\b/i, /\bprobably\b/i, /\blikely\b/i, /\bif we\b/i];

export function splitIntoCandidateClaims(message) {
  return message
    .split(/[.!?]\s+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

export function classifyClaimText(text) {
  if (predictionMarkers.some((pattern) => pattern.test(text))) {
    return "prediction";
  }

  if (opinionMarkers.some((pattern) => pattern.test(text))) {
    return "opinion";
  }

  return factualMarkers.some((pattern) => pattern.test(text)) ? "factual" : "opinion";
}

export function scoreLocalSignal(text, type) {
  const lengthFactor = Math.min(0.18, text.length / 420);
  const base =
    type === "factual" ? 0.68 : type === "prediction" ? 0.58 : 0.49;

  return clampConfidence(base + lengthFactor);
}

export function quickAnalyzeMessage(message) {
  const candidates = splitIntoCandidateClaims(message);

  const claims = candidates
    .filter((candidate) => candidate.split(/\s+/).length >= 5)
    .map((candidate, index) => {
      const type = classifyClaimText(candidate);
      const confidence = scoreLocalSignal(candidate, type);
      return {
        id: `local-${index + 1}`,
        text: candidate,
        type,
        confidence,
        status: confidence > 0.72 ? "supported" : confidence > 0.55 ? "uncertain" : "no-evidence"
      };
    });

  const dominant = claims[0];
  const summary =
    claims.length === 0
      ? "No strong claims detected in the quick local pass."
      : `${claims.length} possible claim${claims.length > 1 ? "s" : ""} detected.`;

  return {
    claims,
    summary,
    badgeTone: dominant?.type ?? "neutral"
  };
}
