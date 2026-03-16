const ALLOWED_TEXTUAL_DEPENDENCE = new Set(["low", "medium", "high"]);
const ALLOWED_RELATION = new Set(["outside", "core", "hybrid", "reform"]);
const ALLOWED_CONFIDENCE = new Set(["low", "medium", "high"]);

export function validateTradition(tradition) {
  const errors = [];

  if (!tradition.id) errors.push("id is required");
  if (!tradition.name) errors.push("name is required");
  if (typeof tradition.originTime !== "number") {
    errors.push("originTime must be a number");
  }
  if (
    tradition.declineTime !== null &&
    tradition.declineTime !== undefined &&
    typeof tradition.declineTime !== "number"
  ) {
    errors.push("declineTime must be a number or null");
  }
  if (!Array.isArray(tradition.regions) || tradition.regions.length === 0) {
    errors.push("regions must be a non-empty array");
  }
  if (!ALLOWED_TEXTUAL_DEPENDENCE.has(tradition.textualDependence)) {
    errors.push("textualDependence must be low, medium, or high");
  }
  if (!ALLOWED_RELATION.has(tradition.vedicRelation)) {
    errors.push("vedicRelation must be outside, core, hybrid, or reform");
  }
  if (!ALLOWED_CONFIDENCE.has(tradition.confidence)) {
    errors.push("confidence must be low, medium, or high");
  }

  const strength = tradition.institutionalStrength ?? {};
  if (!strength.start || !strength.end) {
    errors.push("institutionalStrength.start and .end are required");
  }
  if (
    typeof tradition.declineTime === "number" &&
    typeof tradition.originTime === "number" &&
    tradition.declineTime < tradition.originTime
  ) {
    errors.push("declineTime must be greater than or equal to originTime");
  }

  return errors;
}

export function summarizeTradition(tradition) {
  const endLabel =
    tradition.declineTime === null || tradition.declineTime === undefined
      ? "present"
      : tradition.declineTime;

  return `${tradition.name} (${tradition.originTime} to ${endLabel})`;
}
