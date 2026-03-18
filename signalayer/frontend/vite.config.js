import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  root: path.resolve(import.meta.dirname, "."),
  server: {
    port: 4174
  },
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "src")
    }
  },
  build: {
    outDir: path.resolve(import.meta.dirname, "dist"),
    emptyOutDir: true
  }
});
