import {
  createEmptyAnalysis,
  normalizeAnalyzeResponse,
  normalizeClaim
} from "../../shared/contracts.js";
import { hashMessage, nowMs, truncate } from "../../shared/utils.js";
import { retrieveEvidence } from "./retrieval.js";
import { runOptionalLlmStep } from "./llm.js";

const FACTUAL_PATTERNS = [
  /\b(is|are|was|were|has|have)\b/i,
  /\b\d+(\.\d+)?%?\b/,
  /\baccording to\b/i
];

const PREDICTION_PATTERNS = [/\bwill\b/i, /\bgoing to\b/i, /\bsoon\b/i, /\bdefinitely\b/i];
const OPINION_PATTERNS = [/\bi think\b/i, /\bi feel\b/i, /\bin my opinion\b/i, /\bprobably\b/i];

export function fastClassifyMessage(message) {
  const text = String(message ?? "").trim();
  if (!text) {
    return {
      hasClaims: false,
      signal: "neutral",
      badges: ["neutral"]
    };
  }

  const looksPredictive = PREDICTION_PATTERNS.some((pattern) => pattern.test(text));
  const looksFactual = FACTUAL_PATTERNS.some((pattern) => pattern.test(text));

  if (looksPredictive && looksFactual) {
    return {
      hasClaims: true,
      signal: "mixed",
      badges: ["prediction", "claim"]
    };
  }

  if (looksPredictive || looksFactual) {
    return {
      hasClaims: true,
      signal: "claim",
      badges: [looksPredictive ? "prediction" : "claim"]
    };
  }

  return {
    hasClaims: false,
    signal: "neutral",
    badges: ["neutral"]
  };
}

export function extractClaims(message) {
  const sentences = String(message ?? "")
    .split(/(?<=[.!?])\s+/)
    .map((part) => part.trim())
    .filter(Boolean);

  return sentences.filter((sentence) => {
    const hasVerb = FACTUAL_PATTERNS.some((pattern) => pattern.test(sentence));
    const hasLength = sentence.length > 20;
    return hasVerb && hasLength;
  });
}

export function classifyClaim(claimText) {
  if (PREDICTION_PATTERNS.some((pattern) => pattern.test(claimText))) {
    return "prediction";
  }

  if (OPINION_PATTERNS.some((pattern) => pattern.test(claimText))) {
    return "opinion";
  }

  return "factual";
}

export function buildCounterArgument(type, evidence = []) {
  const conflicting = evidence.find((item) => item.stance === "conflicting");
  if (conflicting) {
    return `Conflicting context suggests caution: ${truncate(conflicting.snippet, 110)}`;
  }

  if (type === "prediction") {
    return "Treat this as a forecast rather than a verified outcome unless it includes a source and timeframe.";
  }

  if (type === "opinion") {
    return "This may reflect a viewpoint rather than a verifiable fact, so supporting evidence matters more than tone.";
  }

  return "This statement would be stronger with a named source, date, or supporting data.";
}

export function scoreConfidence(type, claimText, evidence) {
  let score = 0.45;
  if (type === "factual") {
    score += 0.15;
  }
  if (type === "prediction") {
    score -= 0.08;
  }
  if (/\b\d+(\.\d+)?%?\b/.test(claimText)) {
    score += 0.05;
  }

  const supportCount = evidence.filter((item) => item.stance === "supporting").length;
  const conflictCount = evidence.filter((item) => item.stance === "conflicting").length;
  score += supportCount * 0.1;
  score -= conflictCount * 0.12;

  if (!evidence.length) {
    score -= 0.1;
  }

  return Math.max(0.05, Math.min(0.95, score));
}

export async function analyzeMessage(request) {
  const startedAt = nowMs();
  const messageHash = request.messageHash || hashMessage(request.message);
  const fastPass = fastClassifyMessage(request.message);

  if (!fastPass.hasClaims) {
    return createEmptyAnalysis({
      messageId: request.messageId,
      messageHash,
      status: "no_claims",
      latencyMs: nowMs() - startedAt
    });
  }

  const extractedClaims = extractClaims(request.message);
  if (!extractedClaims.length) {
    return {
      ...createEmptyAnalysis({
        messageId: request.messageId,
        messageHash,
        status: "no_claims",
        latencyMs: nowMs() - startedAt
      }),
      fastPass
    };
  }

  const llmRefinement = await runOptionalLlmStep({
    task: "Refine claims for analysis. Return JSON { claims: [{ text, type, summary }] }.",
    payload: {
      message: request.message,
      context: request.context,
      extractedClaims
    }
  }).catch(() => null);

  const claims = extractedClaims.map((claimText, index) => {
    const candidate = llmRefinement?.claims?.[index] ?? {};
    const type = candidate.type || classifyClaim(claimText);
    const evidence = retrieveEvidence(claimText, request.context);
    return normalizeClaim(
      {
        id: `claim-${index + 1}`,
        text: candidate.text || claimText,
        type,
        confidence: scoreConfidence(type, claimText, evidence),
        summary:
          candidate.summary ||
          `Possible ${type} claim detected. Review the available evidence and counterpoint before trusting it.`,
        counter: buildCounterArgument(type, evidence),
        evidence
      },
      index
    );
  });

  const response = normalizeAnalyzeResponse({
    messageId: request.messageId,
    messageHash,
    status: claims.length ? "ok" : "no_claims",
    fastPass,
    claims,
    meta: {
      latencyMs: nowMs() - startedAt,
      cache: "miss",
      reasoningMode: llmRefinement ? "hybrid" : "heuristic"
    }
  });

  return response;
}
