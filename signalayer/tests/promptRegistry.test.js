import test from "node:test";
import assert from "node:assert/strict";
import { createPromptRegistry, generate_component_prompt } from "../shared/promptRegistry.js";

test("generate_component_prompt returns structured prompt content", () => {
  const result = generate_component_prompt("backend_layer", { endpoint: "/analyze" });

  assert.equal(result.component, "backend_layer");
  assert.match(result.prompt, /Testing requirements:/);
  assert.match(result.prompt, /Constraints:/);
});

test("createPromptRegistry includes all core subsystems", () => {
  const registry = createPromptRegistry();
  assert.ok(registry.browser_app_layer);
  assert.ok(registry.ui_component_layer);
  assert.ok(registry.backend_layer);
  assert.ok(registry.ai_agent_layer);
  assert.ok(registry.data_layer);
});
