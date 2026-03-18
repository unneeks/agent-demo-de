function tokenize(text) {
  return Array.from(
    new Set(
      text
        .toLowerCase()
        .replace(/[^a-z0-9\s]/g, " ")
        .split(/\s+/)
        .filter((token) => token.length > 2)
    )
  );
}

export function retrieveEvidence(claimText, knowledgeBase, context = []) {
  const claimTerms = tokenize(claimText);
  const documents = [
    ...knowledgeBase.map((doc) => ({ ...doc, sourceType: "kb" })),
    ...context.map((message) => ({
      id: `ctx-${message.id}`,
      title: `Conversation: ${message.author}`,
      tags: ["conversation"],
      content: message.text,
      sourceType: "conversation"
    }))
  ];

  return documents
    .map((doc) => {
      const haystack = `${doc.title} ${doc.content} ${doc.tags.join(" ")}`.toLowerCase();
      const matchedTerms = claimTerms.filter((term) => haystack.includes(term));
      const score = matchedTerms.length / Math.max(1, claimTerms.length);
      return { doc, score, matchedTerms };
    })
    .filter((item) => item.score > 0)
    .sort((left, right) => right.score - left.score)
    .slice(0, 3)
    .map(({ doc, score, matchedTerms }) => ({
      title: doc.title,
      snippet: doc.content,
      sourceType: doc.sourceType,
      score,
      matchedTerms
    }));
}
