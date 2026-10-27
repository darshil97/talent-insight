import assert from "node:assert/strict";
import { test } from "node:test";
import { sortForReview } from "../src/lib/candidate-order.ts";

test("sorts known ranks descending and leaves unresolved candidates last", () => {
  const rows = [
    { name: "Zed", rank: null },
    { name: "Mina", rank: 76 },
    { name: "Avery", rank: 92 },
    { name: "Jordan", rank: null },
    { name: "Kai", rank: 92 },
  ];
  assert.deepEqual(sortForReview(rows).map((row) => row.name), ["Avery", "Kai", "Mina", "Jordan", "Zed"]);
  assert.equal(rows[0].name, "Zed");
});

test("a small availability bonus can reorder close scores but never ranks a range", () => {
  // Ranks are backend ranking scores: point score plus an availability bonus of at most +5.
  const rows = [
    { name: "Slow joiner", rank: 82 + 0 },
    { name: "Fast joiner", rank: 79 + 5 },
    { name: "Unknown notice", rank: 80 + 0 },
    { name: "Range only", rank: null },
  ];
  assert.deepEqual(sortForReview(rows).map((row) => row.name), ["Fast joiner", "Slow joiner", "Unknown notice", "Range only"]);
});
