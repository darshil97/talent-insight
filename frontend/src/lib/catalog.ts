/** Public FastAPI contracts and validation at the browser's network boundary. */
export interface JobSummary {
  id: string;
  title: string;
  client: string;
  description: string;
  skills: string[];
  is_demo: true;
}

export interface JobListItem extends JobSummary {
  candidate_count: number;
}

export type RequirementCategory = "mandatory" | "experience" | "preferred" | "qualification";

export interface JobRequirement {
  id: string;
  category: RequirementCategory;
  description: string;
  minimum_years: number | null;
  sort_order: number;
}

export interface JobDetail extends JobSummary {
  requirements: JobRequirement[];
  screening_criteria: string[];
  questions: { id: string; text: string; requirement_ids: string[] }[];
}

export class CatalogError extends Error {
  kind: "not_found" | "unavailable";

  constructor(kind: "not_found" | "unavailable") {
    super(kind === "not_found" ? "Job not found." : "The job catalog is unavailable.");
    this.kind = kind;
  }
}

export function isJobId(value: unknown): value is string {
  return typeof value === "string" && value.length <= 64 && /^demo_[a-z0-9_]+$/.test(value);
}

const object = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const text = (value: unknown): value is string =>
  typeof value === "string" && value.trim().length > 0;
const texts = (value: unknown): value is string[] => Array.isArray(value) && value.every(text);
const uniqueIds = (rows: { id: string }[]) => new Set(rows.map((row) => row.id)).size === rows.length;

export function isJobSummary(value: unknown): value is JobSummary {
  return object(value) && isJobId(value.id) && text(value.title) && text(value.client) &&
    text(value.description) && texts(value.skills) && value.is_demo === true;
}

export function decodeJobs(value: unknown): JobListItem[] {
  if (!object(value) || !Array.isArray(value.jobs) || !value.jobs.every((row): row is JobListItem => isJobSummary(row) && object(row) &&
      Number.isSafeInteger(row.candidate_count) && Number(row.candidate_count) >= 0) || !uniqueIds(value.jobs)) {
    throw new CatalogError("unavailable");
  }
  return value.jobs;
}

function isRequirement(value: unknown): value is JobRequirement {
  return object(value) && isJobId(value.id) && text(value.description) &&
    ["mandatory", "experience", "preferred", "qualification"].includes(String(value.category)) &&
    Number.isInteger(value.sort_order) && Number(value.sort_order) >= 0 &&
    (value.minimum_years === null || (value.category === "experience" &&
      typeof value.minimum_years === "number" && Number.isFinite(value.minimum_years) && value.minimum_years >= 0));
}

export function decodeJob(value: unknown): JobDetail {
  if (!isJobSummary(value) || !object(value) || !texts(value.screening_criteria) ||
      !Array.isArray(value.requirements) || !value.requirements.every(isRequirement) ||
      !uniqueIds(value.requirements) || !Array.isArray(value.questions)) {
    throw new CatalogError("unavailable");
  }
  const ids = new Set(value.requirements.map((row) => row.id));
  const questions = value.questions;
  if (!questions.every((row): row is JobDetail["questions"][number] =>
    object(row) && isJobId(row.id) && text(row.text) && texts(row.requirement_ids) &&
    row.requirement_ids.length > 0 && row.requirement_ids.every((id) => ids.has(id))) || !uniqueIds(questions)) {
    throw new CatalogError("unavailable");
  }
  return { ...value, requirements: [...value.requirements].sort((a, b) => a.sort_order - b.sort_order),
    screening_criteria: value.screening_criteria, questions };
}

export function apiBaseUrl(raw = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"): string {
  try {
    const url = new URL(raw);
    const loopback = url.hostname === "localhost" || url.hostname === "[::1]" || /^127\.\d+\.\d+\.\d+$/.test(url.hostname);
    if (raw !== raw.trim() || url.username || url.password || url.pathname !== "/" || url.search || url.hash ||
        !(url.protocol === "https:" || (url.protocol === "http:" && loopback))) {
      throw new Error();
    }
    return url.origin;
  } catch {
    throw new CatalogError("unavailable");
  }
}

export async function fetchCatalog<T>(path: string, decode: (value: unknown) => T, signal: AbortSignal): Promise<T> {
  const response = await fetch(`${apiBaseUrl()}${path}`, {
    method: "GET", cache: "no-store", credentials: "omit", redirect: "error",
    signal: AbortSignal.any([signal, AbortSignal.timeout(20_000)]),
  });
  if (!response.ok) throw new CatalogError(response.status === 404 ? "not_found" : "unavailable");
  return decode(await response.json());
}
