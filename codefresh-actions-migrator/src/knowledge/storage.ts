import { promises as fs } from "fs";
import * as vscode from "vscode";

const DEFAULT_USER_PATTERNS = "[]\n";

export async function initializeKnowledgeStorage(context: vscode.ExtensionContext): Promise<void> {
  const directory = context.globalStorageUri.fsPath;
  const userPatternsPath = vscode.Uri.joinPath(context.globalStorageUri, "user-patterns.json").fsPath;

  await fs.mkdir(directory, { recursive: true });

  try {
    await fs.access(userPatternsPath);
  } catch {
    await fs.writeFile(userPatternsPath, DEFAULT_USER_PATTERNS, "utf8");
  }
}
