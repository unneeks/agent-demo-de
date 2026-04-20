import path from "path";
import type { CodefreshPipeline, MigrationPlan, WorkflowJobPlan } from "../types";
import { mapStep, type MappingAccumulator } from "./mapper";

export function createMigrationPlan(pipeline: CodefreshPipeline): MigrationPlan {
  const job: WorkflowJobPlan = {
    id: "migrate",
    name: "Migrated Codefresh pipeline",
    runsOn: "ubuntu-latest",
    steps: [],
    mappings: []
  };

  const accumulator: MappingAccumulator = {
    job,
    warnings: [],
    requiredSecrets: new Set<string>(),
    confidenceValues: []
  };

  const hasCloneStep = pipeline.steps.some(step => isCloneType(step.type));
  if (!hasCloneStep) {
    job.steps.push({
      name: "Checkout",
      uses: "actions/checkout@v4"
    });
  }

  for (const step of pipeline.steps) {
    mapStep(step, accumulator);
  }

  const confidence = accumulator.confidenceValues.length === 0
    ? 0
    : round(accumulator.confidenceValues.reduce((sum, value) => sum + value, 0) / accumulator.confidenceValues.length);

  return {
    pipeline,
    targetWorkflowPath: path.join(".github", "workflows", `${pipeline.name}.yml`),
    jobs: [job],
    warnings: unique(accumulator.warnings),
    requiredSecrets: [...accumulator.requiredSecrets].sort(),
    confidence
  };
}

function isCloneType(type: string): boolean {
  const normalized = type.toLowerCase();
  return normalized === "git-clone" || normalized === "git_clone" || normalized === "clone";
}

function round(value: number): number {
  return Math.round(value * 100) / 100;
}

function unique(values: string[]): string[] {
  return [...new Set(values)];
}
