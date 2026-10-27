import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { AvailabilityError, availabilityLabel, isAvailability, requestAvailability } from "../src/lib/availability.ts";

afterEach(() => mock.restoreAll());
const base = { last_working_day: null, notice_days: null };

test("labels never present missing availability as a penalty", () => {
  assert.equal(availabilityLabel(null), "Not provided · no penalty");
  assert.equal(availabilityLabel({ status: null, ...base, days_to_join: null, bonus: 0 }), "Not provided · no penalty");
  assert.equal(availabilityLabel({ status: "immediate", ...base, days_to_join: 0, bonus: 5 }), "Available now · +5");
  assert.equal(availabilityLabel({ status: "serving_notice", last_working_day: "2026-11-16", notice_days: null, days_to_join: 20, bonus: 4 }), "Joins in ~20 days · +4");
  assert.equal(availabilityLabel({ status: "serving_notice", last_working_day: "2026-10-01", notice_days: null, days_to_join: 0, bonus: 5 }), "Notice period ended · +5");
  assert.equal(availabilityLabel({ status: "not_serving", last_working_day: null, notice_days: 120, days_to_join: 120, bonus: 0 }), "120-day notice");
});

test("availability contracts reject inconsistent details", () => {
  assert.ok(isAvailability({ status: "not_serving", last_working_day: null, notice_days: 60, days_to_join: 60, bonus: 2 }));
  for (const value of [
    { status: "immediate", ...base, days_to_join: 3, bonus: 5 },
    { status: "serving_notice", last_working_day: "16/11/2026", notice_days: null, days_to_join: 20, bonus: 4 },
    { status: null, ...base, days_to_join: null, bonus: 1 },
    { status: "not_serving", last_working_day: null, notice_days: 400, days_to_join: 400, bonus: 0 },
    { status: "immediate", ...base, days_to_join: 0, bonus: 11 },
  ]) assert.equal(isAvailability(value), false);
});

test("requests send details in the JSON body and validate the backend result", async () => {
  const calls: { url: string; init: RequestInit }[] = [];
  mock.method(globalThis, "fetch", async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return new Response(JSON.stringify({ availability: { status: "not_serving", last_working_day: null, notice_days: 28, days_to_join: 28, bonus: 4 }, ranking_score: 74 }), { status: 200 });
  });
  const result = await requestAvailability({ status: "not_serving", last_working_day: null, notice_days: 28 }, 70, new AbortController().signal);
  assert.equal(result.ranking_score, 74);
  assert.ok(calls[0].url.endsWith("/availability") && !calls[0].url.includes("28"));
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(String(calls[0].init.body)), { availability: { status: "not_serving", last_working_day: null, notice_days: 28 }, match_estimate: 70 });
  assert.equal(calls[0].init.credentials, "omit");
});

test("a forged ranking or failed request becomes a safe error", async () => {
  mock.method(globalThis, "fetch", async () => new Response(JSON.stringify({ availability: { status: "immediate", last_working_day: null, notice_days: null, days_to_join: 0, bonus: 5 }, ranking_score: 99 }), { status: 200 }));
  await assert.rejects(requestAvailability({ status: "immediate", ...base }, 70, new AbortController().signal), AvailabilityError);
  mock.restoreAll();
  mock.method(globalThis, "fetch", async () => new Response("{}", { status: 422 }));
  await assert.rejects(requestAvailability({ status: null, ...base }, null, new AbortController().signal), AvailabilityError);
});
