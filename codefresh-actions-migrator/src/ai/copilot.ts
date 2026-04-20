import * as vscode from "vscode";
import type { MigrationPlan } from "../types";

export async function explainPlanWithCopilot(
  plan: MigrationPlan,
  token: vscode.CancellationToken,
  model?: vscode.LanguageModelChat
): Promise<string> {
  const selectedModel = model ?? await selectCopilotModel();
  if (!selectedModel) {
    return fallbackExplanation(plan, "Copilot is unavailable or consent was not granted.");
  }

  const prompt = [
    vscode.LanguageModelChatMessage.User(
      [
        "You are reviewing a deterministic Codefresh to GitHub Actions migration plan.",
        "Explain the mapped steps, warnings, required secrets, and manual follow-ups.",
        "Do not invent file changes. Keep the response concise and actionable.",
        "",
        JSON.stringify(toPortablePlan(plan), null, 2)
      ].join("\n")
    )
  ];

  try {
    const response = await selectedModel.sendRequest(prompt, {}, token);
    let text = "";
    for await (const fragment of response.text) {
      text += fragment;
    }
    return text.trim() || fallbackExplanation(plan, "Copilot returned an empty response.");
  } catch (error) {
    return fallbackExplanation(plan, error instanceof Error ? error.message : "Copilot request failed.");
  }
}

export async function selectCopilotModel(): Promise<vscode.LanguageModelChat | undefined> {
  try {
    const models = await vscode.lm.selectChatModels({ vendor: "copilot" });
    return models[0];
  } catch {
    return undefined;
  }
}

function fallbackExplanation(plan: MigrationPlan, reason: string): string {
  const warnings = plan.warnings.length > 0 ? plan.warnings.map(warning => `- ${warning}`).join("\n") : "- No warnings.";
  const secrets = plan.requiredSecrets.length > 0 ? plan.requiredSecrets.map(secret => `- ${secret}`).join("\n") : "- No required secrets detected.";

  return [
    `Copilot explanation unavailable: ${reason}`,
    "",
    `Deterministic confidence: ${plan.confidence}`,
    "",
    "Warnings:",
    warnings,
    "",
    "Required secrets:",
    secrets
  ].join("\n");
}

function toPortablePlan(plan: MigrationPlan): Record<string, unknown> {
  return {
    pipeline: {
      sourcePath: plan.pipeline.sourcePath,
      name: plan.pipeline.name,
      version: plan.pipeline.version,
      steps: plan.pipeline.steps.map(step => ({
        id: step.id,
        type: step.type,
        title: step.title
      }))
    },
    targetWorkflowPath: plan.targetWorkflowPath,
    warnings: plan.warnings,
    requiredSecrets: plan.requiredSecrets,
    confidence: plan.confidence,
    mappings: plan.jobs.flatMap(job => job.mappings)
  };
}
