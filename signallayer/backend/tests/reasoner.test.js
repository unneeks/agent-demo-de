import test from "node:test";
import assert from "node:assert/strict";
import {
  analyzeMessage,
  classifyClaim,
  fastClassifyMessage,
  scoreConfidence
} from "../src/reasoner.js";

test("fastClassifyMessage detects predictive claims", () => {
  const result = fastClassifyMessage("Bitcoin will definitely double next month.");
  assert.equal(result.hasClaims, true);
  assert.equal(result.signal, "claim");
});

test("classifyClaim distinguishes prediction and opinion", () => {
  assert.equal(classifyClaim("This will happen soon."), "prediction");
  assert.equal(classifyClaim("I think this is fine."), "opinion");
});

test("scoreConfidence drops when evidence conflicts", () => {
  const score = scoreConfidence("factual", "This policy is active now.", [
    { stance: "supporting" },
    { stance: "conflicting" }
  ]);

  assert.ok(score < 0.7);
});

test("analyzeMessage returns structured claims", async () => {
  const result = await analyzeMessage({
    message: "The government has banned plastic bottles nationwide starting today.",
    context: [{ id: "1", text: "Someone forwarded this in another group.", author: "other" }],
    messageId: "m-1",
    conversationId: "c-1",
    messageHash: "hash-1"
  });

  assert.equal(result.status, "ok");
  assert.equal(Array.isArray(result.claims), true);
  assert.ok(result.claims[0].summary.length > 0);
});
