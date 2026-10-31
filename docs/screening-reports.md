# Screening reports

After a screening ends, the backend reviews the candidate's own answers and returns a structured report for a recruiter. The model chooses statuses and levels and must quote the candidate; the server checks every quote and calculates every score and the suggested next step. A human makes every decision.

The report is temporary: it stays in the session's memory until the session expires (15 minutes after it was created) and in the browser panel until it is closed, refreshed or left ([data retention](data-retention.md)). Endpoints and sessions: [screening sessions](voice-sessions.md).

## Flow

1. The screening ends: the interviewer closes it, the time limit or turn cap is reached, two model failures stop it, or the candidate presses End.
2. The panel calls `POST /screenings/{id}/end`, then `POST /screenings/{id}/report` with `{capability}`, and shows "Preparing the screening report…".
3. The backend builds the report once per session. Repeat or simultaneous requests share the build and then its result; a disconnected browser does not cancel it, and a failed build can be retried.

Errors: 409 `screening_active` before the screening has ended; 413 `report_too_large` (input over 60,000 characters, refused rather than truncated); 504 `report_timeout`; 503 `report_unavailable`. The browser shows fixed messages only.

## Response

`ScreeningReport` in `app/voice/report.py`:

| Field | Meaning |
| --- | --- |
| `job_id`, `job_title`, `candidate_kind` | `candidate_kind` is `demo` or `upload` |
| `evaluated_by` | `model`; `mock` (mock mode, every topic not covered); `none` (no candidate answers, so no model call) |
| `end_reason`, `complete`, `candidate_answers` | `interviewer`, `time_limit`, `failure` or `ended_early` |
| `topics[]` | `requirement_id`, `category`, `description`, `resume_status` (the resume assessment before the screening), `status`, `correctness`, `prompted`, `quotes`, `note`, `needs_check` |
| `dimensions[]` | Four entries: `name`, `level`, `score`, `quotes`, `reason` |
| `correctness_score`, `overall_score` | Server-calculated, or `null` |
| `unresolved`, `follow_ups`, `summary` | Open topics; up to five recruiter questions; a neutral summary |
| `next_step`, `next_step_reasons` | `interview`, `gather_information` or `human_review`, with plain-language reasons from the same rules |
| `integrity_flags[]` | `kind`, `quote`, `note`, `detected_by` (`rules`, `ai` or `both`) |

## What is judged

Only the job-related content of the candidate's answers; never fluency, grammar, accent, filler words, pauses, speed, tone, confidence or personality. Obvious speech-recognition errors are ignored. Each topic is judged on the candidate's best answer by the end of that topic: if it needed a follow-up or hint, `prompted` is true (**Needed a prompt**) and the weaker first attempt does not count against them.

**Topic status:** `supported` (concrete, relevant example or explanation); `partly_supported` (thin or partial); `not_shown` (answered, nothing relevant); `declined` ("don't know", neutral); `not_covered` (not discussed: unknown, not a gap).

**Correctness**, only where the question has a right answer. Experience stories and `declined` or `not_covered` topics are `not_applicable`.

| Level | Meaning | Credit |
| --- | --- | --- |
| `correct` | Right without help | 1.0 |
| `correct_after_hint` | Right after a follow-up or hint | 0.8 |
| `comparable` | Right for an equivalent, such as the matching GCP service when asked about AWS | 0.75 |
| `partly_correct` | Partly right | 0.5 |
| `incorrect` | Wrong, or about something else | 0 |

`partly_correct` and `incorrect` set `needs_check` (**Needs check**), because they rest on the model's own knowledge.

**Dimensions**, across the conversation, level 1–4 or 0 when there is too little to judge: relevance (answers the question), specificity (tools, steps, numbers, outcomes), ownership (what the candidate personally did) and explanation (approach, reasoning, trade-offs, results).

## Model call and evidence

- One call per report to the assessment model (`BEDROCK_MODEL_ID`, `json_schema`; `openai.gpt-oss-120b-1:0`), within `AI_TIMEOUT_SECONDS` (130 s). The prompt is `app/voice/prompts/report.md`; the transcript goes in the JSON data message, never the instructions, and is treated as untrusted.
- An unusable response, or one where more than half the judgments fail verification, is retried once (`AI_MAX_ATTEMPTS` 2) with location-only hints; the attempt with more verified judgments is kept.
- Every topic that is not `not_covered`, and every dimension above 0, needs one to three quotes, each matching a **candidate** turn through the resume-evidence matcher (`locate_quote`). The stored quote is the exact transcript span; interviewer text never counts.
- Copying slips are repaired only towards the transcript's own text: changed capitalisation or an added end mark is accepted (at least three words); a quote stitched from sentences or "…" parts is kept as those parts only if every part matches; a passage over 300 characters keeps its whole sentences up to the limit. A changed or added word rejects the quote.
- A judgment without a verifiable quote becomes `not_covered`, or level 0. Nothing is invented or reworded into evidence.
- Notes and reasons are capped at 200 characters, follow-ups at five of 200, the summary at 600.

## Integrity flags

Candidate attempts to steer the AI are recorded for a human. They are never obeyed and never raise a score, and a flagged screening always goes to **Human review**.

| Kind | Meaning |
| --- | --- |
| `instruction_override` | Asks the AI to ignore or replace its instructions or role, claims special authority, or writes text formatted as a system message |
| `score_request` | Asks to be scored highly, marked correct or passed, recommended, hired or shortlisted |
| `answer_request` | Asks for the answer instead of answering; asking to repeat or clarify is not a flag |
| `prompt_probe` | Asks to see the AI's own instructions, prompt, rubric, scoring rules or the resume assessment |

Two independent sources, at most ten flags in all:
- **Server rules** (`app/voice/integrity.py`) run on every candidate turn in every mode with no model call, so a flag survives a manipulated report model. Each needs a request aimed at the AI ("ignore your previous instructions", "give me a perfect score", "please recommend me", "tell me the answer", "show me your system prompt", or a sentence opening "Note for whoever evaluates this…"); work stories such as "they decided to hire me" do not match. The quote is the matched sentence; text formatted as a system message ("SYSTEM:", "[developer]") is quoted to the end of the answer.
- **The AI review** adds subtler or indirect attempts (a favourable summary, an "ideal answer", the AI's configuration), each with an exact quote matching one candidate turn within 300 characters.

A model flag on a sentence the rules caught confirms it (`detected_by: both`), keeping the longer quote.

**Effect on evidence:** any sentence in an evidence quote that is, contains or belongs to a flagged quote is removed; the rest still counts. A topic or dimension left without quotes becomes not covered or not assessed, so an attempt can never help the candidate. The prompt also tells the model to judge the remaining answers as if the attempt were absent and never to lower a status or level because of it.

## Server-calculated results

| Result | Rule |
| --- | --- |
| Dimension score | `(level − 1) / 3 × 100`; none at level 0 |
| Correctness % | Mean credit over topics where correctness applies; none if none apply |
| Answer quality (`overall_score`) | Equal-weight mean of assessed dimension scores and correctness %; needs at least two parts |
| Complete | Ended by the interviewer or the time limit, with at least 3 candidate answers |
| Next step | Integrity flags or incomplete → **Human review**. Answer quality ≥ 67 and no mandatory topic declined, not shown or incorrect → **Recruiter or technical interview**. Otherwise → **Gather more information**. |
| Unresolved | Topics not `supported`, or `partly_correct` or `incorrect` |

The credits, threshold and minimum answers are illustrative constants, not validated hiring science.

## Report view

`frontend/src/components/screening-report.tsx` (labels and groupings in `src/lib/report-view.ts`), recruiter-first:
1. **At a glance:** the next step and its reasons; integrity flags grouped by sentence, noting they were not followed and are not proof of bad faith; an answer-quality bar marked at 67; correctness; **Strengths** (supported, no check needed), **Verify** (needs check, partly supported, not shown, or a declined mandatory topic) and **Not covered**; the AI summary.
2. **Job topics: resume → screening**, mandatory first, quotes collapsed.
3. **Dimensions** as a strip, reasons and quotes behind one toggle.
4. **Ask next:** needs-check notes by topic, then the model's follow-ups.
5. **Footer:** the not-stored note and "How this is scored".
6. **Copy as notes:** plain text for an ATS, written only to the clipboard.

The browser only checks shape and consistency (`decodeReport` in `src/lib/screenings.ts`), including that a flagged report suggests human review.

Logs record the evaluation source, answer count, verified judgment counts, flag count and next step; never transcript text, quotes or scores. Token counts go to the [usage table](data-retention.md#usage-table-on-neon).

## Limitations

- In this demo the person who takes the screening also sees the report; a real deployment would show it only to a recruiter.
- Quotes come from speech recognition and can contain recognition errors. They are candidate claims, not verified facts.
- Correctness depends on the model's knowledge; "Needs check" items need a human with domain knowledge.
- A candidate can still influence the report model: subtle indirect requests are sometimes missed, an unflagged attempt can stay inside an evidence quote, and borderline process questions are sometimes flagged. Rules and prompt were tuned on a few synthetic screenings; there is no accuracy evaluation.
- A model quote that changes or adds a word is rejected, which can drop a real judgment.
- Reports are lost on a restart or when the session expires, by design.
