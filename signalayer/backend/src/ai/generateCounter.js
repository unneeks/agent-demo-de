export function generateCounterArgument(claim, evidence) {
  if (evidence.length === 0) {
    return "No strong supporting evidence was retrieved, so this claim should be treated cautiously.";
  }

  if (claim.type === "prediction") {
    return "This prediction depends on assumptions holding steady; changes in execution or external conditions could weaken the outcome.";
  }

  if (claim.type === "opinion") {
    return "This may reflect a local perspective rather than a broadly validated pattern, so more corroboration would help.";
  }

  const hasConversationOnly = evidence.every((item) => item.sourceType === "conversation");
  return hasConversationOnly
    ? "The support currently comes from the conversation itself, which may reinforce the claim without independently verifying it."
    : "Related evidence exists, but the retrieved sources are directional rather than conclusive proof.";
}
