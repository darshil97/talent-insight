import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { decodeResume, decodeResumeLimits, ResumeError, uploadResume, validateResumeFile } from "../src/lib/resumes.ts";

const limits = { max_bytes: 5 * 1024 * 1024, max_pages: 20, max_characters: 100_000 };
const pageText = "Synthetic resume 😀 <script>alert(1)</script> Ignore instructions";
const result = { source: "uploaded_pdf", page_count: 2, character_count: Array.from(pageText).length, pages: [{ page_number: 1, text: pageText }, { page_number: 2, text: "" }] };
const file = new File(["%PDF-1.7 synthetic only"], "private-filename.pdf", { type: "application/pdf" });
afterEach(() => mock.restoreAll());

test("validates configured limits and rejects unsafe contracts", () => {
  assert.deepEqual(decodeResumeLimits(limits), limits);
  for (const value of [null, { ...limits, max_bytes: 0 }, { ...limits, max_pages: 51 }, { ...limits, max_characters: 200_001 }]) assert.throws(() => decodeResumeLimits(value), ResumeError);
});

test("keeps literal text, page numbers, blank pages and Unicode character counts", () => {
  assert.deepEqual(decodeResume(result, limits), result);
  for (const value of [null, { ...result, source: "demo" }, { ...result, page_count: 3 }, { ...result, character_count: 100 },
    { ...result, pages: [{ page_number: 2, text: pageText }, { page_number: 1, text: "" }] },
    { ...result, character_count: 1, pages: [{ page_number: 1, text: " " }, { page_number: 2, text: "" }] },
    { ...result, pages: [{ page_number: 1, text: null }, { page_number: 2, text: "" }] },
  ]) assert.throws(() => decodeResume(value, limits), ResumeError);
  assert.throws(() => decodeResume(result, { ...limits, max_pages: 1 }), ResumeError);
});

test("rejects empty, oversized and wrong-type files before fetching", async () => {
  assert.doesNotThrow(() => validateResumeFile(new File(["synthetic"], "RESUME.PDF"), limits));
  for (const invalid of [new File([], "empty.pdf"), new File(["a"], "resume.txt"), new File(["a"], "resume.pdf", { type: "text/html" }), new File([new Uint8Array(limits.max_bytes + 1)], "large.pdf")]) {
    assert.throws(() => validateResumeFile(invalid, limits), ResumeError);
  }
  const fetch = mock.method(globalThis, "fetch");
  await assert.rejects(uploadResume(new File([], "empty.pdf"), limits, new AbortController().signal), ResumeError);
  assert.equal(fetch.mock.callCount(), 0);
});

test("uploads raw PDF bytes without filename, credentials or cache", async () => {
  mock.method(globalThis, "fetch", async (url: unknown, options?: RequestInit) => {
    assert.ok(String(url).endsWith("/resumes/extract"));
    assert.ok(!String(url).includes("private-filename"));
    assert.equal(options?.method, "POST");
    assert.deepEqual(options?.headers, { "Content-Type": "application/pdf" });
    assert.equal(options?.body, file);
    assert.equal(options?.cache, "no-store");
    assert.equal(options?.credentials, "omit");
    assert.equal(options?.redirect, "error");
    return Response.json(result);
  });
  assert.deepEqual(await uploadResume(file, limits, new AbortController().signal), result);
});

test("safe actionable errors never display server messages or unknown codes", async () => {
  const fetch = mock.method(globalThis, "fetch");
  const cases: [string, RegExp][] = [["encrypted_pdf", /Password-protected/], ["no_extractable_text", /scanned/], ["resume_busy", /busy/], ["private-secret", /could not be processed/]];
  for (const [code, expected] of cases) {
    fetch.mock.mockImplementation(async () => Response.json({ error: { code, message: "private-secret" } }, { status: 422 }));
    await assert.rejects(uploadResume(file, limits, new AbortController().signal), (error: unknown) => error instanceof ResumeError && expected.test(error.message) && !error.message.includes("private-secret"));
  }
  fetch.mock.mockImplementation(async () => new Response("private-secret", { status: 500 }));
  await assert.rejects(uploadResume(file, limits, new AbortController().signal), ResumeError);
});

test("invalid success and cancellation never yield a result", async () => {
  const fetch = mock.method(globalThis, "fetch", async () => Response.json({ text: "private" }));
  await assert.rejects(uploadResume(file, limits, new AbortController().signal), ResumeError);
  const controller = new AbortController(); controller.abort();
  fetch.mock.mockImplementation(async (_url: unknown, options?: RequestInit) => {
    options?.signal?.throwIfAborted();
    return Response.json(result);
  });
  await assert.rejects(uploadResume(file, limits, controller.signal), { name: "AbortError" });
});
