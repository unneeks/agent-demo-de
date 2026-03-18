import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";
import {
  getConversationId,
  getConversationTitle,
  parseMessageNodes
} from "../extension/src/lib/parser.js";

const fixturePath = new URL("./fixtures/whatsapp-dom.html", import.meta.url);

test("parseMessageNodes extracts WhatsApp-like messages", () => {
  const dom = new JSDOM(readFileSync(fixturePath, "utf8"));
  global.document = dom.window.document;

  const messages = parseMessageNodes(dom.window.document);

  assert.equal(messages.length, 2);
  assert.equal(messages[0].id, "msg-1");
  assert.equal(messages[0].author, "other");
  assert.match(messages[0].text, /plastic bottles/);
});

test("conversation helpers derive title and id from header", () => {
  const dom = new JSDOM(readFileSync(fixturePath, "utf8"));
  global.document = dom.window.document;

  assert.equal(getConversationTitle(), "Family Updates");
  assert.equal(getConversationId(), "Family Updates");
});
