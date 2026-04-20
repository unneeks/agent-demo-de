import { promises as fs } from "fs";
import path from "path";
import { parseDocument } from "yaml";
import { z } from "zod";
import { analyzePipeline } from "./analyzer";
import type { CodefreshPipeline } from "../types";

const rawPipelineSchema = z.object({
  version: z.union([z.string(), z.number()]).optional(),
  steps: z.record(z.unknown()).optional(),
  variables: z.record(z.unknown()).optional()
});

export async function parseCodefreshFile(filePath: string): Promise<CodefreshPipeline> {
  const source = await fs.readFile(filePath, "utf8");
  return parseCodefreshSource(source, filePath);
}

export function parseCodefreshSource(source: string, sourcePath = "codefresh.yml"): CodefreshPipeline {
  const doc = parseDocument(source, { prettyErrors: true });
  if (doc.errors.length > 0) {
    throw new Error(doc.errors.map(error => error.message).join("\n"));
  }

  const data = doc.toJSON();
  const parsed = rawPipelineSchema.parse(data ?? {});
  const rawSteps = parsed.steps ?? {};
  const name = derivePipelineName(sourcePath);

  return analyzePipeline({
    sourcePath,
    name,
    version: String(parsed.version ?? "1.0"),
    variables: parsed.variables ?? {},
    rawSteps
  });
}

function derivePipelineName(sourcePath: string): string {
  const parent = path.basename(path.dirname(sourcePath));
  if (parent && parent !== "." && parent !== ".codefresh") {
    return sanitizeName(parent);
  }

  const base = path.basename(sourcePath, path.extname(sourcePath));
  return sanitizeName(base || "codefresh-pipeline");
}

function sanitizeName(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "codefresh-pipeline";
}
