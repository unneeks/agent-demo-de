import * as vscode from "vscode";
import { initializeKnowledgeStorage } from "./knowledge/storage";
import { registerChatParticipant } from "./vscode/chat";
import { registerCommands } from "./vscode/commands";
import { registerLanguageModelTools } from "./vscode/tools";

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  await initializeKnowledgeStorage(context);
  registerCommands(context);
  registerChatParticipant(context);
  registerLanguageModelTools(context);
}

export function deactivate(): void {}
