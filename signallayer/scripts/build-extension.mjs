import { mkdir, cp } from "node:fs/promises";
import path from "node:path";
import { build } from "esbuild";

const root = new URL("../", import.meta.url);
const extensionDir = path.resolve(root.pathname, "extension");
const distDir = path.resolve(extensionDir, "dist");

await mkdir(distDir, { recursive: true });

await build({
  entryPoints: [path.resolve(extensionDir, "src/content/main.jsx")],
  bundle: true,
  format: "iife",
  outfile: path.resolve(distDir, "content.js"),
  jsx: "automatic",
  loader: {
    ".js": "jsx"
  },
  define: {
    "process.env.NODE_ENV": '"production"'
  }
});

await cp(path.resolve(extensionDir, "public/manifest.json"), path.resolve(distDir, "manifest.json"));
