import assert from "node:assert/strict";
import * as vscode from "vscode";

export async function run(): Promise<void> {
  const extension = vscode.extensions.getExtension("local.codefresh-actions-migrator");
  assert.ok(extension, "Extension should be discoverable by VS Code.");

  await extension.activate();

  const commands = await vscode.commands.getCommands(true);
  assert.ok(commands.includes("codefreshMigrator.scanWorkspace"));
  assert.ok(commands.includes("codefreshMigrator.planMigration"));
  assert.ok(commands.includes("codefreshMigrator.generateWorkflow"));
  assert.ok(commands.includes("codefreshMigrator.explainMigration"));
}
