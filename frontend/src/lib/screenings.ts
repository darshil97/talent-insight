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
};

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
