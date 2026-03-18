import test from "node:test";
import assert from "node:assert/strict";
import { handleAnalyzePayload } from "../backend/src/analyzeService.js";
import { conversationFixture } from "../shared/chatFixtures.js";

test("/analyze service returns the required schema and uses cache on repeat", async () => {
  const payload = {
    message: conversationFixture.messages[0].text,
    context: conversationFixture.messages,
    conversationId: conversationFixture.id,
    messageId: conversationFixture.messages[0].id
  };

  const first = await handleAnalyzePayload(payload);
  assert.equal(first.status, 200);
  assert.equal(first.payload.messageId, payload.messageId);
  assert.ok(Array.isArray(first.payload.claims));
  assert.equal(first.payload.meta.cacheHit, false);

  const second = await handleAnalyzePayload(payload);
  assert.equal(second.status, 200);
  assert.equal(second.payload.meta.cacheHit, true);
});

test("/analyze service rejects invalid payloads", async () => {
  const response = await handleAnalyzePayload({
    message: "",
    context: [],
    conversationId: "",
    messageId: ""
  });

  assert.equal(response.status, 400);
  assert.equal(response.payload.error, "invalid_request");
  assert.ok(response.payload.details.length > 0);
});
