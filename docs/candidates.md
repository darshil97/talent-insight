# Candidate pipeline and profiles — module 7

Modules 5 and 6 are approved. Module 7 adds a read-only candidate pool and profiles within the selected job. The existing twelve synthetic Neon candidates and their memberships are unchanged. The pipeline is an alphabetical pool; no workflow stages, rankings, match scores or hiring recommendations are introduced.

## API and membership boundary

| FastAPI route | Response |
| --- | --- |
| `GET /jobs/{job_id}/candidates` | `{"job": JobSummary, "candidates": CandidateSummary[]}` |
| `GET /jobs/{job_id}/candidates/{candidate_id}` | `{"job": JobSummary, "candidate": CandidateDetail}` |

Both IDs use the existing stable `demo_...` syntax (at most 64 characters). The backend first verifies the job exists. It lists candidates or loads a profile through actual `job_candidates` membership, never by interpreting an ID prefix. A missing job or a candidate outside that job returns a safe 404; invalid ID syntax returns 422. An existing job with no members returns an empty pool. Database failures return sanitized 503 responses.

The routes reuse the module 6 read-only session and five-second SQL statement timeout. Responses and errors are `no-store`. Only GET routes were added. Startup/health still do not query, seed or migrate. No database schema or configuration changes were needed.

`CandidateSummary` contains only `id`, `display_name`, `headline`, `summary` and `is_demo: true`. Detail adds `resume_text`, `claims` and `offset_unit: "unicode_code_point"`. Claims contain `kind` (`skill`, `experience`, `qualification`), `label`, `quote`, `start` and `end`. Internal scenario labels remain private fixture metadata; they are never returned as candidate statuses or scores.

## Source evidence

Before returning a detail, the backend validates the stored profile shape, demo marker and nonempty text. Name/headline/summary must appear in the synthetic source resume. Claim offsets must be integers in range, the exact source slice must equal the quote, and the label must appear in that quote. Invalid provenance fails closed with a safe 500 and no resume or validation payload in logs/errors.

Offsets are zero-based Unicode code points with an exclusive end, matching Python string slicing. The frontend validates the job/candidate context and source slices again at its network boundary, using code-point-aware slicing so emoji do not shift highlights. Text is rendered through React as literal content, without interpreting HTML or embedded instructions.

Summaries are labeled as authored demo summaries. Excerpts are curated source evidence, not inferred skills or an assessment against the selected job. Missing excerpt categories retain neutral unknown-evidence wording and the complete source remains visible. No excerpt, qualification or interview answer is fabricated.

## Frontend workflow

From a job detail, choose **Review demo candidates**. The pool at `/jobs/<job_id>/candidates` shows its job context, actual member count, synthetic labels and profile links. Profiles at `/jobs/<job_id>/candidates/<candidate_id>` show the authored summary, grouped excerpts and complete source resume, with links back to the pool and requirements.

**View in source resume** moves focus to the source section and highlights exactly that excerpt. **Clear highlight** removes it. Selection is React memory only and clears on refresh or route change; no candidate data is written to browser storage. Job navigation remains active on nested candidate routes. Each route retains one main landmark and one h1.

Loading, empty pool, missing job/profile and service failure are distinct. Error views support retry; navigation can interrupt pending requests through the existing abort handling. The browser sends direct credential-free FastAPI requests using the existing validated public API origin, no-store behavior and 20-second timeout. No JSON/fixture fallback or product mock mode exists. Like module 6, valid dynamic frontend route patterns return their HTML shell with HTTP 200 before browser fetching; the API supplies missing-record HTTP 404 responses.

## Verification

- Backend: **99 passed, three opt-in Neon checks skipped**, with warnings treated as errors. New tests cover all twelve fixture profiles, all four pools, exact membership and public fields, cross-job/missing IDs, empty pools, corrupt provenance/redaction, Unicode offsets, empty evidence and safe database failures/CORS. SQL compilation checks verify both membership filters without a database.
- Frontend: **11 Node tests passed** (five new candidate tests plus the six existing job-client tests), covering payload/context validation, corrupt evidence and Unicode slicing. ESLint, TypeScript and the Webpack production build passed. No dependencies were installed.
- Live local application reads loaded the existing Data Scientist pool and Avery Chen profile from Neon. The full opt-in Neon suite was not repeated. No migrations, seeds, fixture edits or external infrastructure changes occurred.
- Production browser state checks used a temporary local mock API with database configuration disabled: empty pool, loading/navigation away, service failure, keyboard retry/recovery, missing/cross-job profile recovery, no curated evidence, exact highlighting/focus, clearing and inert rendering of test HTML/instructions. Test payloads were never written to Neon or shipped as an application mode.
- Pool/profile reflow checks passed at 320, 375, 768, 1024 and 1280 CSS pixels without horizontal scrolling; mobile/desktop screenshots were inspected. Browser checks are manual, not an automated browser suite, screen-reader audit or accessibility conformance claim.

No AI/voice integration, uploaded-candidate persistence, deployment or commit was introduced. Hosted behavior, other browsers and other operating systems remain unverified.

After review and explicit approval, the next module is **8 — resume upload and PDF extraction**: bounded stateless upload, file/content validation, clear extraction failures and temporary frontend results. Structured AI extraction and matching remain modules 9–11.
