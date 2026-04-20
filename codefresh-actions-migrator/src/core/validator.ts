import { parseDocument } from "yaml";
import type { ValidationResult } from "../types";

export function validateGitHubWorkflow(source: string): ValidationResult {
  const errors: string[] = [];
  const doc = parseDocument(source, { prettyErrors: true });

  if (doc.errors.length > 0) {
    errors.push(...doc.errors.map(error => error.message));
    return { valid: false, errors };
  }

  const workflow = doc.toJSON();
  if (!isRecord(workflow)) {
    return { valid: false, errors: ["Workflow YAML must be an object."] };
  }

  if (!("name" in workflow)) {
    errors.push("Workflow must include a top-level name.");
  }
  if (!("on" in workflow)) {
    errors.push("Workflow must include a top-level on trigger.");
  }
  if (!isRecord(workflow.jobs)) {
    errors.push("Workflow must include top-level jobs.");
  } else if (Object.keys(workflow.jobs).length === 0) {
    errors.push("Workflow must include at least one job.");
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
