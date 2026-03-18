import test from "node:test";
import assert from "node:assert/strict";
import { retrieveEvidence } from "../backend/src/ai/retrieveEvidence.js";
import { knowledgeBase } from "../backend/src/data/knowledgeBase.js";

test("retrieveEvidence ranks relevant knowledge base documents first", () => {
  const results = retrieveEvidence(
    "Enterprise buyers care about security reviews in the sales cycle.",
    knowledgeBase,
    []
  );

  assert.ok(results.length > 0);
  assert.equal(results[0].title, "Enterprise Discovery Patterns");
});
