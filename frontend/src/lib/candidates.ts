import { isAvailability, isRankingScore, type Availability } from "./availability.ts";
import { isEstimate, type Confidence } from "./estimate.ts";
import { CatalogError, decodeJob, isJobId, isJobSummary, type JobDetail } from "./catalog.ts";

export const isCandidateId = isJobId;

export interface CandidateSummary {
  id: string;
  display_name: string;
  headline: string;
  summary: string;
  is_demo: true;
}

export interface CandidateTableSummary extends CandidateSummary {
  stated_experience: string | null;
  snapshot_available: boolean;
  match_score: number | null;
  score_lower: number | null;
  score_upper: number | null;
  match_estimate: number | null;
  confidence: Confidence | null;
  availability: Availability;
  ranking_score: number | null;
}

export interface EvidenceClaim {
  kind: "skill" | "experience" | "qualification";
  label: string;
  quote: string;
  start: number;
  end: number;
}

export interface CandidateDetail extends CandidateSummary {
  resume_text: string;
  claims: EvidenceClaim[];
  offset_unit: "unicode_code_point";
}

export interface CandidatePool {
  job: JobDetail;
  candidates: CandidateTableSummary[];
}

export interface CandidateProfile {
  job: JobDetail;
  candidate: CandidateDetail;
  availability: Availability;
  assessment: unknown;
}

const object = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const text = (value: unknown): value is string =>
  typeof value === "string" && value.trim().length > 0;

function isCandidateSummary(value: unknown): value is CandidateSummary {
  return object(value) && isCandidateId(value.id) && text(value.display_name) &&
    text(value.headline) && text(value.summary) && value.is_demo === true;
}

function isCandidateTableSummary(value: unknown): value is CandidateTableSummary {
  if (!isCandidateSummary(value) || !object(value)) return false;
  const lower = value.score_lower;
  const upper = value.score_upper;
  const score = value.match_score;
  return (value.stated_experience === null || text(value.stated_experience)) &&
    typeof value.snapshot_available === "boolean" &&
    [score, lower, upper].every((number) => number === null ||
      (typeof number === "number" && Number.isFinite(number) && number >= 0 && number <= 100)) &&
    (lower === null ? upper === null && score === null :
      typeof lower === "number" && typeof upper === "number" && lower <= upper &&
      (score === null || score === lower)) &&
    (value.snapshot_available || (score === null && lower === null && upper === null)) &&
    isEstimate(value.match_estimate, value.confidence, lower, upper) &&
    isAvailability(value.availability) &&
    isRankingScore(value.ranking_score, typeof value.match_estimate === "number" ? value.match_estimate : null, value.availability);
}

function isClaim(value: unknown): value is EvidenceClaim {
  return object(value) && ["skill", "experience", "qualification"].includes(String(value.kind)) &&
    text(value.label) && text(value.quote) && Number.isSafeInteger(value.start) &&
    Number(value.start) >= 0 && Number.isSafeInteger(value.end) && Number(value.end) > Number(value.start);
}

/** Python offsets count Unicode code points, rather than JavaScript UTF-16 units. */
export function splitResume(source: string, start: number, end: number) {
  const characters = Array.from(source);
  return {
    before: characters.slice(0, start).join(""),
    excerpt: characters.slice(start, end).join(""),
    after: characters.slice(end).join(""),
  };
}

export function decodeCandidatePool(value: unknown, jobId: string): CandidatePool {
  if (!object(value) || !isJobSummary(value.job) || value.job.id !== jobId ||
      !Array.isArray(value.candidates) || !value.candidates.every(isCandidateTableSummary) ||
      new Set(value.candidates.map((row) => row.id)).size !== value.candidates.length) {
    throw new CatalogError("unavailable");
  }
  return { job: decodeJob(value.job), candidates: value.candidates };
}

export function decodeCandidateProfile(value: unknown, jobId: string, candidateId: string): CandidateProfile {
  if (!object(value) || !isJobSummary(value.job) || value.job.id !== jobId ||
      !object(value.candidate)) {
    throw new CatalogError("unavailable");
  }
  const candidate = value.candidate;
  const source = candidate.resume_text;
  const claims = candidate.claims;
  if (!isCandidateSummary(candidate) || candidate.id !== candidateId || !text(source) ||
      candidate.offset_unit !== "unicode_code_point" || !Array.isArray(claims) || !claims.every(isClaim)) {
    throw new CatalogError("unavailable");
  }
  if (![candidate.display_name, candidate.headline, candidate.summary].every((value) => source.includes(value)) ||
      claims.some((claim) => claim.end > Array.from(source).length ||
        splitResume(source, claim.start, claim.end).excerpt !== claim.quote)) {
    throw new CatalogError("unavailable");
  }
  if (!("assessment" in value) || !isAvailability(value.availability)) throw new CatalogError("unavailable");
  return { job: decodeJob(value.job), candidate: { ...candidate, resume_text: source, claims, offset_unit: "unicode_code_point" }, availability: value.availability, assessment: value.assessment };
}
