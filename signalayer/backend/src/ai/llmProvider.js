export async function maybeCallLlm({ stage, payload }) {
  const endpoint = process.env.SIGNALLAYER_LLM_ENDPOINT;
  const apiKey = process.env.SIGNALLAYER_LLM_API_KEY;

  if (!endpoint || !apiKey) {
    return null;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 4000);

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${apiKey}`
      },
      body: JSON.stringify({ stage, payload }),
      signal: controller.signal
    });

    if (!response.ok) {
      return null;
    }

    return await response.json();
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}
