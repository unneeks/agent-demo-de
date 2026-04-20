import type { CodefreshPipeline, CodefreshStep } from "../types";

interface AnalyzeInput {
  sourcePath: string;
  name: string;
  version: string;
  variables: Record<string, unknown>;
  rawSteps: Record<string, unknown>;
}

export function analyzePipeline(input: AnalyzeInput): CodefreshPipeline {
  const steps = Object.entries(input.rawSteps).map(([id, raw]) => normalizeStep(id, raw));

  return {
    sourcePath: input.sourcePath,
    name: input.name,
    version: input.version,
    variables: input.variables,
    steps
  };
}

function normalizeStep(id: string, raw: unknown): CodefreshStep {
  const record = isRecord(raw) ? raw : {};
  const type = String(record.type ?? inferStepType(record));

  return {
    id,
    type,
    title: asOptionalString(record.title),
    image: asOptionalString(record.image),
    commands: normalizeCommands(record.commands ?? record.command),
    environment: normalizeEnvironment(record.environment),
    when: record.when,
    raw: record
  };
}

function inferStepType(record: Record<string, unknown>): string {
  if (record.image || record.commands || record.command) {
    return "freestyle";
  }
  return "unknown";
}

function normalizeCommands(value: unknown): string[] | undefined {
  if (Array.isArray(value)) {
    return value.map(item => String(item));
  }
  if (typeof value === "string") {
    return [value];
  }
  return undefined;
}

function normalizeEnvironment(value: unknown): Record<string, string> | undefined {
  if (Array.isArray(value)) {
    const env: Record<string, string> = {};
    for (const item of value) {
      const [key, ...rest] = String(item).split("=");
      if (key && rest.length > 0) {
        env[key] = rest.join("=");
      }
    }
    return Object.keys(env).length > 0 ? env : undefined;
  }

  if (isRecord(value)) {
    const env: Record<string, string> = {};
    for (const [key, rawValue] of Object.entries(value)) {
      env[key] = String(rawValue);
    }
    return env;
  }

  return undefined;
}

function asOptionalString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
