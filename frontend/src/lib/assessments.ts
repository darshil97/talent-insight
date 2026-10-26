/** Temporary assessment contracts. The backend owns interpretation and scoring. */
import { apiBaseUrl, type JobDetail, type RequirementCategory } from "./catalog.ts";
import { splitResume } from "./candidates.ts";
import { ResumeError, validateResumeFile, type ResumeLimits } from "./resumes.ts";

type FactKind = "skill" | "experience" | "qualification" | "project";
export type JudgmentStatus = "met" | "partial" | "not_met" | "unknown";
export interface Citation { page_number: number; quote: string; start: number; end: number }
export interface Fact { kind: FactKind; value: string; evidence: Citation[] }
export interface Judgment { requirement_id: string; status: JudgmentStatus; fact_indices: number[]; reason: string }
export interface CategoryScore { category: RequirementCategory; requirement_count: number; resolved_count: number; unknown_count: number; effective_weight: number; lower: number; upper: number }
export interface Assessment {
  structured: {
    source: { kind: "uploaded_pdf" | "synthetic_demo"; candidate_id: string | null; pages: { page_number: number; text: string }[] };
    mode: "mock" | "bedrock"; model_id: string | null; facts: Fact[];
    unknown_categories: FactKind[]; offset_unit: "unicode_code_point"; notice: string;
  };
  judgments: Judgment[];
  scoring: { score: number | null; lower: number | null; upper: number | null; resolved_count: number; unknown_count: number; mandatory_met: number; mandatory_total: number; categories: CategoryScore[] };
  notice: string;
}

const messages: Record<string, string> = {
  ai_not_configured: "Assessment is not enabled on the backend. Configure AI_MODE and try again.",
  provider_configuration_error: "The assessment provider needs backend configuration.",
  provider_access_denied: "The assessment provider is unavailable. Check backend access.",
  unsupported_model_capability: "The configured model cannot handle this assessment request.",
  ai_unavailable: "Assessment is unavailable. Try again later.",
  provider_throttled: "The assessment provider is busy. Try again later.",
  provider_timeout: "The assessment provider timed out. Try again later.",
  ai_timeout: "Assessment took too long. Try a shorter resume later.",
  ai_busy: "Assessment is busy. Try again shortly.",
  ai_rate_limited: "The assessment request limit was reached. Try again in a minute.",
  ai_input_too_large: "The resume and job exceed the assessment text limit.",
  invalid_model_output: "The model response could not be validated. No assessment was produced.",
  invalid_evidence: "The model evidence could not be verified. No assessment was produced.",
  invalid_interpretation: "The requirement interpretation could not be verified. No assessment was produced.",
  candidate_not_found: "This synthetic candidate is not in the job pool.",
};

export class AssessmentError extends Error {
  constructor(code = "unavailable") { super(messages[code] ?? "Assessment could not be completed. Check the connection and try again."); }
}

const object = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const text = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;
const integer = (value: unknown, min: number, max: number): value is number => Number.isSafeInteger(value) && Number(value) >= min && Number(value) <= max;
const percent = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100;
const kinds: FactKind[] = ["skill", "experience", "qualification", "project"];
const categories: RequirementCategory[] = ["mandatory", "experience", "preferred", "qualification"];
const statuses: JudgmentStatus[] = ["met", "partial", "not_met", "unknown"];
const pdfErrors = new Set(["unsupported_media_type", "invalid_pdf_signature", "empty_upload", "payload_too_large", "encrypted_pdf", "invalid_pdf", "empty_pdf", "no_extractable_text", "too_many_pages", "too_much_text", "pdf_complexity_limit", "extraction_timeout", "upload_timeout", "resume_busy"]);
const fail = (): never => { throw new AssessmentError(); };

export function decodeAssessment(value: unknown, job: JobDetail, kind: "uploaded_pdf" | "synthetic_demo", candidateId: string | null = null): Assessment {
  if (!object(value) || !object(value.structured) || !object(value.scoring) || !Array.isArray(value.judgments) || !text(value.notice)) return fail();
  const structured = value.structured;
  const context = structured.job;
  const requirements = object(context) && Array.isArray(context.requirements) ? context.requirements : null;
  if (!object(context) || context.id !== job.id || context.title !== job.title ||
      JSON.stringify(context.skills) !== JSON.stringify(job.skills) || requirements === null ||
      requirements.length !== job.requirements.length ||
      job.requirements.some((req, index) => {
        const row = requirements[index];
        return !object(row) || row.id !== req.id || row.category !== req.category || row.description !== req.description || row.minimum_years !== req.minimum_years || row.sort_order !== req.sort_order;
      })) return fail();
  if (!object(structured.source) || structured.source.kind !== kind || structured.source.candidate_id !== candidateId ||
      !Array.isArray(structured.source.pages) || !integer(structured.source.pages.length, 1, 50) ||
      structured.source.pages.some((page: unknown, index: number) => !object(page) || page.page_number !== index + 1 || typeof page.text !== "string") ||
      !structured.source.pages.some((page: { text: string }) => page.text.trim()) ||
      structured.source.pages.reduce((total: number, page: { text: string }) => total + page.text.length, 0) > 200_000 ||
      !["mock", "bedrock"].includes(String(structured.mode)) ||
      (structured.mode === "mock" ? structured.model_id !== null : !text(structured.model_id)) ||
      structured.offset_unit !== "unicode_code_point" || !text(structured.notice) ||
      !Array.isArray(structured.facts) || structured.facts.length > 40 ||
      !Array.isArray(structured.unknown_categories) ||
      structured.unknown_categories.some((item: unknown) => !kinds.includes(item as FactKind)) ||
      new Set(structured.unknown_categories).size !== structured.unknown_categories.length) return fail();
  const pages = structured.source.pages as { page_number: number; text: string }[];
  const facts = structured.facts as unknown[];
  if (facts.some((fact: unknown) => {
    if (!object(fact) || !kinds.includes(fact.kind as FactKind) || !text(fact.value) || !Array.isArray(fact.evidence) || !integer(fact.evidence.length, 1, 3)) return true;
    return fact.evidence.some((citation: unknown) => {
      if (!object(citation) || !integer(citation.page_number, 1, pages.length) || !text(citation.quote) ||
          !integer(citation.start, 0, 200_000) || !integer(citation.end, citation.start + 1, 200_000)) return true;
      return splitResume(pages[citation.page_number - 1].text, citation.start, citation.end).excerpt !== citation.quote;
    });
  })) return fail();
  const ids = new Set(job.requirements.map((row) => row.id));
  if (value.judgments.length !== ids.size || value.judgments.some((row: unknown) => {
    if (!object(row) || !ids.has(row.requirement_id as string) || !statuses.includes(row.status as JudgmentStatus) ||
        !text(row.reason) || !Array.isArray(row.fact_indices) || row.fact_indices.length > 10 ||
        row.fact_indices.some((index: unknown) => !integer(index, 0, facts.length - 1)) ||
        new Set(row.fact_indices).size !== row.fact_indices.length) return true;
    return (row.status === "unknown") !== (row.fact_indices.length === 0);
  }) || new Set(value.judgments.map((row: Judgment) => row.requirement_id)).size !== ids.size) return fail();
  const scoring = value.scoring;
  const judgments = value.judgments as Judgment[];
  const unknown = judgments.filter((row) => row.status === "unknown").length;
  const mandatory = judgments.filter((row) => job.requirements.find((req) => req.id === row.requirement_id)?.category === "mandatory");
  if (!integer(scoring.resolved_count, 0, ids.size) || scoring.resolved_count !== ids.size - unknown ||
      scoring.unknown_count !== unknown || scoring.mandatory_total !== mandatory.length ||
      scoring.mandatory_met !== mandatory.filter((row) => row.status === "met").length ||
      !Array.isArray(scoring.categories) || scoring.categories.length !== new Set(job.requirements.map((row) => row.category)).size ||
      scoring.categories.some((row: unknown) => {
        if (!object(row) || !categories.includes(row.category as RequirementCategory)) return true;
        const members = judgments.filter((item) => job.requirements.find((req) => req.id === item.requirement_id)?.category === row.category);
        return members.length === 0 || row.requirement_count !== members.length || row.resolved_count !== members.filter((item) => item.status !== "unknown").length ||
          row.unknown_count !== members.filter((item) => item.status === "unknown").length ||
          !percent(row.effective_weight) || !percent(row.lower) || !percent(row.upper) || row.lower > row.upper;
      }) || new Set(scoring.categories.map((row: CategoryScore) => row.category)).size !== scoring.categories.length) return fail();
  const activeWeight = (scoring.categories as CategoryScore[]).reduce((sum, row) => sum + row.effective_weight, 0);
  if (ids.size === 0 || activeWeight === 0) {
    if (scoring.score !== null || scoring.lower !== null || scoring.upper !== null) return fail();
  } else if (!percent(scoring.lower) || !percent(scoring.upper) || scoring.lower > scoring.upper ||
             (unknown > 0 ? scoring.score !== null : !percent(scoring.score) || scoring.score !== scoring.lower)) return fail();
  return value as unknown as Assessment;
}

async function postAssessment(path: string, job: JobDetail, kind: "uploaded_pdf" | "synthetic_demo", candidateId: string | null, signal: AbortSignal, file?: File): Promise<Assessment> {
  const response = await fetch(`${apiBaseUrl()}${path}`, {
    method: "POST", ...(file ? { headers: { "Content-Type": "application/pdf" }, body: file } : {}),
    cache: "no-store", credentials: "omit", redirect: "error",
    signal: AbortSignal.any([signal, AbortSignal.timeout(360_000)]),
  });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    if (response.status === 404) throw new AssessmentError(kind === "synthetic_demo" ? "candidate_not_found" : "unavailable");
    const code = object(body) && object(body.error) && typeof body.error.code === "string" ? body.error.code : undefined;
    if (kind === "uploaded_pdf" && code && pdfErrors.has(code)) throw new ResumeError(code);
    throw new AssessmentError(code);
  }
  return decodeAssessment(await response.json(), job, kind, candidateId);
}

export function assessUpload(file: File, limits: ResumeLimits, job: JobDetail, signal: AbortSignal): Promise<Assessment> {
  validateResumeFile(file, limits);
  return postAssessment(`/jobs/${encodeURIComponent(job.id)}/resumes/assess`, job, "uploaded_pdf", null, signal, file);
}
