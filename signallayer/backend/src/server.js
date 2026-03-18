import http from "node:http";
import { AnalysisCache } from "./cache.js";
import { analyzeMessage, fastClassifyMessage } from "./reasoner.js";
import {
  createAnalyzeRequest,
  createEmptyAnalysis,
  normalizeAnalyzeResponse,
  validateAnalyzeRequest
} from "../../shared/contracts.js";
import { hashMessage } from "../../shared/utils.js";

const cache = new AnalysisCache();

function jsonResponse(res, statusCode, payload) {
  res.writeHead(statusCode, {
    "content-type": "application/json",
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-allow-headers": "content-type"
  });
  res.end(JSON.stringify(payload));
}

async function readJson(req) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(chunk);
  }

  const raw = Buffer.concat(chunks).toString("utf8");
  return raw ? JSON.parse(raw) : {};
}

export async function handleAnalyzeRequest(rawPayload) {
  const payload = createAnalyzeRequest(rawPayload);
  payload.messageHash = payload.messageHash || hashMessage(payload.message);

  const validation = validateAnalyzeRequest(payload);
  if (!validation.valid) {
    return {
      statusCode: 400,
      body: {
        status: "error",
        errors: validation.errors
      }
    };
  }

  const cached = cache.get(payload.messageHash);
  if (cached) {
    return {
      statusCode: 200,
      body: normalizeAnalyzeResponse({
        ...cached,
        meta: {
          ...cached.meta,
          cache: "hit"
        }
      })
    };
  }

  const analysis = await analyzeMessage(payload);
  const result =
    analysis.status === "error"
      ? analysis
      : {
          ...analysis,
          fastPass: analysis.fastPass || fastClassifyMessage(payload.message)
        };

  cache.set(payload.messageHash, result);
  return {
    statusCode: 200,
    body: result
  };
}

export function createServer() {
  return http.createServer(async (req, res) => {
    if (req.method === "OPTIONS") {
      jsonResponse(res, 204, {});
      return;
    }

    if (req.method === "GET" && req.url === "/health") {
      jsonResponse(res, 200, {
        status: "ok",
        service: "signallayer-backend"
      });
      return;
    }

    if (req.method === "POST" && req.url === "/analyze") {
      try {
        const result = await handleAnalyzeRequest(await readJson(req));
        jsonResponse(res, result.statusCode, result.body);
        return;
      } catch (error) {
        jsonResponse(
          res,
          500,
          createEmptyAnalysis({
            status: "error",
            latencyMs: 0,
            cache: "miss",
            reasoningMode: "heuristic"
          })
        );
      }

      return;
    }

    jsonResponse(res, 404, {
      status: "error",
      error: "not_found"
    });
  });
}

export function startServer(port = 8787) {
  const server = createServer();
  server.listen(port);
  return server;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const port = Number(process.env.PORT || 8787);
  const server = startServer(port);
  console.log(`SignalLayer backend listening on http://localhost:${port}`);

  process.on("SIGINT", () => {
    server.close(() => process.exit(0));
  });
}
