import { performance } from "node:perf_hooks";
import { validateAnalyzeRequest } from "../../shared/contracts.js";
import { hashMessage } from "../../shared/hash.js";
import { analysisCache } from "./lib/cache.js";
import { analyzeMessage } from "./ai/pipeline.js";

export async function handleAnalyzePayload(body) {
  const errors = validateAnalyzeRequest(body);

  if (errors.length > 0) {
    return {
      status: 400,
      payload: {
        error: "invalid_request",
        details: errors
      }
    };
  }

  const startedAt = performance.now();
  const key = `${body.conversationId}:${hashMessage(body.message)}`;
  const cached = analysisCache.get(key);

  if (cached) {
    return {
      status: 200,
      payload: {
        ...cached,
        meta: {
          ...cached.meta,
          cacheHit: true
        }
      }
    };
  }

  try {
    const result = await analyzeMessage({
      message: body.message,
      context: body.context
    });

    const payload = {
      messageId: body.messageId,
      summary: result.summary,
      claims: result.claims,
      meta: {
        cacheHit: false,
        latencyMs: Math.round(performance.now() - startedAt),
        pipeline: [
          "claim-extraction",
          "claim-classification",
          "evidence-retrieval",
          "counter-argument",
          "confidence-scoring"
        ],
        promptAudit: result.promptAudit
      }
    };

    analysisCache.set(key, payload);

    return {
      status: 200,
      payload
    };
  } catch (error) {
    return {
      status: 500,
      payload: {
        error: "analysis_failed",
        message: error instanceof Error ? error.message : "Unknown analysis error"
      }
    };
  }
}
