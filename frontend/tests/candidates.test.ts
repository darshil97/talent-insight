import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { CatalogError } from "../src/lib/catalog.ts";
import { decodeCandidatePool, decodeCandidateProfile, splitResume } from "../src/lib/candidates.ts";

const fixtures = JSON.parse(readFileSync(new URL("../../backend/app/fixtures/candidates.json", import.meta.url), "utf8"));
const source = fixtures.candidates[0];
const jobSource = JSON.parse(readFileSync(new URL("../../backend/app/fixtures/jobs/demo_ds.json", import.meta.url), "utf8"));
const job = { ...jobSource, requirements: jobSource.requirements.map((row: object, sort_order: number) => ({ ...row, sort_order })) };
const none = { status: null, last_working_day: null, notice_days: null, days_to_join: null, bonus: 0 };
const summary = { id: source.id, display_name: source.display_name, headline: source.headline, summary: source.summary, is_demo: true, stated_experience: "4 years", snapshot_available: false, match_score: null, score_lower: null, score_upper: null, match_estimate: null, confidence: null, availability: none, ranking_score: null };
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
  const body = decodeCandidateProfile({ job, candidate, availability: none, assessment: null }, job.id, candidate.id);
  assert.equal(body.candidate.resume_text, source.resume_text);
  assert.equal(body.candidate.claims[0].quote, source.claims[0].quote);
  assert.deepEqual(decodeCandidateProfile({ job, candidate: { ...candidate, claims: [] }, availability: none, assessment: null }, job.id, candidate.id).candidate.claims, []);
});

test("mismatched job or candidate context is rejected before presentation", () => {
  assert.throws(() => decodeCandidateProfile({ job, candidate, availability: none, assessment: null }, "demo_backend", candidate.id), CatalogError);
  assert.throws(() => decodeCandidateProfile({ job, candidate, availability: none, assessment: null }, job.id, "demo_other"), CatalogError);
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
  ]) assert.throws(() => decodeCandidateProfile({ job, candidate: changed, availability: none, assessment: null }, job.id, candidate.id), CatalogError);
});

test("Unicode offsets highlight the same characters as Python, without changing the source", () => {
  const resume_text = "SYNTHETIC 🧪\nAvery\nEngineer\nAuthored summary\nUsed Python.\nEnd.";
  const quote = "Used Python.";
  const start = Array.from(resume_text.slice(0, resume_text.indexOf(quote))).length;
  const end = start + Array.from(quote).length;
  assert.notEqual(start, resume_text.indexOf(quote));
  const unicode = { id: "demo_unicode", display_name: "Avery", headline: "Engineer", summary: "Authored summary", is_demo: true,
    resume_text, offset_unit: "unicode_code_point", claims: [{ kind: "skill", label: "Python", quote, start, end }] };
  const result = decodeCandidateProfile({ job, candidate: unicode, availability: none, assessment: null }, job.id, unicode.id);
  const highlight = splitResume(result.candidate.resume_text, start, end);
  assert.equal(highlight.excerpt, quote);
  assert.equal(highlight.before + highlight.excerpt + highlight.after, resume_text);
});

test("availability and ranking stay consistent with the match score", () => {
  const scored = { ...summary, snapshot_available: true, match_score: 80, score_lower: 80, score_upper: 80, match_estimate: 80, confidence: "very_high" };
  const soon = { status: "serving_notice", last_working_day: "2026-11-16", notice_days: null, days_to_join: 20, bonus: 4 };
  assert.equal(decodeCandidatePool({ job, candidates: [{ ...scored, availability: soon, ranking_score: 84 }] }, job.id).candidates[0].ranking_score, 84);
  assert.equal(decodeCandidatePool({ job, candidates: [{ ...scored, ranking_score: 80 }] }, job.id).candidates[0].availability.status, null);
  for (const changed of [
    { ...scored, availability: soon, ranking_score: 80 },
    { ...scored, ranking_score: null },
    { ...summary, ranking_score: 4 },
    { ...summary, availability: { ...none, bonus: 2 } },
    { ...summary, availability: { ...soon, last_working_day: null } },
    { ...summary, availability: { status: "not_serving", last_working_day: null, notice_days: 30, days_to_join: 10, bonus: 4 } },
    { ...summary, availability: { ...none, status: "on_leave" } },
    { ...summary, availability: undefined },
  ]) assert.throws(() => decodeCandidatePool({ job, candidates: [changed] }, job.id), CatalogError);
  assert.throws(() => decodeCandidateProfile({ job, candidate, assessment: null }, job.id, candidate.id), CatalogError);
});

test("ranges rank by their estimate with a confidence label", () => {
  const range = { ...summary, snapshot_available: true, score_lower: 57.5, score_upper: 84.2, match_estimate: 70.9, confidence: "medium", ranking_score: 72.9,
    availability: { status: "not_serving", last_working_day: null, notice_days: 60, days_to_join: 60, bonus: 2 } };
  assert.equal(decodeCandidatePool({ job, candidates: [range] }, job.id).candidates[0].ranking_score, 72.9);
  for (const changed of [{ ...range, match_estimate: 60 }, { ...range, confidence: "very_high" }, { ...range, ranking_score: 70.9 }, { ...range, confidence: undefined }]) {
    assert.throws(() => decodeCandidatePool({ job, candidates: [changed] }, job.id), CatalogError);
  }
});
