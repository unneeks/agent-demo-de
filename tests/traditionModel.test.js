import test from "node:test";
import assert from "node:assert/strict";

import { traditions } from "../src/data/traditions.js";
import { runTraditionQuery } from "../src/domain/queryEngine.js";
import { buildSynchronologyBands, getSynchronologyLayout } from "../src/domain/synchronology.js";
import { getTraditionEndYear, sortTraditionsForTimeline } from "../src/domain/timeline.js";
import { summarizeTradition, validateTradition } from "../src/domain/traditionModel.js";

test("all seed traditions satisfy the baseline schema", () => {
  for (const tradition of traditions) {
    assert.deepEqual(validateTradition(tradition), [], tradition.id);
  }
});

test("query engine returns only outside-Vedic records for the seeded prompt", () => {
  const { results } = runTraditionQuery(traditions, "show traditions outside Vedic system");
  assert.ok(results.length > 0);
  assert.ok(results.every((item) => item.vedicRelation === "outside"));
});

test("timeline sort orders traditions by origin time", () => {
  const ordered = sortTraditionsForTimeline(traditions);
  assert.equal(ordered[0].originTime, -1500);
  assert.ok(ordered[0].originTime <= ordered.at(-1).originTime);
});

test("open-ended traditions resolve to the present year", () => {
  const modernReform = traditions.find((item) => item.id === "modern-reform");
  assert.equal(getTraditionEndYear(modernReform), 2026);
});

test("summary includes present for open-ended records", () => {
  const modernReform = traditions.find((item) => item.id === "modern-reform");
  assert.equal(
    summarizeTradition(modernReform),
    "Modern Reform Movements (1800 to present)"
  );
});

test("synchronology groups traditions into ordered category bands", () => {
  const bands = buildSynchronologyBands(traditions);
  assert.ok(bands.length >= 4);
  assert.equal(bands[0].title, "tribal religious systems");
});

test("synchronology layout returns positive width for chart cards", () => {
  const layout = getSynchronologyLayout(traditions[0], 0.42);
  assert.ok(layout.width > 0);
  assert.ok(layout.left >= 0);
});
