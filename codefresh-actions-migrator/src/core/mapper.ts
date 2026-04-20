import { stringify } from "yaml";
import type { CodefreshStep, GitHubActionStep, StepMapping, WorkflowJobPlan } from "../types";

export interface MappingAccumulator {
  job: WorkflowJobPlan;
  warnings: string[];
  requiredSecrets: Set<string>;
  confidenceValues: number[];
}

export function mapStep(step: CodefreshStep, accumulator: MappingAccumulator): void {
  const normalizedType = step.type.toLowerCase();

  if (normalizedType === "git-clone" || normalizedType === "git_clone" || normalizedType === "clone") {
    addMappedStep(step, accumulator, "checkout", 0.98, { name: titleFor(step), uses: "actions/checkout@v4" });
    return;
  }

  if (normalizedType === "freestyle") {
    mapFreestyle(step, accumulator);
    return;
  }

  if (normalizedType === "build") {
    mapBuild(step, accumulator);
    return;
  }

  if (normalizedType === "push") {
    mapPush(step, accumulator);
    return;
  }

  if (normalizedType === "composition") {
    mapComposition(step, accumulator);
    return;
  }

  if (normalizedType === "pending-approval" || normalizedType === "approval") {
    mapApproval(step, accumulator);
    return;
  }

  if (normalizedType === "deploy") {
    mapDeploy(step, accumulator);
    return;
  }

  mapUnknown(step, accumulator);
}

function mapFreestyle(step: CodefreshStep, accumulator: MappingAccumulator): void {
  const commands = step.commands ?? [];
  const warnings: string[] = [];

  if (step.image) {
    if (!accumulator.job.container && !step.image.includes("${{")) {
      accumulator.job.container = step.image;
      warnings.push(`Mapped Codefresh image "${step.image}" to the GitHub Actions job container.`);
    } else {
      warnings.push(`Step "${step.id}" uses image "${step.image}" but the job already has a container or references a dynamic image.`);
    }
  }

  if (commands.length === 0) {
    warnings.push(`Freestyle step "${step.id}" has no commands; generated a placeholder.`);
  }

  const ghStep: GitHubActionStep = {
    name: titleFor(step),
    run: commands.length > 0 ? commands.join("\n") : `echo "TODO: migrate freestyle step ${step.id}"`,
    env: step.environment
  };

  addMappedStep(step, accumulator, "run", warnings.length > 0 ? 0.78 : 0.9, ghStep, warnings);
}

function mapBuild(step: CodefreshStep, accumulator: MappingAccumulator): void {
  const imageName = stringField(step.raw, "image_name") ?? "${{ github.repository }}";
  const dockerfile = stringField(step.raw, "dockerfile") ?? "Dockerfile";
  const context = stringField(step.raw, "working_directory") ?? ".";
  const tag = stringField(step.raw, "tag") ?? "latest";
  const disablePush = Boolean(step.raw.disable_push);

  addMappedStep(step, accumulator, "docker-buildx", 0.9, {
    name: `Set up Buildx for ${step.id}`,
    uses: "docker/setup-buildx-action@v3"
  });

  addMappedStep(step, accumulator, "docker-build", disablePush ? 0.86 : 0.82, {
    name: titleFor(step),
    uses: "docker/build-push-action@v6",
    with: {
      context,
      file: dockerfile,
      push: !disablePush,
      tags: `${imageName}:${tag}`
    }
  }, disablePush ? [] : [`Codefresh build steps push automatically unless disable_push is true; verify registry authentication for "${step.id}".`]);
}

function mapPush(step: CodefreshStep, accumulator: MappingAccumulator): void {
  const registry = stringField(step.raw, "registry") ?? stringField(step.raw, "candidate") ?? "registry.example.com";
  const imageName = stringField(step.raw, "image_name") ?? stringField(step.raw, "candidate") ?? "${{ github.repository }}";
  const tag = stringField(step.raw, "tag") ?? "latest";

  accumulator.requiredSecrets.add("REGISTRY_USERNAME");
  accumulator.requiredSecrets.add("REGISTRY_PASSWORD");

  addMappedStep(step, accumulator, "docker-login", 0.82, {
    name: `Log in for ${step.id}`,
    uses: "docker/login-action@v3",
    with: {
      registry,
      username: "${{ secrets.REGISTRY_USERNAME }}",
      password: "${{ secrets.REGISTRY_PASSWORD }}"
    }
  }, [`Verify the registry host and secret names for push step "${step.id}".`]);

  addMappedStep(step, accumulator, "docker-push", 0.8, {
    name: titleFor(step),
    run: [
      `docker tag ${imageName}:${tag} ${registry}/${imageName}:${tag}`,
      `docker push ${registry}/${imageName}:${tag}`
    ].join("\n")
  });
}

function mapComposition(step: CodefreshStep, accumulator: MappingAccumulator): void {
  const composition = step.raw.composition;
  const warnings: string[] = [];

  if (isRecord(composition)) {
    const services = isRecord(composition.services) ? composition.services : composition;
    accumulator.job.services = {
      ...(accumulator.job.services ?? {}),
      ...services
    };
    warnings.push(`Mapped composition "${step.id}" to job services; verify service health checks and ports.`);
    addMappingOnly(step, accumulator, "services", 0.72, warnings);
    return;
  }

  const composeFile = typeof composition === "string" ? composition : "docker-compose.yml";
  warnings.push(`Composition "${step.id}" needs manual verification because not all Docker Compose fields map to GitHub services.`);
  addMappedStep(step, accumulator, "docker-compose", 0.62, {
    name: titleFor(step),
    run: `docker compose -f ${composeFile} up --abort-on-container-exit --exit-code-from ${firstCandidate(step) ?? "tests"}`
  }, warnings);
}

function mapApproval(step: CodefreshStep, accumulator: MappingAccumulator): void {
  accumulator.job.environment = sanitizeEnvironmentName(step.title ?? step.id);
  addMappingOnly(step, accumulator, "environment-approval", 0.75, [
    `Approval step "${step.id}" maps to a GitHub environment; configure required reviewers in repository settings.`
  ]);
}

function mapDeploy(step: CodefreshStep, accumulator: MappingAccumulator): void {
  const commands = step.commands ?? normalizeDeployCommands(step);
  if (commands.length > 0) {
    addMappedStep(step, accumulator, "deploy-run", 0.7, {
      name: titleFor(step),
      run: commands.join("\n"),
      env: step.environment
    }, [`Deploy step "${step.id}" was preserved as commands; verify credentials, cluster context, and environment protection.`]);
    return;
  }

  addMappedStep(step, accumulator, "deploy-placeholder", 0.35, {
    name: titleFor(step),
    run: `echo "TODO: migrate deploy step ${step.id}"`
  }, [`Deploy step "${step.id}" has no clear command mapping and needs manual migration.`]);
}

function mapUnknown(step: CodefreshStep, accumulator: MappingAccumulator): void {
  addMappedStep(step, accumulator, "manual-review", 0.25, {
    name: `TODO migrate ${step.id}`,
    run: [
      `echo "Unsupported Codefresh step type: ${step.type}"`,
      `echo "Review original step ${step.id} before enabling this workflow."`
    ].join("\n")
  }, [`Unsupported Codefresh step "${step.id}" of type "${step.type}" requires manual review or Copilot suggestion.`]);
}

function addMappedStep(
  step: CodefreshStep,
  accumulator: MappingAccumulator,
  targetKind: string,
  confidence: number,
  ghStep: GitHubActionStep,
  warnings: string[] = []
): void {
  const normalizedStep = removeUndefined(ghStep);
  accumulator.job.steps.push(normalizedStep);
  addMapping(step, accumulator, targetKind, confidence, stringify(normalizedStep).trim(), warnings);
}

function addMappingOnly(
  step: CodefreshStep,
  accumulator: MappingAccumulator,
  targetKind: string,
  confidence: number,
  warnings: string[] = []
): void {
  addMapping(step, accumulator, targetKind, confidence, "", warnings);
}

function addMapping(
  step: CodefreshStep,
  accumulator: MappingAccumulator,
  targetKind: string,
  confidence: number,
  yamlFragment: string,
  warnings: string[]
): void {
  const mapping: StepMapping = {
    sourceStepId: step.id,
    sourceType: step.type,
    targetKind,
    confidence,
    yamlFragment,
    warnings
  };

  accumulator.job.mappings.push(mapping);
  accumulator.warnings.push(...warnings);
  accumulator.confidenceValues.push(confidence);
}

function titleFor(step: CodefreshStep): string {
  return step.title ?? step.id;
}

function stringField(record: Record<string, unknown>, key: string): string | undefined {
  const value = record[key];
  return typeof value === "string" ? value : undefined;
}

function firstCandidate(step: CodefreshStep): string | undefined {
  const candidates = step.raw.composition_candidates;
  if (isRecord(candidates)) {
    return Object.keys(candidates)[0];
  }
  return undefined;
}

function normalizeDeployCommands(step: CodefreshStep): string[] {
  const commands = step.raw.commands ?? step.raw.command;
  if (Array.isArray(commands)) {
    return commands.map(command => String(command));
  }
  if (typeof commands === "string") {
    return [commands];
  }
  return [];
}

function sanitizeEnvironmentName(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "production";
}

function removeUndefined<T extends object>(value: T): T {
  for (const key of Object.keys(value)) {
    const record = value as Record<string, unknown>;
    if (record[key] === undefined) {
      delete record[key];
    }
  }
  return value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
