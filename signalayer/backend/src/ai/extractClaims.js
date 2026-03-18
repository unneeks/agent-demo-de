import { splitIntoCandidateClaims } from "../../../shared/localAnalysis.js";

export function extractClaims(message) {
  return splitIntoCandidateClaims(message)
    .filter((candidate) => candidate.split(/\s+/).length >= 5)
    .map((text, index) => ({
      id: `claim-${index + 1}`,
      text
    }));
}
