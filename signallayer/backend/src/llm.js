export async function runOptionalLlmStep({ task, payload }) {
  const apiKey = process.env.OPENAI_API_KEY;
  const baseUrl = process.env.OPENAI_BASE_URL || "https://api.openai.com/v1";
  const model = process.env.OPENAI_MODEL || "gpt-4.1-mini";

  if (!apiKey) {
    return null;
  }

  const prompt = [
    `Task: ${task}`,
    "Return strict JSON only.",
    JSON.stringify(payload, null, 2)
  ].join("\n\n");

  const response = await fetch(`${baseUrl}/responses`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${apiKey}`
    },
    body: JSON.stringify({
      model,
      input: prompt,
      text: {
        format: {
          type: "json_object"
        }
      }
    })
  });

  if (!response.ok) {
    return null;
  }

  const data = await response.json();
  const text = data.output_text;

  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}
