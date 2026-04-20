import { promises as fs } from "fs";
import path from "path";

const CODEFRESH_FILENAMES = new Set(["codefresh.yml", "codefresh.yaml"]);
type NamedDirent = {
  name: string;
  isDirectory(): boolean;
  isFile(): boolean;
};

export async function scanForCodefreshPipelines(workspaceRoots: string[]): Promise<string[]> {
  const results = new Set<string>();

  for (const root of workspaceRoots) {
    await scanDirectory(root, root, results);
  }

  return [...results].sort();
}

async function scanDirectory(root: string, current: string, results: Set<string>): Promise<void> {
  let entries: NamedDirent[];
  try {
    entries = await fs.readdir(current, { withFileTypes: true });
  } catch {
    return;
  }

  for (const entry of entries) {
    if (entry.name === "node_modules" || entry.name === ".git" || entry.name === "out") {
      continue;
    }

    const absolute = path.join(current, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === ".codefresh") {
        await collectCodefreshDirectory(absolute, results);
      } else {
        await scanDirectory(root, absolute, results);
      }
      continue;
    }

    if (entry.isFile() && CODEFRESH_FILENAMES.has(entry.name.toLowerCase())) {
      results.add(absolute);
    }
  }
}

async function collectCodefreshDirectory(directory: string, results: Set<string>): Promise<void> {
  let entries: NamedDirent[];
  try {
    entries = await fs.readdir(directory, { withFileTypes: true });
  } catch {
    return;
  }

  for (const entry of entries) {
    if (!entry.isFile()) {
      continue;
    }
    if (entry.name.endsWith(".yml") || entry.name.endsWith(".yaml")) {
      results.add(path.join(directory, entry.name));
    }
  }
}
