import { promises as fs } from "fs";
import path from "path";
import * as vscode from "vscode";
import { explainPlanWithCopilot } from "../ai/copilot";
import { generateWorkflow } from "../core/generator";
import { parseCodefreshFile } from "../core/parser";
import { createMigrationPlan } from "../core/planner";
import { scanForCodefreshPipelines } from "../core/scanner";
import { validateGitHubWorkflow } from "../core/validator";
import type { MigrationPlan } from "../types";
import { getWorkspaceRoots, workspaceRelativeOrAbsolute } from "./workspace";

export function registerCommands(context: vscode.ExtensionContext): void {
  const output = vscode.window.createOutputChannel("Codefresh Migrator");
  context.subscriptions.push(output);

  context.subscriptions.push(
    vscode.commands.registerCommand("codefreshMigrator.scanWorkspace", async () => scanWorkspace(output)),
    vscode.commands.registerCommand("codefreshMigrator.planMigration", async () => planMigration(output)),
    vscode.commands.registerCommand("codefreshMigrator.generateWorkflow", async () => generateWorkflowCommand(output)),
    vscode.commands.registerCommand("codefreshMigrator.explainMigration", async () => explainMigration(output))
  );
}

export async function scanWorkspace(output?: vscode.OutputChannel): Promise<string[]> {
  const roots = getWorkspaceRoots();
  if (roots.length === 0) {
    vscode.window.showWarningMessage("Open a workspace to scan for Codefresh pipelines.");
    return [];
  }

  const files = await vscode.window.withProgress({
    location: vscode.ProgressLocation.Notification,
    title: "Scanning for Codefresh pipelines",
    cancellable: false
  }, () => scanForCodefreshPipelines(roots));

  output?.appendLine(`Found ${files.length} Codefresh pipeline file(s).`);
  if (files.length === 0) {
    vscode.window.showInformationMessage("No Codefresh pipeline files found.");
  } else {
    vscode.window.showInformationMessage(`Found ${files.length} Codefresh pipeline file(s).`);
  }
  return files;
}

export async function planMigration(output?: vscode.OutputChannel, selectedPath?: string): Promise<MigrationPlan | undefined> {
  const filePath = selectedPath ?? await pickPipelineFile(output);
  if (!filePath) {
    return undefined;
  }

  const pipeline = await parseCodefreshFile(filePath);
  const plan = createMigrationPlan(pipeline);
  outputPlan(plan, output);
  await showPlanDocument(plan);
  return plan;
}

export async function generateWorkflowCommand(output?: vscode.OutputChannel, selectedPath?: string): Promise<string | undefined> {
  const plan = await planMigration(output, selectedPath);
  if (!plan) {
    return undefined;
  }

  const generated = generateWorkflow(plan);
  const validation = validateGitHubWorkflow(generated.yaml);
  if (!validation.valid) {
    vscode.window.showErrorMessage(`Generated workflow is invalid: ${validation.errors.join("; ")}`);
    return undefined;
  }

  const root = getWorkspaceRoots()[0];
  if (!root) {
    vscode.window.showWarningMessage("Open a workspace before generating a workflow.");
    return undefined;
  }

  const targetPath = path.join(root, generated.path);
  await previewWorkflow(generated.yaml);

  if (await exists(targetPath)) {
    const overwrite = await vscode.window.showWarningMessage(
      `${generated.path} already exists. Overwrite it?`,
      { modal: true },
      "Overwrite"
    );
    if (overwrite !== "Overwrite") {
      return undefined;
    }
  } else {
    const write = await vscode.window.showInformationMessage(
      `Write ${generated.path}?`,
      { modal: true },
      "Write workflow"
    );
    if (write !== "Write workflow") {
      return undefined;
    }
  }

  await fs.mkdir(path.dirname(targetPath), { recursive: true });
  await fs.writeFile(targetPath, generated.yaml, "utf8");
  output?.appendLine(`Wrote ${targetPath}`);
  vscode.window.showInformationMessage(`Generated ${generated.path}`);
  return targetPath;
}

export async function explainMigration(output?: vscode.OutputChannel, selectedPath?: string): Promise<string | undefined> {
  const plan = await planMigration(output, selectedPath);
  if (!plan) {
    return undefined;
  }

  const source = new vscode.CancellationTokenSource();
  const explanation = await explainPlanWithCopilot(plan, source.token);
  const document = await vscode.workspace.openTextDocument({
    content: explanation,
    language: "markdown"
  });
  await vscode.window.showTextDocument(document, { preview: true });
  return explanation;
}

async function pickPipelineFile(output?: vscode.OutputChannel): Promise<string | undefined> {
  const files = await scanWorkspace(output);
  if (files.length === 0) {
    return undefined;
  }
  if (files.length === 1) {
    return files[0];
  }

  const picked = await vscode.window.showQuickPick(
    files.map(file => ({
      label: workspaceRelativeOrAbsolute(file),
      description: file,
      file
    })),
    { title: "Select Codefresh pipeline" }
  );

  return picked?.file;
}

function outputPlan(plan: MigrationPlan, output?: vscode.OutputChannel): void {
  output?.appendLine(`Planned ${plan.pipeline.sourcePath} -> ${plan.targetWorkflowPath}`);
  output?.appendLine(`Confidence: ${plan.confidence}`);
  for (const warning of plan.warnings) {
    output?.appendLine(`Warning: ${warning}`);
  }
}

async function showPlanDocument(plan: MigrationPlan): Promise<void> {
  const content = [
    `# Migration plan: ${plan.pipeline.name}`,
    "",
    `Target: \`${plan.targetWorkflowPath}\``,
    `Confidence: ${plan.confidence}`,
    "",
    "## Required secrets",
    plan.requiredSecrets.length > 0 ? plan.requiredSecrets.map(secret => `- ${secret}`).join("\n") : "- None detected.",
    "",
    "## Warnings",
    plan.warnings.length > 0 ? plan.warnings.map(warning => `- ${warning}`).join("\n") : "- None.",
    "",
    "## Step mappings",
    ...plan.jobs.flatMap(job => job.mappings.map(mapping => `- ${mapping.sourceStepId} (${mapping.sourceType}) -> ${mapping.targetKind} (${mapping.confidence})`))
  ].join("\n");

  const document = await vscode.workspace.openTextDocument({ content, language: "markdown" });
  await vscode.window.showTextDocument(document, { preview: true });
}

async function previewWorkflow(yaml: string): Promise<void> {
  const document = await vscode.workspace.openTextDocument({ content: yaml, language: "yaml" });
  await vscode.window.showTextDocument(document, { preview: true });
}

async function exists(filePath: string): Promise<boolean> {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}
