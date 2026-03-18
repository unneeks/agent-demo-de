export async function analyzeMessage({ message, context, messageId, conversationId, messageHash }) {
  const response = await fetch("http://localhost:8787/analyze", {
    method: "POST",
    headers: {
      "content-type": "application/json"
    },
    body: JSON.stringify({
      message,
      context,
      messageId,
      conversationId,
      messageHash
    })
  });

  if (!response.ok) {
    throw new Error(`Analysis failed: ${response.status}`);
  }

  return response.json();
}
