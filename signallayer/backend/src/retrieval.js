import { knowledgeCorpus } from "../../shared/corpus.js";
import { scoreOverlap, truncate } from "../../shared/utils.js";

export function retrieveEvidence(message, context = [], limit = 3) {
  const contextualText = [
    message,
    ...context.map((item) => item.text ?? "")
  ].join(" ");

  const hits = knowledgeCorpus
    .map((doc) => ({
      id: doc.id,
      title: doc.title,
      score: scoreOverlap(contextualText, `${doc.title} ${doc.content}`),
      snippet: truncate(doc.content, 160),
      stance: inferStance(message, doc),
      sourceType: "corpus"
    }))
    .filter((hit) => hit.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);

  if (!hits.length && context.length) {
    return context.slice(-2).map((item, index) => ({
      id: `context-${index + 1}`,
      title: "Conversation context",
      score: 0.2,
      snippet: truncate(item.text ?? "", 160),
      stance: "context",
      sourceType: "context"
    }));
  }

  return hits;
}

function inferStance(message, doc) {
  const text = `${message} ${doc.content}`.toLowerCase();

  if (/\b(fake|hoax|misleading|uncertain|no evidence)\b/.test(text)) {
    return "conflicting";
  }

  if (/\bsource|evidence|official|study|data\b/.test(text)) {
    return "supporting";
  }

  return "context";
}
