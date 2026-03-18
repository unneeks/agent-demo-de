export const CLAIM_TYPES = ["factual", "opinion", "prediction"];
export const CLAIM_STATUS = ["supported", "contested", "uncertain", "no-evidence"];
export const ANALYSIS_STATUS = ["idle", "loading", "ready", "error"];

export function isChatMessage(value) {
  return Boolean(
    value &&
      typeof value.id === "string" &&
      typeof value.author === "string" &&
      typeof value.text === "string" &&
      typeof value.timestamp === "string"
  );
}

export function validateAnalyzeRequest(payload) {
  const errors = [];

  if (!payload || typeof payload !== "object") {
    return ["Payload must be a JSON object."];
  }

  if (typeof payload.message !== "string" || payload.message.trim().length === 0) {
    errors.push("`message` must be a non-empty string.");
  }

  if (!Array.isArray(payload.context) || payload.context.some((item) => !isChatMessage(item))) {
    errors.push("`context` must be an array of ChatMessage objects.");
  }

  if (typeof payload.conversationId !== "string" || payload.conversationId.trim().length === 0) {
    errors.push("`conversationId` must be a non-empty string.");
  }

  if (typeof payload.messageId !== "string" || payload.messageId.trim().length === 0) {
    errors.push("`messageId` must be a non-empty string.");
  }

  return errors;
}

export function clampConfidence(value) {
  return Math.max(0, Math.min(1, Number(value) || 0));
}
