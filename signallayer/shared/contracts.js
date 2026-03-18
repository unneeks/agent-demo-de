export const CLAIM_TYPES = ["factual", "opinion", "prediction"];

export function createAnalyzeRequest(payload = {}) {
  return {
    message: String(payload.message ?? ""),
    context: Array.isArray(payload.context) ? payload.context : [],
    messageId: String(payload.messageId ?? ""),
    conversationId: String(payload.conversationId ?? ""),
    messageHash: String(payload.messageHash ?? "")
  };
}

export function createEmptyAnalysis({
  messageId = "",
  messageHash = "",
  status = "no_claims",
  latencyMs = 0,
  cache = "miss",
  reasoningMode = "heuristic"
} = {}) {
  return {
    messageId,
    messageHash,
    status,
    fastPass: {
      hasClaims: false,
      signal: "neutral",
      badges: ["neutral"]
    },
    claims: [],
    meta: {
      latencyMs,
      cache,
      reasoningMode
    }
  };
}

export function normalizeClaim(claim, index = 0) {
  const confidence = Number.isFinite(claim.confidence)
    ? Math.max(0, Math.min(1, claim.confidence))
    : 0;

  return {
    id: claim.id ?? `claim-${index + 1}`,
    text: String(claim.text ?? ""),
    type: CLAIM_TYPES.includes(claim.type) ? claim.type : "factual",
    confidence,
    summary: String(claim.summary ?? ""),
    counter: String(claim.counter ?? ""),
    evidence: Array.isArray(claim.evidence)
      ? claim.evidence.map((item) => ({
          title: String(item.title ?? "Context"),
          snippet: String(item.snippet ?? ""),
          stance: ["supporting", "conflicting", "context"].includes(item.stance)
            ? item.stance
            : "context",
          sourceType: ["corpus", "context", "heuristic"].includes(item.sourceType)
            ? item.sourceType
            : "heuristic"
        }))
      : []
  };
}

export function normalizeAnalyzeResponse(response = {}) {
  return {
    messageId: String(response.messageId ?? ""),
    messageHash: String(response.messageHash ?? ""),
    status: ["ok", "no_claims", "error"].includes(response.status)
      ? response.status
      : "error",
    fastPass: {
      hasClaims: Boolean(response.fastPass?.hasClaims),
      signal: ["neutral", "claim", "mixed"].includes(response.fastPass?.signal)
        ? response.fastPass.signal
        : "neutral",
      badges: Array.isArray(response.fastPass?.badges)
        ? response.fastPass.badges.map(String)
        : []
    },
    claims: Array.isArray(response.claims)
      ? response.claims.map(normalizeClaim)
      : [],
    meta: {
      latencyMs: Number(response.meta?.latencyMs ?? 0),
      cache: ["hit", "miss"].includes(response.meta?.cache)
        ? response.meta.cache
        : "miss",
      reasoningMode: ["heuristic", "hybrid"].includes(response.meta?.reasoningMode)
        ? response.meta.reasoningMode
        : "heuristic"
    }
  };
}

export function validateAnalyzeRequest(request = {}) {
  const errors = [];

  if (!request.message || !String(request.message).trim()) {
    errors.push("message is required");
  }

  if (!Array.isArray(request.context)) {
    errors.push("context must be an array");
  }

  return {
    valid: errors.length === 0,
    errors
  };
}
