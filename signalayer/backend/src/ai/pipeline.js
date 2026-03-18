import { extractClaims } from "./extractClaims.js";
import { classifyClaims } from "./classifyClaims.js";
import { retrieveEvidence } from "./retrieveEvidence.js";
import { generateCounterArgument } from "./generateCounter.js";
import { scoreConfidence } from "./scoreConfidence.js";
import { summarizeClaims } from "./summarize.js";
import { knowledgeBase } from "../data/knowledgeBase.js";
import { runPromptLoop } from "./promptLoop.js";
import { maybeCallLlm } from "./llmProvider.js";

function deriveStatus(confidence, evidence) {
  if (evidence.length === 0) {
    return "no-evidence";
  }

  if (confidence >= 0.75) {
    return "supported";
  }

  return confidence >= 0.55 ? "uncertain" : "contested";
}

export async function analyzeMessage({ message, context }) {
  const extracted = extractClaims(message);
  const classified = classifyClaims(extracted);

  const providerEnhancement = await maybeCallLlm({
    stage: "claim-analysis",
    payload: { message, context, claims: classified }
  });

  const claims = classified.map((claim) => {
    const evidence = retrieveEvidence(claim.text, knowledgeBase, context);
    const confidence = scoreConfidence(claim, evidence);
    return {
      id: claim.id,
      text: claim.text,
      type: claim.type,
      confidence,
      summary:
        providerEnhancement?.summaries?.[claim.id] ??
        `${claim.type[0].toUpperCase()}${claim.type.slice(1)} claim about: ${claim.text}`,
      counter: generateCounterArgument(claim, evidence),
      evidence: evidence.map(({ title, snippet, sourceType }) => ({
        title,
        snippet,
        sourceType
      })),
      status: deriveStatus(confidence, evidence)
    };
  });

  const promptAudit = runPromptLoop("ai_agent_layer", {
    interfacesDefined: true,
    testsDefined: true,
    analyzedClaims: claims.length
  });

  return {
    summary: summarizeClaims(claims),
    claims,
    promptAudit
  };
}
