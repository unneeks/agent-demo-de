import { hashMessage } from "./hash.js";
import { quickAnalyzeMessage } from "./localAnalysis.js";

export function createInitialAnalysisState(messages) {
  return messages.reduce((state, message) => {
    const local = quickAnalyzeMessage(message.text);
    state[message.id] = {
      messageId: message.id,
      hash: hashMessage(message.text),
      status: local.claims.length > 0 ? "loading" : "idle",
      summary: local.summary,
      claims: local.claims,
      latencyMs: 0,
      source: "local"
    };
    return state;
  }, {});
}
