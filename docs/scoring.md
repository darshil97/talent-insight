# Interpretation and scoring

This page covers how verified facts become requirement judgments, how the backend scores them, and how availability affects ranking. A score summarizes resume evidence against one job. It is not a performance prediction or a hiring decision.

## Assess route

`POST /jobs/{job_id}/resumes/assess` takes a raw PDF and runs [extraction](structured-extraction.md), interpretation and scoring. It stores nothing and is `no-store`. It returns `structured`, `judgments` (in job order), `scoring`, `notice` and `screening_context` (signed for a [screening](voice-sessions.md), or `null` when not configured).

Callers cannot submit facts, judgments or scores. Demo candidates get the same shape from the [snapshot](candidates.md#demo-assessment-snapshot).

## Judgments

Each judgment is `{requirement_id, status, fact_indices, reason}`:

- **Citations:** a resolved status cites 1–10 indices into `structured.facts`; `unknown` cites none.
- **Reason:** up to 300 characters of model interpretation, not a quote.

| Status | Meaning (from the prompt) |
| --- | --- |
| `met` | Applied use in a role or project clearly satisfies it. Same-field evidence satisfies "or equivalent". |
| `transferable` | Applied use of a comparable tool, platform or method, or closely adjacent work (for example GCP for AWS). The reason names the substitution. Credentials and legal requirements are never transferable. |
| `partial` | Narrower scope, below a year threshold, weaker evidence, or only listed. |
| `not_met` | Explicit contrary evidence only. |
| `unknown` | Everything else. Missing evidence is unknown, not a missing skill. |

- **Experience thresholds:** only relevant documented work counts against `minimum_years`. The model is told not to invent years or add overlapping periods.
- **Mock mode:** every requirement is `unknown`.
- **New evidence:** the judging step may add `new_evidence`, resume quotes that no fact covers. Each one is verified like an extracted fact before it is appended to `structured.facts` and cited. Anything else is discarded.

**Normalization** (`salvage_judgments`):

- Judgments for unknown requirement IDs and extra fields are ignored; bad or duplicate citations are dropped; long reasons are shortened.
- **Forced to `unknown`:**
  - missing judgments;
  - conflicting judgments;
  - resolved judgments left without a valid citation;
  - `not_met` judgments whose quotes only say information is "not stated / described / provided / specified / documented / mentioned / listed".
- **Retry:** if over half the requirements were forced to `unknown`, the stage [retries](structured-extraction.md#attempts-limits-and-admission).
- **Strict check:** exactly one judgment per requirement, valid references, and every quote re-verified. Failure returns 502 `invalid_interpretation`.

Normalization only moves toward `unknown`. Provider failures stop the assessment and never become a score of 0 or 100.

## Score

- **Credits:** `met` 1, `transferable` 0.75, `partial` 0.5, `not_met` 0; `unknown` stays unresolved.
- **Default category weights:** mandatory 50%, experience 25%, preferred 15%, qualification 10%.

Weights (integers summing to 100) and middle credits (0 < partial < transferable < 1) are configurable ([configuration](configuration.md)). The defaults are unvalidated.

- **Category credit:** the mean over all its requirements.
- **Absent categories:** their weight is shared proportionally among the present ones.
- **Range:** `lower` counts `unknown` as 0 and `upper` counts it as 1, on a 0–100 scale.
- **`score`:** equals `lower` only when nothing is unknown; otherwise `null`.
- **`estimate`:** the range midpoint, so each unknown counts at half credit. This is a placeholder, not evidence.
- **`confidence`:** from `upper − lower` (the weight still unknown): `very_high` at 0, `high` up to 15, `medium` up to 35, else `low` (constants in `app/pipeline/scoring.py`).
- **No score:** with no requirements or zero present weight, every score field is `null`.
- **Rounding:** exact decimals, rounded half-up to one place.
- **Also reported:** resolved and unknown counts, `mandatory_met` (only `met`), `mandatory_total`, and per-category counts, effective weights and bounds.

**Example:** with three mandatory requirements and one each of experience, preferred and qualification, all `met` except an `unknown` experience requirement, the result is a range of 75–100, an estimate of 87.5, `medium` confidence and no point score. A mock upload has every requirement unknown, giving a range of 0–100, an estimate of 50 and `low` confidence.

## Availability and ranking

Availability never changes the score, range, estimate or snapshot.

- **Input:** `status` is `immediate`, `serving_notice` (with `last_working_day`), `not_serving` (with `notice_days`, 0–365) or `null`. The fields must match the status.
- **`days_to_join`:** 0 for `immediate`; days until the last working day (never below 0); the notice days; or `null`.
- **Bonus:** ≤15 days +5, ≤30 +4, ≤45 +3, ≤60 +2, ≤90 +1, otherwise 0. Not provided gets 0, never a penalty. The tiers are configurable.
- **`ranking_score`:** `estimate + bonus`, rounded to one place; `null` without an estimate. The pool sorts by it.
- **Demo candidates:** computed on each read from stored availability, so no refresh is needed.
- **Uploads:** `POST /availability` with `{"availability": {...}, "match_estimate": number | null}` returns `{"availability": {..., "days_to_join", "bonus"}, "ranking_score"}`. It is stateless, unlogged and `no-store`, and returns 422 for mismatched fields.

## Limits

- Weights, credits, confidence bands and bonus tiers are unvalidated. Do not use them as an automatic filter.
- Status semantics cannot be fully machine-verified; a citation proves location only.
- The interpretation has had no formal accuracy evaluation. Ambiguous or negated wording needs human review.
- A low-confidence estimate near 50 mostly reflects missing information.
