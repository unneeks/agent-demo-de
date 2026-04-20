import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, it } from "node:test";
import { generateWorkflow } from "../../src/core/generator";
import { parseCodefreshSource } from "../../src/core/parser";
import { createMigrationPlan } from "../../src/core/planner";
import { validateGitHubWorkflow } from "../../src/core/validator";

const fixtures = path.resolve(__dirname, "..", "..", "..", "test", "fixtures");

function planFixture(name: string) {
  const filePath = path.join(fixtures, name);
  const source = readFileSync(filePath, "utf8");
  return createMigrationPlan(parseCodefreshSource(source, filePath));
}

describe("Codefresh converter", () => {
  it("maps freestyle steps to GitHub run steps and a job container", () => {
    const plan = planFixture("freestyle-node.codefresh.yml");
    const workflow = generateWorkflow(plan);

    assert.equal(plan.jobs[0].container, "node:20");
    assert.match(workflow.yaml, /npm ci/);
    assert.match(workflow.yaml, /npm test/);
    assert.deepEqual(validateGitHubWorkflow(workflow.yaml), { valid: true, errors: [] });
  });

  it("maps Docker build and push steps", () => {
    const plan = planFixture("docker-build-push.codefresh.yml");
    const workflow = generateWorkflow(plan);

    assert.match(workflow.yaml, /docker\/setup-buildx-action@v3/);
    assert.match(workflow.yaml, /docker\/build-push-action@v6/);
    assert.match(workflow.yaml, /docker\/login-action@v3/);
    assert.deepEqual(plan.requiredSecrets, ["REGISTRY_PASSWORD", "REGISTRY_USERNAME"]);
    assert.equal(validateGitHubWorkflow(workflow.yaml).valid, true);
  });

  it("maps composition services to GitHub job services", () => {
    const plan = planFixture("composition.codefresh.yml");
    const workflow = generateWorkflow(plan);

    assert.ok(plan.jobs[0].services);
    assert.match(workflow.yaml, /postgres:16/);
    assert.match(plan.warnings.join("\n"), /verify service health checks/i);
  });

  it("maps approval steps to a GitHub environment warning", () => {
    const plan = planFixture("approval.codefresh.yml");
    const workflow = generateWorkflow(plan);

    assert.equal(plan.jobs[0].environment, "production-approval");
    assert.match(workflow.yaml, /environment: production-approval/);
    assert.match(plan.warnings.join("\n"), /required reviewers/i);
  });

  it("preserves deploy commands with warnings", () => {
    const plan = planFixture("deploy.codefresh.yml");
    const workflow = generateWorkflow(plan);

    assert.match(workflow.yaml, /kubectl apply -f k8s\//);
    assert.match(plan.warnings.join("\n"), /verify credentials/i);
  });

  it("keeps unknown steps as manual review placeholders", () => {
    const plan = planFixture("unknown.codefresh.yml");
    const workflow = generateWorkflow(plan);

    assert.match(workflow.yaml, /Unsupported Codefresh step type: custom-plugin/);
    assert.match(plan.warnings.join("\n"), /manual review/i);
    assert.ok(plan.confidence < 0.5);
  });

  it("rejects workflows missing required top-level fields", () => {
    assert.deepEqual(validateGitHubWorkflow("name: bad\n"), {
      valid: false,
      errors: [
        "Workflow must include a top-level on trigger.",
        "Workflow must include top-level jobs."
      ]
    });
  });
});
