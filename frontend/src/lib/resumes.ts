/** Temporary PDF data only; no persistence or interpretation. */
import { apiBaseUrl } from "./catalog.ts";

export interface ResumeLimits {
  max_bytes: number;
  max_pages: number;
  max_characters: number;
  /** Public Cloudflare Turnstile key when an upload must pass a bot check before assessment. */
  bot_check_site_key?: string | null;
}

export interface ExtractedResume {
  source: "uploaded_pdf";
  page_count: number;
  character_count: number;
  pages: { page_number: number; text: string }[];
}

const messages: Record<string, string> = {
  unsupported_media_type: "Choose a PDF file.",
  invalid_pdf_signature: "The file content is not a PDF. Export a PDF and try again.",
  empty_upload: "This file is empty. Choose a text-based PDF.",
  payload_too_large: "This PDF exceeds the upload size limit. Choose a smaller file.",
  encrypted_pdf: "Password-protected PDFs are not supported. Choose an unencrypted PDF.",
  invalid_pdf: "This PDF is malformed or unsupported. Export a new PDF and try again.",
  empty_pdf: "This PDF has no pages. Choose a PDF containing resume text.",
  no_extractable_text: "This PDF is blank or scanned and has no extractable text. Choose a text-based PDF; OCR is not available.",
  too_many_pages: "This PDF exceeds the page limit. Choose a shorter resume.",
  too_much_text: "This PDF exceeds the extracted-text limit. Choose a shorter resume.",
  pdf_complexity_limit: "This PDF is too complex to process. Export a simpler text-based PDF.",
  extraction_timeout: "PDF processing took too long. Export a simpler PDF and try again.",
  upload_timeout: "The upload took too long. Try again.",
  resume_busy: "PDF processing is busy. Try again shortly.",
};

export class ResumeError extends Error {
  constructor(code = "unavailable") {
    super(messages[code] ?? "The PDF could not be processed. Check the connection and try again.");
  }
}

const object = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const integer = (v: unknown, min: number, max: number): v is number => Number.isInteger(v) && Number(v) >= min && Number(v) <= max;

export function decodeResumeLimits(value: unknown): ResumeLimits {
  if (!object(value) || !integer(value.max_bytes, 1024, 10 * 1024 * 1024) ||
      !integer(value.max_pages, 1, 50) || !integer(value.max_characters, 100, 200_000)) throw new ResumeError();
  const siteKey = value.bot_check_site_key ?? null;
  if (siteKey !== null && !(typeof siteKey === "string" && /^[A-Za-z0-9_-]{1,64}$/.test(siteKey))) throw new ResumeError();
  return { max_bytes: value.max_bytes, max_pages: value.max_pages, max_characters: value.max_characters, bot_check_site_key: siteKey };
}

export function decodeResume(value: unknown, limits: ResumeLimits): ExtractedResume {
  if (!object(value) || value.source !== "uploaded_pdf" || !integer(value.page_count, 1, limits.max_pages) ||
      !integer(value.character_count, 1, limits.max_characters) || !Array.isArray(value.pages) || value.pages.length !== value.page_count) throw new ResumeError();
  const pages = value.pages.map((page: unknown, index: number) => {
    if (!object(page) || page.page_number !== index + 1 || typeof page.text !== "string" || page.text.length > limits.max_characters * 2) throw new ResumeError();
    return { page_number: index + 1, text: page.text };
  });
  if (!pages.some((page) => page.text.trim()) || pages.reduce((total, page) => total + Array.from(page.text).length, 0) !== value.character_count) throw new ResumeError();
  return { source: "uploaded_pdf", page_count: value.page_count, character_count: value.character_count, pages };
}

export function validateResumeFile(file: File, limits: ResumeLimits): void {
  if (file.size === 0) throw new ResumeError("empty_upload");
  if (file.size > limits.max_bytes) throw new ResumeError("payload_too_large");
  // Browsers may provide no MIME type; server-side signature and parser checks remain authoritative.
  if (!/\.pdf$/i.test(file.name) || (file.type !== "" && file.type !== "application/pdf")) throw new ResumeError("unsupported_media_type");
}

export async function uploadResume(file: File, limits: ResumeLimits, signal: AbortSignal): Promise<ExtractedResume> {
  validateResumeFile(file, limits);
  const response = await fetch(`${apiBaseUrl()}/resumes/extract`, {
    method: "POST", headers: { "Content-Type": "application/pdf" }, body: file,
    cache: "no-store", credentials: "omit", redirect: "error",
    signal: AbortSignal.any([signal, AbortSignal.timeout(95_000)]),
  });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    throw new ResumeError(object(body) && object(body.error) && typeof body.error.code === "string" ? body.error.code : undefined);
  }
  return decodeResume(await response.json(), limits);
}
