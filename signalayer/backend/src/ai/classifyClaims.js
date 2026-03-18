import { classifyClaimText } from "../../../shared/localAnalysis.js";

export function classifyClaims(claims) {
  return claims.map((claim) => ({
    ...claim,
    type: classifyClaimText(claim.text)
  }));
}
