import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { assessDemo, assessUpload, AssessmentError, decodeAssessment } from "../src/lib/assessments.ts";
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
    unknown_categories: ["experience", "qualification", "project"], offset_unit: "unicode_code_point", notice: "Review facts.",
  },
  judgments: [{ requirement_id: "demo_requirement", status: "met", fact_indices: [0], reason: "The source mentions relevant Python work." }],
  scoring: { score: 100, lower: 100, upper: 100, resolved_count: 1, unknown_count: 0, mandatory_met: 1, mandatory_total: 1,
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
  unknown.scoring = { ...unknown.scoring, score: null as never, lower: 0, upper: 100, resolved_count: 0, unknown_count: 1, mandatory_met: 0,
    categories: [{ category: "mandatory", requirement_count: 1, resolved_count: 0, unknown_count: 1, effective_weight: 100, lower: 0, upper: 100 }] };
  assert.deepEqual(decodeAssessment(unknown, job, "uploaded_pdf"), unknown);
});

test("accepts an unavailable range when present requirements have zero configured weight", () => {
  const zero = structuredClone(result);
  zero.scoring.score = null as never;
  zero.scoring.lower = null as never;
  zero.scoring.upper = null as never;
  zero.scoring.categories[0] = { ...zero.scoring.categories[0], effective_weight: 0, lower: 0, upper: 0 };
  assert.deepEqual(decodeAssessment(zero, job, "uploaded_pdf"), zero);
});

test("upload sends only raw PDF bytes and demo request sends no profile/body", async () => {
  const fetch = mock.method(globalThis, "fetch", async (url: unknown, options?: RequestInit) => {
    assert.equal(options?.method, "POST");
    assert.equal(options?.cache, "no-store"); assert.equal(options?.credentials, "omit"); assert.equal(options?.redirect, "error");
    assert.ok(!String(url).includes("private-name"));
    if (String(url).endsWith("/resumes/assess")) {
      assert.deepEqual(options?.headers, { "Content-Type": "application/pdf" }); assert.equal(options?.body, file);
      return Response.json(result);
    }
    assert.ok(String(url).endsWith("/candidates/demo_candidate/assess"));
    assert.equal(options?.body, undefined); assert.equal(options?.headers, undefined);
    const demo = structuredClone(result); demo.structured.source.kind = "synthetic_demo"; demo.structured.source.candidate_id = "demo_candidate" as never;
    return Response.json(demo);
  });
  assert.deepEqual(await assessUpload(file, limits, job, new AbortController().signal), result);
  assert.equal((await assessDemo(job, "demo_candidate", new AbortController().signal)).structured.source.kind, "synthetic_demo");
  assert.equal(fetch.mock.callCount(), 2);
});

test("safe errors and cancellation do not expose server text", async () => {
  const fetch = mock.method(globalThis, "fetch", async () => Response.json({ error: { code: "provider_throttled", message: "private-secret" } }, { status: 503 }));
  await assert.rejects(assessDemo(job, "demo_candidate", new AbortController().signal), (error: unknown) => error instanceof AssessmentError && /busy/.test(error.message) && !error.message.includes("private-secret"));
  fetch.mock.mockImplementation(async () => new Response("private-secret", { status: 500 }));
  await assert.rejects(assessDemo(job, "demo_candidate", new AbortController().signal), AssessmentError);
  fetch.mock.mockImplementation(async () => Response.json({ error: { code: "no_extractable_text", message: "private-secret" } }, { status: 422 }));
  await assert.rejects(assessUpload(file, limits, job, new AbortController().signal), (error: unknown) => error instanceof ResumeError && /scanned/.test(error.message) && !error.message.includes("private-secret"));
  const controller = new AbortController(); controller.abort();
  fetch.mock.mockImplementation(async (_url: unknown, options?: RequestInit) => { options?.signal?.throwIfAborted(); return Response.json(result); });
  await assert.rejects(assessUpload(file, limits, job, controller.signal), { name: "AbortError" });
});
