# Assessment UI (module 11)

The job's Candidates tab accepts a temporary text-based PDF and immediately calls `POST /jobs/{job_id}/resumes/assess` with raw `application/pdf` bytes on selection. Synthetic candidate profiles receive any current precomputed assessment with their read-only profile response. The backend supplies canonical job context, validated source citations, interpretation and deterministic scoring when the manual refresh command runs. The frontend checks the result against the selected job and source before displaying it. No filename is sent with an uploaded PDF.

Both flows show score availability and possible range, mandatory coverage, requirement statuses, model reasons, verbatim excerpts linked to highlighted source text, verification gaps and existing job questions linked to unresolved requirements. Mock mode leaves all requirements unknown and the score unavailable. A range reflects uncertainty, not a predicted hiring outcome. The rubric and any AI interpretation require human review; citation checks prove location only.

The Candidates table highlights the latest uploaded result and sorts available point scores descending. Results without a point score remain unresolved and follow alphabetically. Selecting the uploaded row's name or **View details** opens its complete evidence view in the page; demo names open their existing profile route. The current extraction contract has no uploaded name/title field, so the table says “Uploaded candidate” and “Not extracted” rather than guessing identity. The candidate pool API returns a cached score or range for each demo member when a current snapshot exists.

Uploaded results and the selected PDF live only in React memory. Clear cancels the browser request and discards them. Leaving the page, refresh and browser history restoration also discard them. A disconnected backend request may still finish within its server deadline. Demo assessments reside in the versioned JSON snapshot, never browser storage. Backend responses return `Cache-Control: no-store`; deployment caches and provider retention still need review.

Assessment uses the backend's configured `AI_MODE`. The saved local backend configuration is Bedrock, so clicking an assessment action there makes provider calls. For no-cost review, start a backend process with `AI_MODE=mock` explicitly set in its process environment and use synthetic data. Mock results verify the workflow but cannot establish semantic match quality. The module has no live interpretation accuracy evaluation.

Offline checks cover context/source/quote/count validation, Unicode offsets, upload and empty-body transport, error redaction, cancellation, lint, TypeScript and a production build. Browser interaction and responsive verification remain unconfirmed because computer-use permission was unavailable during module 11 verification.

## Candidate details and availability (2026-10-27)

**Add resume PDF** now opens a panel before the file picker. The recruiter can set optional availability (not provided, available now, serving notice with a last working day, or not yet serving with a notice length in days), then choose the PDF. After assessment, the panel shows Name and Current position prefilled from `structured.identity`: text the extraction found and the backend verified as an exact source span. Both stay editable and are never sent back or used for scoring. Editing availability and pressing **Update availability** calls only `POST /availability`; the AI assessment is not repeated. The table has an **Availability** column (for example "Joins in ~20 days · +4" or "Not provided · no penalty") and sorts point scores by `ranking_score`. Judgments with comparable experience show "Comparable experience" and appear under both strengths and verification gaps. Everything entered stays in React memory and clears with the upload.

## Match estimate and confidence (2026-10-27)

The Candidates table shows one **Match estimate** per candidate with a confidence label (Very high, High, Medium, Low) instead of a range, and sorts every assessed candidate by estimate plus the availability bonus; previously ranges sorted alphabetically after point scores. The details view shows the estimate and confidence first, then the range as "If unverified items resolve" and mandatory coverage. Uploads rank the same way: `POST /availability` receives the upload's `match_estimate`.

## Screening panel (module 13, 2026-10-28)

Screening can start from the job's candidate table or the demo profile:
- **Candidate table:** columns are Candidate name, Title, Experience, Match estimate, Availability, Source, **Screening**, **Details**. A row's **Start** button (telephone-handset icon) opens the consent step just below the table, titled with the candidate's name. Other Start buttons are disabled while a screening is starting or live, because the backend allows one at a time. Details shows **View ↗**.
- **Upload details:** the header has a **Start screening** action that opens the same inline panel.
- **Demo profile:** the panel sits above Resume evidence.

The optional **AI screening conversation** panel It covers server notice and consent, voice or text, a live transcript, a countdown, Mute, Continue by text and End. See [voice sessions](voice-sessions.md#browser-client-and-text-alternative-module-13).
- **Uploads:** the panel needs the upload's signed `screening_context`. Without it, Start is disabled with an explanation.
- **Clean-up:** clearing the upload, navigating away, refreshing or closing the panel discards the transcript and ends the backend session.
- **Assessment type:** the `Assessment` type now includes the optional `screening_context`, validated by `decodeAssessment`.
