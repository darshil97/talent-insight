/** Screening sessions: consent, session control and text turns. The backend owns context, limits and the interviewer. */
import { apiBaseUrl } from "./catalog.ts";

export type ScreeningMode = "voice" | "text";
export type ScreeningCandidate = { kind: "demo"; candidate_id: string } | { kind: "upload"; context: string };
export interface ScreeningNotice { notice_version: string; text: string; screening_minutes: number; voice_available: boolean; text_available: boolean }
export interface ScreeningStart {
  session_id: string; capability: string; mode: ScreeningMode; expires_at: string; greeting: string;
  screening_seconds: number; max_turns: number;
  agent_url: string | null; deepgram_token: string | null; token_expires_in: number | null; settings: Record<string, unknown> | null;
}
export interface ScreeningSession { session_id: string; capability: string }
export interface TokenGrant { deepgram_token: string; token_expires_in: number }
export interface MessageReply { reply: string; ended: boolean }

export type TopicStatus = "supported" | "partly_supported" | "not_shown" | "declined" | "not_covered";
export type Correctness = "correct" | "correct_after_hint" | "comparable" | "partly_correct" | "incorrect" | "not_applicable";
export type ReportDimensionName = "relevance" | "specificity" | "ownership" | "explanation";
export type NextStep = "interview" | "gather_information" | "human_review";
export type EndReason = "interviewer" | "time_limit" | "failure" | "ended_early";
export type ResumeStatus = "met" | "transferable" | "partial" | "not_met" | "unknown";
export interface ReportTopic {
  requirement_id: string; category: "mandatory" | "experience" | "preferred" | "qualification"; description: string;
  resume_status: ResumeStatus; status: TopicStatus; correctness: Correctness; prompted: boolean; quotes: string[]; note: string; needs_check: boolean;
}
export type FlagKind = "instruction_override" | "score_request" | "answer_request" | "prompt_probe";
/** A candidate attempt to steer the AI: recorded for a human, never obeyed. */
export interface IntegrityFlag { kind: FlagKind; quote: string; note: string; detected_by: "rules" | "ai" | "both" }
export interface ReportDimension { name: ReportDimensionName; level: number; score: number | null; quotes: string[]; reason: string }
/** A temporary, server-scored screening report; candidate statements are unverified claims. */
export interface ScreeningReport {
  job_id: string; job_title: string; candidate_kind: "demo" | "upload"; evaluated_by: "model" | "mock" | "none";
  complete: boolean; end_reason: EndReason; candidate_answers: number;
  overall_score: number | null; correctness_score: number | null;
  dimensions: ReportDimension[]; topics: ReportTopic[]; unresolved: string[]; follow_ups: string[]; summary: string; next_step: NextStep;
  next_step_reasons: string[]; integrity_flags: IntegrityFlag[];
}

const messages: Record<string, string> = {
  voice_not_configured: "Voice screening is turned off on the backend. Use the text option instead.",
  interviewer_not_configured: "Screening is not enabled on the backend. Configure the interviewer and try again.",
  voice_configuration_error: "Screening needs backend configuration before it can start.",
  consent_required: "Consent under the current notice is required before the screening starts.",
  invalid_screening_context: "This assessment has expired for screening. Upload and assess the resume again.",
  screening_not_found: "This screening has expired or was not found. Start a new screening.",
  screening_ended: "This screening has already ended.",
  reconnect_limit_reached: "The call could not reconnect again. Continue by text or start a new screening.",
  voice_busy: "Another screening is in progress. Try again shortly.",
  voice_rate_limited: "The screening limit was reached. Try again later.",
  turn_in_progress: "The interviewer is still answering. Wait a moment and send again.",
  voice_provider_access_denied: "The voice provider rejected the backend key. Use the text option or check the backend.",
  voice_provider_throttled: "The voice provider is busy. Try again shortly or use the text option.",
  voice_provider_timeout: "The voice provider did not respond in time. Try again or use the text option.",
  voice_provider_unavailable: "The voice provider is unavailable. Use the text option or try later.",
  validation_error: "The screening request was invalid. Reload the page and try again.",
  screening_active: "The screening is still running. End it before preparing the report.",
  report_too_large: "This conversation is too long for a report.",
  report_timeout: "Preparing the report took too long. Try again.",
  report_unavailable: "The report could not be prepared. Try again.",
};

export interface TranscriptTurn { role: "candidate" | "interviewer"; text: string }

/**
 * Adds a transcript line, joining it to the previous one from the same speaker. The voice agent
 * reports the interviewer sentence by sentence, and a candidate answer can arrive in parts.
 */
export function appendTurn(turns: TranscriptTurn[], turn: TranscriptTurn): TranscriptTurn[] {
  const last = turns.at(-1);
  if (last?.role !== turn.role) return [...turns, turn];
  return [...turns.slice(0, -1), { role: turn.role, text: `${last.text} ${turn.text}` }];
}

const voiceErrors: Record<string, string> = {
  microphone_denied: "Microphone access was blocked. Continue by text, or allow the microphone and start again.",
  microphone_unavailable: "No usable microphone was found. Continue by text.",
  connection_failed: "The voice service refused the connection. Continue by text.",
  connection_lost: "The call disconnected and could not reconnect. Continue by text.",
};

/**
 * The message for a voice call that stopped. Provider codes are shown so a failure can be traced;
 * the voice client only passes short identifiers, never provider text.
 */
export function voiceErrorMessage(code?: string): string {
  if (code && voiceErrors[code]) return voiceErrors[code];
  const shown = code && /^[A-Za-z0-9_.-]{1,64}$/.test(code) ? ` (code: ${code})` : "";
  return `The voice service reported a problem${shown}. Continue by text.`;
}

export class ScreeningError extends Error {
  readonly code: string;
  constructor(code = "unavailable") {
    super(messages[code] ?? "Screening is unavailable. Check the connection and try again.");
    this.code = code;
  }
}

const object = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const text = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;
const integer = (value: unknown, min: number, max: number): value is number => Number.isSafeInteger(value) && Number(value) >= min && Number(value) <= max;
const opaque = (value: unknown, min: number): value is string => typeof value === "string" && value.length >= min && value.length <= 64 && /^[A-Za-z0-9_-]+$/.test(value);
const agentUrl = (value: unknown): value is string => typeof value === "string" && /^wss:\/\/[a-z0-9.-]+\.deepgram\.com\/v1\/agent\/converse$/.test(value);
const fail = (): never => { throw new ScreeningError(); };

export function decodeNotice(value: unknown): ScreeningNotice {
  if (!object(value) || !text(value.notice_version) || !text(value.text) || !integer(value.screening_minutes, 1, 30) ||
      typeof value.voice_available !== "boolean" || typeof value.text_available !== "boolean") return fail();
  return value as unknown as ScreeningNotice;
}

export function decodeStart(value: unknown, mode: ScreeningMode): ScreeningStart {
  if (!object(value) || !opaque(value.session_id, 22) || !opaque(value.capability, 43) || value.mode !== mode ||
      typeof value.expires_at !== "string" || Number.isNaN(Date.parse(value.expires_at)) || !text(value.greeting) ||
      !integer(value.screening_seconds, 60, 1800) || !integer(value.max_turns, 1, 100)) return fail();
  const voiceFields = mode === "voice"
    ? agentUrl(value.agent_url) && text(value.deepgram_token) && integer(value.token_expires_in, 1, 3600) && object(value.settings) && value.settings.type === "Settings"
    : value.agent_url === null && value.deepgram_token === null && value.token_expires_in === null && value.settings === null;
  if (!voiceFields) return fail();
  return value as unknown as ScreeningStart;
}

export function decodeToken(value: unknown): TokenGrant {
  if (!object(value) || !text(value.deepgram_token) || !integer(value.token_expires_in, 1, 3600)) return fail();
  return value as unknown as TokenGrant;
}

const oneOf = <T extends string>(value: unknown, options: readonly T[]): value is T => typeof value === "string" && (options as readonly string[]).includes(value);
const strings = (value: unknown, max: number, length: number): value is string[] =>
  Array.isArray(value) && value.length <= max && value.every((item) => typeof item === "string" && item.length <= length);
const percent = (value: unknown): value is number | null => value === null || (typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100);
const TOPIC_STATUSES = ["supported", "partly_supported", "not_shown", "declined", "not_covered"] as const;
const CORRECTNESS = ["correct", "correct_after_hint", "comparable", "partly_correct", "incorrect", "not_applicable"] as const;
const DIMENSIONS = ["relevance", "specificity", "ownership", "explanation"] as const;

function reportTopic(value: unknown): boolean {
  return object(value) && text(value.requirement_id) && oneOf(value.category, ["mandatory", "experience", "preferred", "qualification"]) &&
    text(value.description) && oneOf(value.resume_status, ["met", "transferable", "partial", "not_met", "unknown"]) && oneOf(value.status, TOPIC_STATUSES) && oneOf(value.correctness, CORRECTNESS) &&
    typeof value.prompted === "boolean" && strings(value.quotes, 3, 300) && typeof value.note === "string" && value.note.length <= 200 &&
    typeof value.needs_check === "boolean" &&
    // Unassessed topics carry no quotes, and only assessed answers can be right or wrong.
    (value.status === "not_covered") === (value.quotes.length === 0) &&
    (value.status !== "not_covered" && value.status !== "declined" || value.correctness === "not_applicable");
}

function reportDimension(value: unknown, name: string): boolean {
  return object(value) && value.name === name && integer(value.level, 0, 4) && percent(value.score) &&
    (value.level === 0) === (value.score === null) && strings(value.quotes, 3, 300) && typeof value.reason === "string" && value.reason.length <= 200;
}

function integrityFlag(value: unknown): boolean {
  return object(value) && oneOf(value.kind, ["instruction_override", "score_request", "answer_request", "prompt_probe"]) &&
    text(value.quote) && value.quote.length <= 300 && typeof value.note === "string" && value.note.length <= 200 &&
    oneOf(value.detected_by, ["rules", "ai", "both"]);
}

/** Shape and consistency checks only; the backend calculates every score and the next step. */
export function decodeReport(value: unknown, jobId: string): ScreeningReport {
  if (!object(value) || value.job_id !== jobId || !text(value.job_title) || !oneOf(value.candidate_kind, ["demo", "upload"]) ||
      !oneOf(value.evaluated_by, ["model", "mock", "none"]) || typeof value.complete !== "boolean" ||
      !oneOf(value.end_reason, ["interviewer", "time_limit", "failure", "ended_early"]) || !integer(value.candidate_answers, 0, 1000) ||
      !percent(value.overall_score) || !percent(value.correctness_score) ||
      !Array.isArray(value.dimensions) || value.dimensions.length !== DIMENSIONS.length || !value.dimensions.every((item, index) => reportDimension(item, DIMENSIONS[index])) ||
      !Array.isArray(value.topics) || !value.topics.every(reportTopic) ||
      !strings(value.unresolved, 100, 1000) || !strings(value.follow_ups, 5, 200) || typeof value.summary !== "string" || value.summary.length > 600 ||
      !oneOf(value.next_step, ["interview", "gather_information", "human_review"]) ||
      !strings(value.next_step_reasons, 6, 600) || value.next_step_reasons.length === 0 ||
      !Array.isArray(value.integrity_flags) || value.integrity_flags.length > 10 || !value.integrity_flags.every(integrityFlag) ||
      // A flagged screening always goes to a human.
      (value.integrity_flags.length > 0 && value.next_step !== "human_review")) return fail();
  return value as unknown as ScreeningReport;
}

export function decodeReply(value: unknown): MessageReply {
  if (!object(value) || typeof value.reply !== "string" || typeof value.ended !== "boolean") return fail();
  return value as unknown as MessageReply;
}

async function request<T>(path: string, init: { method: "GET" | "POST"; body?: unknown }, decode: (value: unknown) => T, signal: AbortSignal, timeout: number): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, {
      method: init.method,
      ...(init.body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(init.body) }),
      cache: "no-store", credentials: "omit", redirect: "error",
      signal: AbortSignal.any([signal, AbortSignal.timeout(timeout)]),
    });
  } catch (failure) {
    if (signal.aborted) throw failure;
    throw new ScreeningError();
  }
  if (!response.ok) {
    // Only the error code is used; server text is never displayed.
    const body: unknown = await response.json().catch(() => null);
    throw new ScreeningError(object(body) && object(body.error) && typeof body.error.code === "string" ? body.error.code : undefined);
  }
  return decode(await response.json().catch(() => null));
}

const sessionPath = (session: ScreeningSession, suffix: string) => `/screenings/${encodeURIComponent(session.session_id)}/${suffix}`;

export function getNotice(signal: AbortSignal): Promise<ScreeningNotice> {
  return request("/screenings/notice", { method: "GET" }, decodeNotice, signal, 20_000);
}

export function startScreening(jobId: string, candidate: ScreeningCandidate, mode: ScreeningMode, notice: ScreeningNotice, signal: AbortSignal): Promise<ScreeningStart> {
  const consent = { audio_capture: mode === "voice", ai_processing: true, notice_version: notice.notice_version };
  return request("/screenings", { method: "POST", body: { job_id: jobId, candidate, consent, mode } }, (value) => decodeStart(value, mode), signal, 30_000);
}

export function reconnectToken(session: ScreeningSession, signal: AbortSignal): Promise<TokenGrant> {
  return request(sessionPath(session, "token"), { method: "POST", body: { capability: session.capability } }, decodeToken, signal, 20_000);
}

/** One interviewer turn can take the backend's turn deadline plus network time. */
export function sendMessage(session: ScreeningSession, message: string, signal: AbortSignal): Promise<MessageReply> {
  return request(sessionPath(session, "messages"), { method: "POST", body: { capability: session.capability, text: message } }, decodeReply, signal, 60_000);
}

/**
 * Ends the screening (idempotent) and returns its report. The backend builds it once, within its
 * own model deadline, and keeps it only in memory until the session expires.
 */
export async function requestReport(session: ScreeningSession, jobId: string, signal: AbortSignal): Promise<ScreeningReport> {
  const body = { capability: session.capability };
  await request(sessionPath(session, "end"), { method: "POST", body }, (value) => value, signal, 20_000);
  return request(sessionPath(session, "report"), { method: "POST", body }, (value) => decodeReport(value, jobId), signal, 150_000);
}

/** Best effort and survives page unload; the session also expires on its own. */
export function endScreening(session: ScreeningSession): void {
  try {
    void fetch(`${apiBaseUrl()}${sessionPath(session, "end")}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ capability: session.capability }),
      cache: "no-store", credentials: "omit", redirect: "error", keepalive: true,
    }).catch(() => undefined);
  } catch {
    // An invalid API origin already surfaced when the screening started.
  }
}
