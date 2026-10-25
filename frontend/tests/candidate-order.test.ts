import assert from "node:assert/strict";
import { test } from "node:test";
import { sortByMatchScore } from "../src/lib/candidate-order.ts";

test("sorts known point scores descending and leaves unresolved candidates last", () => {
  const rows = [
    { name: "Zed", score: null },
    { name: "Mina", score: 76 },
    { name: "Avery", score: 92 },
    { name: "Jordan", score: null },
    { name: "Kai", score: 92 },
  ];
  assert.deepEqual(sortByMatchScore(rows).map((row) => row.name), ["Avery", "Kai", "Mina", "Jordan", "Zed"]);
  assert.equal(rows[0].name, "Zed");
});
