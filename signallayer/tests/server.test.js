import test from "node:test";
import assert from "node:assert/strict";
import { handleAnalyzeRequest } from "../backend/src/server.js";

test("handleAnalyzeRequest returns structured claim analysis", async () => {
  const response = await handleAnalyzeRequest({
    message: "This stock will definitely double by next week.",
    context: [{ id: "1", text: "My friend forwarded it.", author: "other" }],
    messageId: "m1",
    conversationId: "c1"
  });

  const { statusCode, body } = response;
  assert.equal(statusCode, 200);
  assert.equal(body.messageId, "m1");
  assert.equal(Array.isArray(body.claims), true);
  assert.equal(typeof body.meta.latencyMs, "number");
});

test("handleAnalyzeRequest validates message", async () => {
  const response = await handleAnalyzeRequest({
    message: "",
    context: []
  });

  const { statusCode, body } = response;
  assert.equal(statusCode, 400);
  assert.match(body.errors[0], /message is required/);
});
