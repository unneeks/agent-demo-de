export function summarizeClaims(claims) {
  if (claims.length === 0) {
    return "No clear factual, opinion, or prediction claims were detected in this message.";
  }

  const factual = claims.filter((claim) => claim.type === "factual").length;
  const predictions = claims.filter((claim) => claim.type === "prediction").length;
  const opinions = claims.filter((claim) => claim.type === "opinion").length;

  return `Detected ${claims.length} claim${claims.length > 1 ? "s" : ""}: ${factual} factual, ${opinions} opinion, ${predictions} prediction.`;
}
