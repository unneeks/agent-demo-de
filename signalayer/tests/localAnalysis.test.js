import test from "node:test";
import assert from "node:assert/strict";
import { quickAnalyzeMessage } from "../shared/localAnalysis.js";
import { createInitialAnalysisState } from "../shared/analysisState.js";

test("quickAnalyzeMessage classifies factual, opinion, and prediction signals", () => {
  const factual = quickAnalyzeMessage("Revenue increased 12% after the onboarding update.");
  const opinion = quickAnalyzeMessage("I think the setup feels too dense for new users.");
  const prediction = quickAnalyzeMessage("If we improve the handoff, renewals will likely rise.");

  assert.equal(factual.claims[0].type, "factual");
  assert.equal(opinion.claims[0].type, "opinion");
  assert.equal(prediction.claims[0].type, "prediction");
});

test("createInitialAnalysisState marks messages without claims as idle", () => {
  const state = createInitialAnalysisState([
    {
      id: "msg-none",
      author: "A",
      text: "Okay.",
      timestamp: "2026-03-18T00:00:00.000Z"
    }
  ]);

  assert.equal(state["msg-none"].status, "idle");
  assert.equal(state["msg-none"].claims.length, 0);
});
