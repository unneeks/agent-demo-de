import express from "express";
import cors from "cors";
import { handleAnalyzePayload } from "./analyzeService.js";

export function createServer() {
  const app = express();
  app.use(cors());
  app.use(express.json());

  app.get("/health", (_request, response) => {
    response.json({ ok: true });
  });

  app.post("/analyze", async (request, response) => {
    const result = await handleAnalyzePayload(request.body);
    response.status(result.status).json(result.payload);
  });

  return app;
}

const isDirectRun =
  process.argv[1] && import.meta.url === new URL(process.argv[1], "file:").href;

if (isDirectRun) {
  const port = Number(process.env.PORT || 8787);
  createServer().listen(port, () => {
    console.log(`SignalLayer backend listening on http://localhost:${port}`);
  });
}
