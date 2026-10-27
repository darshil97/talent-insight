/** Match estimate (range midpoint, unknowns at half credit) and how much of it is unknown. */
export type Confidence = "very_high" | "high" | "medium" | "low";

export const confidenceLabels: Record<Confidence, string> = { very_high: "Very high", high: "High", medium: "Medium", low: "Low" };

/** Very high confidence means nothing is unknown, so the range collapses to the estimate. */
export function isEstimate(estimate: unknown, confidence: unknown, lower: unknown, upper: unknown): boolean {
  if (lower === null || upper === null) return estimate === null && confidence === null;
  if (typeof lower !== "number" || typeof upper !== "number" || typeof estimate !== "number" || !Number.isFinite(estimate) || estimate < 0 || estimate > 100) return false;
  if (!["very_high", "high", "medium", "low"].includes(String(confidence))) return false;
  return Math.abs(estimate - (lower + upper) / 2) <= 0.051 && (confidence === "very_high") === (lower === upper);
}
