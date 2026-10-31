# Assessment UI

Where assessments appear in the frontend. The backend owns extraction, interpretation and scoring; the frontend validates and displays.

## Uploading a resume (Candidates tab)

1. **＋ Add resume PDF** opens a panel with optional availability, sent as not provided if incomplete.
2. **Choose PDF**: the browser checks the name, type, emptiness and size against `GET /resumes/limits`.
3. **On selection:** the raw bytes go, without the filename, to `POST /jobs/{job_id}/resumes/assess`, a paid call in Bedrock mode with a 360 s browser timeout. Then `POST /availability` sets the [ranking](scoring.md#availability-and-ranking). **Cancel** aborts.
4. **The result** is one temporary row ("JUST ADDED", Source "Temporary") ranked with the demo candidates. Clear it to add another.
5. **Name** and **Current position** are prefilled from the verified `structured.identity`. They are editable, display-only and never sent or scored.
   - **Update availability** calls only `/availability`.
   - If that call fails, the row ranks without a bonus.
6. **The name or View ↗** opens the evidence view inline.
7. **Start screening** needs the signed `screening_context`; otherwise it is disabled with a reason. One screening runs at a time; see [voice sessions](voice-sessions.md).

Backend error codes map to fixed, safe messages.

## Demo profiles

A profile shows **Precomputed job assessment** from the [snapshot](candidates.md#demo-assessment-snapshot), checked by the same decoder as uploads. With no current entry, it says so. It makes no provider call.

## Assessment view

`assessment-result.tsx`, shared by uploads and profiles:

- **Header:** demo or upload, mock or AI, "Human review required" and the backend notice.
- **Figures:**
  - match estimate with confidence;
  - "If unverified items resolve" (`lower`–`upper`);
  - mandatory coverage;
  - interpreted and unknown counts.
- **Lists:** supported, comparable and partial evidence; and **Verification gaps** (everything not `met`).
- **Requirement by requirement:** status, reason and cited quotes. **View excerpt in source** highlights the exact span.
- **Follow-up questions:** existing job questions linked to any requirement not `met`.
- **Source text:** shown page by page.

| Status | Label |
| --- | --- |
| `met` | Supported |
| `transferable` | Comparable experience |
| `partial` | Partly supported |
| `not_met` | Evidence does not meet this requirement |
| `unknown` | Needs verification |

## Frontend validation

`decodeAssessment` (`frontend/src/lib/assessments.ts`) rejects a result unless:

- job context, source kind and candidate ID match the page;
- `mode` is `mock` or `bedrock`;
- every quote and identity value equals the source at its code-point offsets;
- there is one judgment per requirement, with valid indices;
- counts and categories agree with the judgments;
- the estimate is the range midpoint, and a point score exists only when nothing is unknown.

## Temporary state

- The PDF, result, edits and availability live only in React state.
- Clearing, leaving the page, refresh, `pagehide` or a back-forward restore discards them.
- Nothing goes to browser storage, URLs or the catalog cache.
- A cancelled request may still finish on the backend.

## Limits

- Mock results test the workflow, not match quality.
- Frontend tests (`frontend/tests/`) are Node unit tests; there is no automated browser suite.
