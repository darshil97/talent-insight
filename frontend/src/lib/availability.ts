/** Self-reported availability: a small ranking aid computed by the backend, never part of the match score. */
import { apiBaseUrl } from "./catalog.ts";

export type NoticeStatus = "immediate" | "serving_notice" | "not_serving";
export interface AvailabilityInput { status: NoticeStatus | null; last_working_day: string | null; notice_days: number | null }
export interface Availability extends AvailabilityInput { days_to_join: number | null; bonus: number }
export interface RankedAvailability { availability: Availability; ranking_score: number | null }

export const notProvided: AvailabilityInput = { status: null, last_working_day: null, notice_days: null };

export class AvailabilityError extends Error {
  constructor() { super("Availability could not be calculated. The match score is shown without a bonus."); }
}

const object = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const integer = (value: unknown, min: number, max: number): value is number => Number.isSafeInteger(value) && Number(value) >= min && Number(value) <= max;
const isoDate = (value: unknown): value is string => typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(`${value}T00:00:00Z`));

export function isAvailability(value: unknown): value is Availability {
  if (!object(value)) return false;
  const { status, last_working_day: day, notice_days: notice, days_to_join: days, bonus } = value;
  const fields = status === null || status === "immediate" ? day === null && notice === null
    : status === "serving_notice" ? isoDate(day) && notice === null
    : status === "not_serving" ? day === null && integer(notice, 0, 365) : false;
  if (!fields || !integer(bonus, 0, 10)) return false;
  if (status === null) return days === null && bonus === 0;
  if (status === "immediate") return days === 0;
  if (status === "not_serving") return days === notice;
  return integer(days, 0, 36_500);
}

/** A ranking score exists only with a match estimate and always equals it plus the bonus. */
export function isRankingScore(value: unknown, matchEstimate: number | null, availability: Availability): value is number | null {
  if (matchEstimate === null) return value === null;
  return typeof value === "number" && Math.abs(value - Math.round((matchEstimate + availability.bonus) * 10) / 10) < 1e-9;
}

export function availabilityLabel(value: Availability | null): string {
  if (value === null || value.status === null) return "Not provided · no penalty";
  const bonus = value.bonus > 0 ? ` · +${value.bonus}` : "";
  if (value.status === "immediate") return `Available now${bonus}`;
  if (value.status === "serving_notice") return value.days_to_join === 0 ? `Notice period ended${bonus}` : `Joins in ~${value.days_to_join} days${bonus}`;
  return `${value.notice_days}-day notice${bonus}`;
}

export async function requestAvailability(input: AvailabilityInput, matchEstimate: number | null, signal: AbortSignal): Promise<RankedAvailability> {
  try {
    const response = await fetch(`${apiBaseUrl()}/availability`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ availability: input, match_estimate: matchEstimate }),
      cache: "no-store", credentials: "omit", redirect: "error",
      signal: AbortSignal.any([signal, AbortSignal.timeout(20_000)]),
    });
    const body: unknown = response.ok ? await response.json() : null;
    if (!object(body) || !isAvailability(body.availability) || !isRankingScore(body.ranking_score, matchEstimate, body.availability)) throw new AvailabilityError();
    return { availability: body.availability, ranking_score: body.ranking_score };
  } catch (failure) {
    if (signal.aborted) throw failure;
    throw new AvailabilityError();
  }
}
