# Candidate pipeline and profiles — module 7

Modules 5 and 6 are approved. Module 7 added a read-only candidate pool and profiles within the selected job. The twelve synthetic Neon candidates and memberships remain unchanged. The current pool sorts available precomputed match scores while retaining alphabetical order for unresolved rows. No workflow stages or hiring recommendations are introduced.

## API and membership boundary

| FastAPI route | Response |
| --- | --- |
| `GET /jobs/{job_id}/candidates` | `{"job": JobSummary, "candidates": CandidateTableSummary[]}` |
| `GET /jobs/{job_id}/candidates/{candidate_id}` | `{"job": JobSummary, "candidate": CandidateDetail, "availability": Availability, "assessment": Assessment or null}` |
| `POST /availability` | Body `{"availability": AvailabilityInput, "match_score": number or null}` → `{"availability": Availability, "ranking_score": number or null}`; stateless, no-store, never logged |

Both IDs use the existing stable `demo_...` syntax (at most 64 characters). The backend first verifies the job exists. It lists candidates or loads a profile through actual `job_candidates` membership, never by interpreting an ID prefix. A missing job or a candidate outside that job returns a safe 404; invalid ID syntax returns 422. An existing job with no members returns an empty pool. Database failures return sanitized 503 responses.

The routes reuse the module 6 read-only session and five-second SQL statement timeout. Responses and errors are `no-store`. Only GET routes were added. Startup/health still do not query, seed or migrate. No database schema or configuration changes were needed.

`CandidateSummary` contains `id`, `display_name`, `headline`, `summary` and `is_demo: true`. The job-scoped list adds `stated_experience`, taken only from a validated source experience claim or `null`; it is a source claim, not verified years of relevant experience. The list also returns `snapshot_available`, `match_score`, `score_lower` and `score_upper` from the current snapshot. Detail adds `resume_text`, `claims` and `offset_unit: "unicode_code_point"`. Claims contain `kind` (`skill`, `experience`, `qualification`), `label`, `quote`, `start` and `end`. Internal scenario labels remain private fixture metadata.

### Availability and ranking

Each demo candidate may carry self-reported availability in `candidates.json` (`availability: {status, last_working_day | notice_days}` or `null`), stored in the `demo_candidates` columns. `app/ranking.py` turns it into `days_to_join` (0 when available now, days until the last working day, or the notice length) and a small bonus from `ranking.availability_tiers` (default ≤15 days +5, ≤30 +4, ≤45 +3, ≤60 +2, ≤90 +1, otherwise 0). Not provided is `null` days and bonus 0: no deduction. Pool rows return `match_estimate`, `confidence`, `availability` and `ranking_score` = match estimate + bonus (`null` only when no assessment exists); every candidate with an assessment is ranked by it, with ties by name. The match score, range and AI snapshot never include availability, so editing notice details needs no refresh. Demo last working days are fixed dates; once one passes, that candidate counts as available now.

## Source evidence

Before returning a detail, the backend validates the stored profile shape, demo marker and nonempty text. Name/headline/summary must appear in the synthetic source resume. Claim offsets must be integers in range, the exact source slice must equal the quote, and the label must appear in that quote. Invalid provenance fails closed with a safe 500 and no resume or validation payload in logs/errors.

Offsets are zero-based Unicode code points with an exclusive end, matching Python string slicing. The frontend validates the job/candidate context and source slices again at its network boundary, using code-point-aware slicing so emoji do not shift highlights. Text is rendered through React as literal content, without interpreting HTML or embedded instructions.

Summaries are labeled as authored demo summaries. Excerpts are curated source evidence, not inferred skills or an assessment against the selected job. Missing excerpt categories retain neutral unknown-evidence wording and the complete source remains visible. No excerpt, qualification or interview answer is fabricated.

## Frontend workflow

From a job detail, choose the **Candidates** tab. The pool at `/jobs/<job_id>/candidates` shows its job context, a table of members, stated years where supported, cached score or range, and profile links. Profiles at `/jobs/<job_id>/candidates/<candidate_id>` show the authored summary, grouped excerpts, complete source resume and any current cached assessment. Missing or stale snapshots display as pending; neither page invokes the provider for demo candidates.

## Adding and refreshing demo candidates

The fixture and shared catalog have three synthetic candidates in each role plus one Backend Engineer also assigned to Senior Data Scientist: four Data Scientist memberships and three in each other role, across twelve distinct synthetic people and thirteen memberships. Each synthetic resume includes experience, projects, skills and education/training sections; private reference resumes were used for the level of detail only. To add one, edit `backend/app/fixtures/candidates.json`: add a candidate with a stable `demo_...` ID, source resume text, display context copied from that text and only exact supporting claim quotes. Put its job links in that candidate's `memberships` array:

```json
"memberships": [
  {"job_id": "demo_ds", "demo_scenario": "partial"},
  {"job_id": "demo_backend", "demo_scenario": "transferable"}
]
```

The scenario is internal demo metadata for that candidate **in that job**; it can differ across jobs. The loader derives database membership rows from these links, so candidate IDs are not repeated in a separate authoring list. Membership, rather than the candidate ID prefix, selects the job. The fixture validator checks IDs, unique links, references, quotes, display context and three to five memberships for every populated job. A new job can be staged with zero candidates, but the snapshot refresh requires three to five for every job.

After editing, run `python -m app.seed --validate-only` and `python -m app.refresh_demo` from `backend/` in the `talent-insight` Conda environment. The first validates the catalog; the second checks that every job has three to five candidates and prints counts. Both are offline and read-only; running either does **not** populate scores. The Neon catalog remains the runtime source for candidates, so future fixture changes need a separately approved `python -m app.seed` before they appear in the app. Removing jobs needs a separate reviewed data transition because the seed only upserts; the four-domain retirement is complete. Once the catalog and interpretation are reviewed, run `python -m app.refresh_demo --run` to generate `backend/app/fixtures/assessments.json`. This explicitly calls Bedrock for extraction and interpretation of every demo membership, then atomically replaces the complete JSON only if all succeed. For the current thirteen memberships that is at least 26 provider requests, with configured retries possible. On failure, ignored local extraction and assessment checkpoints retain validated synthetic work; rerun the same command to resume. Each checkpoint entry is checked against the current job, source, code fingerprint and digest before reuse. Successful publication removes both checkpoints. The command does not change Neon. Do not hand edit the generated assessment or checkpoint files. A `weak` scenario label is authoring metadata, not a score target: the backend leaves a point score unavailable when evidence is unresolved. Evaluate the cross-domain assessment after refresh before changing scoring logic.

The API matches each snapshot to the current job requirements, candidate resume, scoring weights and extraction/scoring source code. When those change, or a snapshot is absent, the pool and profile show pending until the command is rerun. The JSON cache now contains all thirteen validated memberships. Five have a point score; eight retain an uncertainty range because at least one requirement is unknown. Uploaded PDFs use the same backend extraction, interpretation and deterministic scoring functions on selection, and remain temporary in React memory.

**View in source resume** moves focus to the source section and highlights exactly that excerpt. **Clear highlight** removes it. Selection is React memory only and clears on refresh or route change; no candidate data is written to browser storage. Job navigation remains active on nested candidate routes. Each route retains one main landmark and one h1.

Loading, empty pool, missing job/profile and service failure are distinct. Error views support retry; navigation can interrupt pending requests through the existing abort handling. The browser sends direct credential-free FastAPI requests using the existing validated public API origin, no-store behavior and 20-second timeout. No JSON/fixture fallback or product mock mode exists. Like module 6, valid dynamic frontend route patterns return their HTML shell with HTTP 200 before browser fetching; the API supplies missing-record HTTP 404 responses.

## Verification

- Backend: **99 passed, three opt-in Neon checks skipped**, with warnings treated as errors. New tests cover all twelve fixture profiles, all four pools, exact membership and public fields, cross-job/missing IDs, empty pools, corrupt provenance/redaction, Unicode offsets, empty evidence and safe database failures/CORS. SQL compilation checks verify both membership filters without a database.
- Frontend: **11 Node tests passed** (five new candidate tests plus the six existing job-client tests), covering payload/context validation, corrupt evidence and Unicode slicing. ESLint, TypeScript and the Webpack production build passed. No dependencies were installed.
- Live local application reads loaded the existing Data Scientist pool and Avery Chen profile from Neon. The full opt-in Neon suite was not repeated. No migrations, seeds, fixture edits or external infrastructure changes occurred.
- Production browser state checks used a temporary local mock API with database configuration disabled: empty pool, loading/navigation away, service failure, keyboard retry/recovery, missing/cross-job profile recovery, no curated evidence, exact highlighting/focus, clearing and inert rendering of test HTML/instructions. Test payloads were never written to Neon or shipped as an application mode.
- Pool/profile reflow checks passed at 320, 375, 768, 1024 and 1280 CSS pixels without horizontal scrolling; mobile/desktop screenshots were inspected. Browser checks are manual, not an automated browser suite, screen-reader audit or accessibility conformance claim.

No AI/voice integration, uploaded-candidate persistence, deployment or commit was introduced. Hosted behavior, other browsers and other operating systems remain unverified.

Module 7 is approved. The later [assessment UI](assessment-ui.md) and demo snapshot workflow supersede its original pending-score behavior. The snapshot workflow awaits review.
