import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { assessUpload, AssessmentError, decodeAssessment } from "../src/lib/assessments.ts";
import type { JobDetail } from "../src/lib/catalog.ts";
import { ResumeError } from "../src/lib/resumes.ts";

const job: JobDetail = {
  id: "demo_job", title: "Demo role", client: "Demo client", description: "Synthetic role", skills: ["Python"], is_demo: true,
  screening_criteria: [], questions: [{ id: "demo_question", text: "Describe the work.", requirement_ids: ["demo_requirement"] }],
  requirements: [{ id: "demo_requirement", category: "mandatory", description: "Python work", minimum_years: null, sort_order: 0 }],
};
const source = "Synthetic 😀 Python work";
const quote = "Python work";
const start = Array.from(source.indexOf("Python") >= 0 ? source.slice(0, source.indexOf("Python")) : "").length;
const result = {
  structured: {
    job: { id: job.id, title: job.title, skills: job.skills, requirements: job.requirements },
    source: { kind: "uploaded_pdf", candidate_id: null, pages: [{ page_number: 1, text: source }] },
    mode: "bedrock", model_id: "demo-model", facts: [{ kind: "skill", value: "Python", evidence: [{ page_number: 1, quote, start, end: start + Array.from(quote).length }] }],
    identity: null as unknown,
    unknown_categories: ["experience", "qualification", "project"], offset_unit: "unicode_code_point", notice: "Review facts.",
  },
  judgments: [{ requirement_id: "demo_requirement", status: "met", fact_indices: [0], reason: "The source mentions relevant Python work." }],
  scoring: { score: 100, lower: 100, upper: 100, estimate: 100, confidence: "very_high", resolved_count: 1, unknown_count: 0, mandatory_met: 1, mandatory_total: 1,
    categories: [{ category: "mandatory", requirement_count: 1, resolved_count: 1, unknown_count: 0, effective_weight: 100, lower: 100, upper: 100 }] },
  notice: "Human review required.",
};
const limits = { max_bytes: 5 * 1024 * 1024, max_pages: 20, max_characters: 100_000 };
const file = new File(["%PDF-1.7 synthetic"], "private-name.pdf", { type: "application/pdf" });
afterEach(() => mock.restoreAll());

test("accepts matching job context and Unicode source citations", () => {
  assert.deepEqual(decodeAssessment(result, job, "uploaded_pdf"), result);
  const demo = structuredClone(result);
  demo.structured.source.kind = "synthetic_demo";
  demo.structured.source.candidate_id = "demo_candidate" as never;
  assert.deepEqual(decodeAssessment(demo, job, "synthetic_demo", "demo_candidate"), demo);
});

test("rejects foreign context, forged citations and inconsistent score availability", () => {
  const changes: ((value: typeof result) => void)[] = [
    (value) => { value.structured.job.id = "demo_other"; },
    (value) => { value.structured.job.requirements[0].description = "Different"; },
    (value) => { value.structured.source.pages[0].text = "Unrelated"; },
    (value) => { value.structured.facts[0].evidence[0].start += 1; },
    (value) => { value.judgments[0].fact_indices = [1]; },
    (value) => { value.judgments[0].requirement_id = "demo_other"; },
    (value) => { value.scoring.unknown_count = 1; },
    (value) => { value.scoring.mandatory_met = 0; },
  ];
  for (const change of changes) {
    const invalid = structuredClone(result); change(invalid);
    assert.throws(() => decodeAssessment(invalid, job, "uploaded_pdf"), AssessmentError);
  }
  assert.throws(() => decodeAssessment(result, job, "synthetic_demo", "demo_candidate"), AssessmentError);
  const unknown = structuredClone(result);
  unknown.structured.mode = "mock"; unknown.structured.model_id = null as never;
  unknown.judgments[0].status = "unknown"; unknown.judgments[0].fact_indices = [];
  unknown.scoring = { ...unknown.scoring, score: null as never, lower: 0, upper: 100, estimate: 50, confidence: "low" as never, resolved_count: 0, unknown_count: 1, mandatory_met: 0,
    categories: [{ category: "mandatory", requirement_count: 1, resolved_count: 0, unknown_count: 1, effective_weight: 100, lower: 0, upper: 100 }] };
  assert.deepEqual(decodeAssessment(unknown, job, "uploaded_pdf"), unknown);
});

test("accepts an unavailable range when present requirements have zero configured weight", () => {
  const zero = structuredClone(result);
  zero.scoring.score = null as never;
  zero.scoring.lower = null as never;
  zero.scoring.upper = null as never;
  zero.scoring.estimate = null as never;
  zero.scoring.confidence = null as never;
  zero.scoring.categories[0] = { ...zero.scoring.categories[0], effective_weight: 0, lower: 0, upper: 0 };
  assert.deepEqual(decodeAssessment(zero, job, "uploaded_pdf"), zero);
});

test("upload sends only raw PDF bytes", async () => {
  const fetch = mock.method(globalThis, "fetch", async (url: unknown, options?: RequestInit) => {
    assert.equal(options?.method, "POST");
    assert.equal(options?.cache, "no-store"); assert.equal(options?.credentials, "omit"); assert.equal(options?.redirect, "error");
    assert.ok(!String(url).includes("private-name"));
    if (String(url).endsWith("/resumes/assess")) {
      assert.deepEqual(options?.headers, { "Content-Type": "application/pdf" }); assert.equal(options?.body, file);
      return Response.json(result);
    }
    throw new Error("Unexpected request");
  });
  assert.deepEqual(await assessUpload(file, limits, job, new AbortController().signal), result);
  assert.equal(fetch.mock.callCount(), 1);
});

test("upload sends the bot check token in a header only when one is given", async () => {
  const fetch = mock.method(globalThis, "fetch", async (_url: unknown, options?: RequestInit) => {
    assert.deepEqual(options?.headers, { "Content-Type": "application/pdf", "X-Bot-Check-Token": "cf.token-1" });
    assert.equal(options?.body, file);
    return Response.json(result);
  });
  assert.deepEqual(await assessUpload(file, limits, job, new AbortController().signal, "cf.token-1"), result);
  assert.equal(fetch.mock.callCount(), 1);
});

test("bot check and daily limit codes have their own messages", async () => {
  const cases: [string, number, RegExp][] = [["bot_check_failed", 403, /bot check did not pass/], ["bot_check_unavailable", 503, /bot check is unavailable/], ["ai_daily_limit", 429, /daily assessment limit/]];
  const fetch = mock.method(globalThis, "fetch", async () => new Response());
  for (const [code, status, message] of cases) {
    fetch.mock.mockImplementation(async () => Response.json({ error: { code, message: "private-secret" } }, { status }));
    await assert.rejects(assessUpload(file, limits, job, new AbortController().signal, "cf.token"), (error: unknown) => error instanceof AssessmentError && message.test(error.message) && !error.message.includes("private-secret"));
  }
});

test("safe errors and cancellation do not expose server text", async () => {
  const fetch = mock.method(globalThis, "fetch", async () => Response.json({ error: { code: "provider_throttled", message: "private-secret" } }, { status: 503 }));
  await assert.rejects(assessUpload(file, limits, job, new AbortController().signal), (error: unknown) => error instanceof AssessmentError && /busy/.test(error.message) && !error.message.includes("private-secret"));
  fetch.mock.mockImplementation(async () => new Response("private-secret", { status: 500 }));
  await assert.rejects(assessUpload(file, limits, job, new AbortController().signal), AssessmentError);
  fetch.mock.mockImplementation(async () => Response.json({ error: { code: "no_extractable_text", message: "private-secret" } }, { status: 422 }));
  await assert.rejects(assessUpload(file, limits, job, new AbortController().signal), (error: unknown) => error instanceof ResumeError && /scanned/.test(error.message) && !error.message.includes("private-secret"));
  const controller = new AbortController(); controller.abort();
  fetch.mock.mockImplementation(async (_url: unknown, options?: RequestInit) => { options?.signal?.throwIfAborted(); return Response.json(result); });
  await assert.rejects(assessUpload(file, limits, job, controller.signal), { name: "AbortError" });
});

test("identity is optional display text that must match the source exactly", () => {
  const named = structuredClone(result);
  const nameStart = Array.from(source.slice(0, source.indexOf("Synthetic"))).length;
  named.structured.identity = { name: { value: "Synthetic", page_number: 1, start: nameStart, end: nameStart + 9 }, current_title: null };
  assert.deepEqual(decodeAssessment(named, job, "uploaded_pdf"), named);
  for (const identity of [
    { name: { value: "Invented Person", page_number: 1, start: 0, end: 15 }, current_title: null },
    { name: { value: "Synthetic", page_number: 2, start: 0, end: 9 }, current_title: null },
    "Synthetic",
    undefined,
  ]) {
    const changed = structuredClone(result);
    changed.structured.identity = identity;
    assert.throws(() => decodeAssessment(changed, job, "uploaded_pdf"), AssessmentError);
  }
});

test("comparable experience is a resolved status but not a mandatory met", () => {
  const comparable = structuredClone(result);
  comparable.judgments[0].status = "transferable";
  comparable.scoring = { ...comparable.scoring, score: 75, lower: 75, upper: 75, estimate: 75, mandatory_met: 0,
    categories: [{ ...comparable.scoring.categories[0], lower: 75, upper: 75 }] };
  assert.deepEqual(decodeAssessment(comparable, job, "uploaded_pdf"), comparable);
  comparable.scoring.mandatory_met = 1;
  assert.throws(() => decodeAssessment(comparable, job, "uploaded_pdf"), AssessmentError);
});

test("the estimate is the range midpoint and confidence reflects unknown weight", () => {
  const open = structuredClone(result);
  open.judgments[0] = { ...open.judgments[0], status: "unknown", fact_indices: [], reason: "Needs review." };
  open.scoring = { ...open.scoring, score: null as never, lower: 0, upper: 100, estimate: 50, confidence: "low" as never, resolved_count: 0, unknown_count: 1, mandatory_met: 0,
    categories: [{ ...open.scoring.categories[0], resolved_count: 0, unknown_count: 1, lower: 0, upper: 100 }] };
  assert.deepEqual(decodeAssessment(open, job, "uploaded_pdf"), open);
  for (const change of [{ estimate: 60 }, { confidence: "very_high" }, { confidence: "certain" }, { estimate: null }]) {
    assert.throws(() => decodeAssessment({ ...open, scoring: { ...open.scoring, ...change } }, job, "uploaded_pdf"), AssessmentError);
  }
});
