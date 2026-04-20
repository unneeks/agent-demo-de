import path from "path";
import * as vscode from "vscode";

export function getWorkspaceRoots(): string[] {
  return vscode.workspace.workspaceFolders?.map(folder => folder.uri.fsPath) ?? [];
}

export function workspaceRelativeOrAbsolute(filePath: string): string {
  const root = getWorkspaceRoots()[0];
  if (!root) {
    return filePath;
  }
  const relative = path.relative(root, filePath);
  return relative.startsWith("..") ? filePath : relative;
}

export async function resolveWorkspacePath(inputPath: string): Promise<string> {
  if (path.isAbsolute(inputPath)) {
    return inputPath;
  }
  const root = getWorkspaceRoots()[0];
  if (!root) {
    throw new Error("Open a workspace before using a relative path.");
  }
  return path.join(root, inputPath);
}
