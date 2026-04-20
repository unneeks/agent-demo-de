import * as vscode from "vscode";
import { explainPlanWithCopilot } from "../ai/copilot";
import { generateWorkflow } from "../core/generator";
import { parseCodefreshFile } from "../core/parser";
import { createMigrationPlan } from "../core/planner";
import { scanForCodefreshPipelines } from "../core/scanner";
import { validateGitHubWorkflow } from "../core/validator";
import { getWorkspaceRoots, resolveWorkspacePath, workspaceRelativeOrAbsolute } from "./workspace";

export function registerChatParticipant(context: vscode.ExtensionContext): void {
  const chatApi = (vscode as typeof vscode & { chat?: { createChatParticipant?: Function } }).chat;
  if (!chatApi?.createChatParticipant) {
    return;
  }

  const participant = chatApi.createChatParticipant(
    "codefresh-actions-migrator.cfmigrator",
    async (request: any, _chatContext: any, stream: any, token: vscode.CancellationToken) => {
      const command = request.command ?? inferCommand(request.prompt);

      if (command === "scan") {
        await handleScan(stream);
        return { metadata: { command } };
      }

      if (command === "plan") {
        await handlePlan(request.prompt, stream);
        return { metadata: { command } };
      }

      if (command === "generate") {
        await handleGenerate(request.prompt, stream);
        return { metadata: { command } };
      }

      if (command === "explain") {
        await handleExplain(request.prompt, request.model, stream, token);
        return { metadata: { command } };
      }

      stream.markdown([
        "I can help migrate local Codefresh YAML to GitHub Actions.",
        "",
        "Try `/scan`, `/plan path/to/codefresh.yml`, `/generate path/to/codefresh.yml`, or `/explain path/to/codefresh.yml`."
      ].join("\n"));
      return { metadata: { command: "help" } };
    }
  );

  participant.iconPath = new vscode.ThemeIcon("repo-push");
  participant.followupProvider = {
    provideFollowups() {
      return [
        { prompt: "/scan", label: "Scan for Codefresh pipelines" },
        { prompt: "/plan codefresh.yml", label: "Plan a migration" },
        { prompt: "/explain codefresh.yml", label: "Explain a migration" }
      ];
    }
  };

  context.subscriptions.push(participant);
}

async function handleScan(stream: any): Promise<void> {
  stream.progress("Scanning workspace for Codefresh pipelines...");
  const files = await scanForCodefreshPipelines(getWorkspaceRoots());
  if (files.length === 0) {
    stream.markdown("No Codefresh pipeline files were found.");
    return;
  }
  stream.markdown(files.map(file => `- \`${workspaceRelativeOrAbsolute(file)}\``).join("\n"));
}

async function handlePlan(prompt: string, stream: any): Promise<void> {
  const filePath = await resolvePromptPath(prompt);
  const plan = createMigrationPlan(await parseCodefreshFile(filePath));
  stream.markdown(renderPlan(plan));
}

async function handleGenerate(prompt: string, stream: any): Promise<void> {
  const filePath = await resolvePromptPath(prompt);
  const plan = createMigrationPlan(await parseCodefreshFile(filePath));
  const generated = generateWorkflow(plan);
  const validation = validateGitHubWorkflow(generated.yaml);

  stream.markdown([
    renderPlan(plan),
    "",
    validation.valid ? "Generated workflow YAML validates." : `Generated workflow needs review: ${validation.errors.join("; ")}`,
    "",
    "```yaml",
    generated.yaml.trim(),
    "```"
  ].join("\n"));
}

async function handleExplain(prompt: string, model: vscode.LanguageModelChat | undefined, stream: any, token: vscode.CancellationToken): Promise<void> {
  const filePath = await resolvePromptPath(prompt);
  const plan = createMigrationPlan(await parseCodefreshFile(filePath));
  const explanation = await explainPlanWithCopilot(plan, token, model);
  stream.markdown(explanation);
}

async function resolvePromptPath(prompt: string): Promise<string> {
  const candidate = prompt.replace(/^\/\w+\s*/, "").trim();
  if (candidate) {
    return resolveWorkspacePath(candidate);
  }

  const files = await scanForCodefreshPipelines(getWorkspaceRoots());
  if (files.length === 0) {
    throw new Error("No Codefresh pipeline files found.");
  }
  return files[0];
}

function inferCommand(prompt: string): string {
  const normalized = prompt.toLowerCase();
  if (normalized.includes("scan")) {
    return "scan";
  }
  if (normalized.includes("generate") || normalized.includes("workflow")) {
    return "generate";
  }
  if (normalized.includes("explain")) {
    return "explain";
  }
  if (normalized.includes("plan") || normalized.includes("migrate")) {
    return "plan";
  }
  return "help";
}

function renderPlan(plan: ReturnType<typeof createMigrationPlan>): string {
  const warnings = plan.warnings.length > 0 ? plan.warnings.map(warning => `- ${warning}`).join("\n") : "- None.";
  const secrets = plan.requiredSecrets.length > 0 ? plan.requiredSecrets.map(secret => `- ${secret}`).join("\n") : "- None detected.";
  const mappings = plan.jobs.flatMap(job => job.mappings.map(mapping => `- ${mapping.sourceStepId} (${mapping.sourceType}) -> ${mapping.targetKind} (${mapping.confidence})`));

  return [
    `Migration target: \`${plan.targetWorkflowPath}\``,
    "",
    `Confidence: ${plan.confidence}`,
    "",
    "Required secrets:",
    secrets,
    "",
    "Warnings:",
    warnings,
    "",
    "Mappings:",
    mappings.join("\n") || "- No steps mapped."
  ].join("\n");
}
