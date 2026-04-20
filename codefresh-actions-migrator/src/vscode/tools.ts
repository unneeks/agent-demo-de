import * as vscode from "vscode";
import { generateWorkflow } from "../core/generator";
import { parseCodefreshFile } from "../core/parser";
import { createMigrationPlan } from "../core/planner";
import { scanForCodefreshPipelines } from "../core/scanner";
import { validateGitHubWorkflow } from "../core/validator";
import { getWorkspaceRoots, resolveWorkspacePath, workspaceRelativeOrAbsolute } from "./workspace";

export function registerLanguageModelTools(context: vscode.ExtensionContext): void {
  const registerTool = (vscode.lm as any).registerTool as Function | undefined;
  if (!registerTool) {
    return;
  }

  context.subscriptions.push(
    registerTool("scan_codefresh_pipelines", new ScanCodefreshPipelinesTool()),
    registerTool("plan_codefresh_migration", new PlanCodefreshMigrationTool()),
    registerTool("validate_github_workflow", new ValidateGitHubWorkflowTool())
  );
}

class ScanCodefreshPipelinesTool {
  async invoke(): Promise<any> {
    const files = await scanForCodefreshPipelines(getWorkspaceRoots());
    return toolResult({ files: files.map(file => workspaceRelativeOrAbsolute(file)) });
  }

  prepareInvocation(): unknown {
    return {
      invocationMessage: "Scanning for Codefresh pipelines",
      confirmationMessages: {
        title: "Scan workspace for Codefresh pipelines",
        message: "Find local codefresh.yml, codefresh.yaml, and .codefresh/*.yml files."
      }
    };
  }
}

class PlanCodefreshMigrationTool {
  async invoke(options: { input: { path: string } }): Promise<any> {
    const filePath = await resolveWorkspacePath(options.input.path);
    const plan = createMigrationPlan(await parseCodefreshFile(filePath));
    const generated = generateWorkflow(plan);
    return toolResult({
      plan,
      generatedWorkflow: generated
    });
  }

  prepareInvocation(options: { input: { path: string } }): unknown {
    return {
      invocationMessage: `Planning migration for ${options.input.path}`,
      confirmationMessages: {
        title: "Plan Codefresh migration",
        message: `Parse and plan migration for ${options.input.path}.`
      }
    };
  }
}

class ValidateGitHubWorkflowTool {
  async invoke(options: { input: { yaml: string } }): Promise<any> {
    return toolResult(validateGitHubWorkflow(options.input.yaml));
  }

  prepareInvocation(): unknown {
    return {
      invocationMessage: "Validating GitHub Actions workflow",
      confirmationMessages: {
        title: "Validate workflow YAML",
        message: "Parse workflow YAML and check required GitHub Actions fields."
      }
    };
  }
}

function toolResult(value: unknown): any {
  const api = vscode as typeof vscode & {
    LanguageModelToolResult?: new (parts: unknown[]) => unknown;
    LanguageModelTextPart?: new (value: string) => unknown;
  };

  if (api.LanguageModelToolResult && api.LanguageModelTextPart) {
    return new api.LanguageModelToolResult([
      new api.LanguageModelTextPart(JSON.stringify(value, null, 2))
    ]);
  }

  return value;
}
