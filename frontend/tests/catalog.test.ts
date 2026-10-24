import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { afterEach, mock, test } from "node:test";
import { apiBaseUrl, CatalogError, decodeJob, decodeJobs, fetchCatalog } from "../src/lib/catalog.ts";

const source = JSON.parse(readFileSync(new URL("../../backend/app/fixtures/jobs/demo_ds.json", import.meta.url), "utf8"));
const detail = { ...source, requirements: source.requirements.map((row: object, sort_order: number) => ({ ...row, sort_order })) };
const summary = { id: source.id, title: source.title, client: source.client, description: source.description, skills: source.skills, is_demo: true };
afterEach(() => mock.restoreAll());

test("decodes API contracts from the editable source and keeps requirement order", () => {
  assert.equal(decodeJobs({ jobs: [summary] })[0].id, source.id);
  assert.equal(decodeJob({ ...detail, requirements: [...detail.requirements].reverse() }).requirements[0].id, source.requirements[0].id);
  assert.deepEqual(decodeJobs({ jobs: [] }), []);
});

test("rejects malformed, non-demo and inconsistent API data", () => {
  for (const input of [null, [], { jobs: "wrong" }, { jobs: [{ ...summary, is_demo: false }] }, { jobs: [summary, summary] }]) {
    assert.throws(() => decodeJobs(input), CatalogError);
  }
  for (const input of [
    { ...detail, skills: [null] },
    { ...detail, requirements: [{ ...detail.requirements[0], category: "score" }] },
    { ...detail, requirements: [{ ...detail.requirements[0], minimum_years: 5 }] },
    { ...detail, questions: [{ ...detail.questions[0], requirement_ids: ["demo_missing"] }] },
  ]) assert.throws(() => decodeJob(input), CatalogError);
});

test("public API setting allows only a credential-free secure origin or loopback HTTP", () => {
  assert.equal(apiBaseUrl("http://127.0.0.1:8000/"), "http://127.0.0.1:8000");
  assert.equal(apiBaseUrl("https://api.example.com"), "https://api.example.com");
  for (const url of ["http://example.com", "https://key:secret@example.com", "https://example.com/path", "https://example.com?key=secret", "https://example.com#data", "file:///tmp", "invalid", ""]) {
    assert.throws(() => apiBaseUrl(url), (error: unknown) => error instanceof CatalogError && !error.message.includes("secret"));
  }
});

test("fetch uses GET/no-store/no credentials and decodes the response", async () => {
  const request = mock.method(globalThis, "fetch", async (_url: unknown, options?: RequestInit) => {
    assert.equal(options?.method, "GET");
    assert.equal(options?.cache, "no-store");
    assert.equal(options?.credentials, "omit");
    assert.equal(options?.redirect, "error");
    return Response.json({ jobs: [summary] });
  });
  const result = await fetchCatalog("/jobs", decodeJobs, new AbortController().signal);
  assert.equal(request.mock.callCount(), 1);
  assert.equal(result[0].id, source.id);
});

test("404 and unavailable responses stay distinct without echoing internal errors", async () => {
  const request = mock.method(globalThis, "fetch");
  for (const status of [404, 503, 500]) {
    request.mock.mockImplementation(async () => new Response("secret internal error", { status }));
    await assert.rejects(fetchCatalog("/jobs/demo_ds", decodeJob, new AbortController().signal),
      (error: unknown) => error instanceof CatalogError && error.kind === (status === 404 ? "not_found" : "unavailable") && !error.message.includes("secret"));
  }
});

test("malformed success and cancellation never fall back to fixture data", async () => {
  const request = mock.method(globalThis, "fetch", async () => Response.json({ jobs: null }));
  await assert.rejects(fetchCatalog("/jobs", decodeJobs, new AbortController().signal), CatalogError);
  const controller = new AbortController();
  controller.abort();
  request.mock.mockImplementation(async (_url: unknown, options?: RequestInit) => {
    options?.signal?.throwIfAborted();
    return Response.json({ jobs: [summary] });
  });
  await assert.rejects(fetchCatalog("/jobs", decodeJobs, controller.signal), { name: "AbortError" });
});
