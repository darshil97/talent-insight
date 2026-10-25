import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { CatalogError } from "../src/lib/catalog.ts";
import { decodeCandidatePool, decodeCandidateProfile, splitResume } from "../src/lib/candidates.ts";

const fixtures = JSON.parse(readFileSync(new URL("../../backend/app/fixtures/candidates.json", import.meta.url), "utf8"));
const source = fixtures.candidates[0];
const job = JSON.parse(readFileSync(new URL("../../backend/app/fixtures/jobs/demo_ds.json", import.meta.url), "utf8"));
const summary = { id: source.id, display_name: source.display_name, headline: source.headline, summary: source.summary, is_demo: true, stated_experience: "4 years" };
const candidate = { ...summary, resume_text: source.resume_text, offset_unit: "unicode_code_point", claims: source.claims.map((claim: { quote: string }) => {
  const start = Array.from(source.resume_text.slice(0, source.resume_text.indexOf(claim.quote))).length;
  return { ...claim, start, end: start + Array.from(claim.quote).length };
}) };

test("candidate pools validate selected job context and preserve authored summaries", () => {
  assert.deepEqual(decodeCandidatePool({ job, candidates: [summary] }, job.id).candidates, [summary]);
  assert.deepEqual(decodeCandidatePool({ job, candidates: [] }, job.id).candidates, []);
  for (const body of [null, { job, candidates: null }, { job, candidates: [summary, summary] }, { job, candidates: [{ ...summary, is_demo: false }] }, { job, candidates: [{ ...summary, stated_experience: undefined }] }, { job: { ...job, id: "demo_other" }, candidates: [summary] }]) {
    assert.throws(() => decodeCandidatePool(body, job.id), CatalogError);
  }
});

test("profile contracts retain exact source quotes and support empty evidence", () => {
  const body = decodeCandidateProfile({ job, candidate }, job.id, candidate.id);
  assert.equal(body.candidate.resume_text, source.resume_text);
  assert.equal(body.candidate.claims[0].quote, source.claims[0].quote);
  assert.deepEqual(decodeCandidateProfile({ job, candidate: { ...candidate, claims: [] } }, job.id, candidate.id).candidate.claims, []);
});

test("mismatched job or candidate context is rejected before presentation", () => {
  assert.throws(() => decodeCandidateProfile({ job, candidate }, "demo_backend", candidate.id), CatalogError);
  assert.throws(() => decodeCandidateProfile({ job, candidate }, job.id, "demo_other"), CatalogError);
});

test("invalid provenance, categories, offsets and stored display context fail closed", () => {
  for (const changed of [
    { ...candidate, resume_text: "unsupported text" },
    { ...candidate, summary: "Unsupported invented qualification" },
    { ...candidate, offset_unit: "utf16" },
    { ...candidate, is_demo: false },
    { ...candidate, claims: [{ ...candidate.claims[0], quote: "Unsupported excerpt" }] },
    { ...candidate, claims: [{ ...candidate.claims[0], start: true }] },
    { ...candidate, claims: [{ ...candidate.claims[0], start: -1 }] },
    { ...candidate, claims: [{ ...candidate.claims[0], end: 1e9 }] },
    { ...candidate, claims: [{ ...candidate.claims[0], kind: "personality" }] },
  ]) assert.throws(() => decodeCandidateProfile({ job, candidate: changed }, job.id, candidate.id), CatalogError);
});

test("Unicode offsets highlight the same characters as Python, without changing the source", () => {
  const resume_text = "SYNTHETIC 🧪\nAvery\nEngineer\nAuthored summary\nUsed Python.\nEnd.";
  const quote = "Used Python.";
  const start = Array.from(resume_text.slice(0, resume_text.indexOf(quote))).length;
  const end = start + Array.from(quote).length;
  assert.notEqual(start, resume_text.indexOf(quote));
  const unicode = { id: "demo_unicode", display_name: "Avery", headline: "Engineer", summary: "Authored summary", is_demo: true,
    resume_text, offset_unit: "unicode_code_point", claims: [{ kind: "skill", label: "Python", quote, start, end }] };
  const result = decodeCandidateProfile({ job, candidate: unicode }, job.id, unicode.id);
  const highlight = splitResume(result.candidate.resume_text, start, end);
  assert.equal(highlight.excerpt, quote);
  assert.equal(highlight.before + highlight.excerpt + highlight.after, resume_text);
});
