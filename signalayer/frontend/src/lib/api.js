import { hashMessage } from "../../../shared/hash.js";

const clientCache = new Map();
const API_BASE_URL = import.meta.env.VITE_SIGNALLAYER_API_URL ?? "http://localhost:8787";

export async function analyzeMessage(message, context) {
  const cacheKey = hashMessage(message.text);

  if (clientCache.has(cacheKey)) {
    const cached = clientCache.get(cacheKey);
    return {
      ...cached,
      meta: {
        ...cached.meta,
        cacheHit: true
      }
    };
  }

  const response = await fetch(`${API_BASE_URL}/analyze`, {
    method: "POST",
    headers: {
      "content-type": "application/json"
    },
    body: JSON.stringify({
      message: message.text,
      context,
      conversationId: "conv-signalayer-demo",
      messageId: message.id
    })
  });

  if (!response.ok) {
    throw new Error(`Analysis request failed with status ${response.status}`);
  }

  const payload = await response.json();
  clientCache.set(cacheKey, payload);
  return payload;
}

export function resetClientCache() {
  clientCache.clear();
}
