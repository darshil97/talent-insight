# Assessment UI (module 11)

The job detail page accepts a temporary text-based PDF and calls `POST /jobs/{job_id}/resumes/assess` with raw `application/pdf` bytes. A synthetic candidate profile calls `POST /jobs/{job_id}/candidates/{candidate_id}/assess` with an empty body. The backend supplies canonical job context, validated source citations, interpretation and deterministic scoring. The frontend checks the response against the selected job and source before displaying it. No filename or candidate profile is sent in either request.

Both flows show score availability and possible range, mandatory coverage, requirement statuses, model reasons, verbatim excerpts linked to highlighted source text, verification gaps and existing job questions linked to unresolved requirements. Mock mode leaves all requirements unknown and the score unavailable. A range reflects uncertainty, not a predicted hiring outcome. The rubric and any AI interpretation require human review; citation checks prove location only.

Results and the selected PDF live only in React memory. Clear cancels the browser request and discards them. Leaving the page, refresh and browser history restoration also discard them. A disconnected backend request may still finish within its server deadline. The UI never uses browser storage. Backend assessment endpoints return `Cache-Control: no-store`; deployment caches and provider retention still need review.

Assessment uses the backend's configured `AI_MODE`. The saved local backend configuration is Bedrock, so clicking an assessment action there makes provider calls. For no-cost review, start a backend process with `AI_MODE=mock` explicitly set in its process environment and use synthetic data. Mock results verify the workflow but cannot establish semantic match quality. The module has no live interpretation accuracy evaluation.

Offline checks cover context/source/quote/count validation, Unicode offsets, upload and empty-body transport, error redaction, cancellation, lint, TypeScript and a production build. Browser interaction and responsive verification remain unconfirmed because computer-use permission was unavailable during module 11 verification.
