# Jobs listing and details — module 6

Module 6 is approved. The browser reads the shared Neon catalog through FastAPI. The frontend contains presentation and request-state handling; validation and database access stay in the backend. Module 7 adds [candidate APIs/views](candidates.md), and module 8 adds [temporary PDF text review](resumes.md) to job details. Scoring and provider integration remain pending.

## Editable job definitions

Each job has its own versioned JSON file under `backend/app/fixtures/jobs/`:

- `demo_ds.json`: Data Scientist.
- `demo_mle.json`: Machine Learning Engineer.
- `demo_ai.json`: AI / LLM Engineer.
- `demo_backend.json`: Backend Engineer.

These files contain the existing role/client descriptions, skills, screening criteria, questions and categorized requirements. Candidate profiles and membership records stay in `backend/app/fixtures/candidates.json`. Splitting the original `catalog.json` preserved all values; no database changes were needed or applied in module 6. All files are included in the backend wheel.

To edit a role, change its JSON. To add one, copy an existing job file, choose a unique stable `demo_...` ID and name the file `<id>.json`. Use new, globally unique requirement/question IDs and update each question's `requirement_ids` to point to requirements in that job. Preserve IDs when editing existing records. Keep `is_demo: true`; files are only for curated synthetic demo records. A new job may have no candidates. Do not copy real candidate data into these files.

Requirement categories are `mandatory`, `experience`, `preferred` and `qualification`. Only experience requirements may specify `minimum_years` (0–99); other requirements use `null`. The order of the JSON requirements determines their display order. No weights or match scores are introduced here.

Validate from the repository root in the existing Conda environment:

```sh
python -m app.seed --validate-only
```

This reads and validates every job file, uniqueness, question references, candidate evidence and memberships. It does not load dotenv, connect or write to a database. A missing/invalid job file fails validation rather than silently using stale hardcoded data.

JSON is an authoring source, not a runtime fallback. Runtime reads continue to use the existing shared Neon project. Publishing edits to that catalog requires review and explicit approval for `python -m app.seed`; neither app startup nor the launcher runs it. The seed is atomic and preserves unrelated rows. Removing a file does not delete database rows; removing or reordering existing requirements needs a reviewed data update because the seed does not prune old IDs. No admin UI or auto-sync was added.

## HTTP contracts

| FastAPI route | Success | Other expected responses |
| --- | --- | --- |
| `GET /jobs` | `{"jobs": [...]}` sorted by title; empty catalog is `{"jobs": []}` | 503 if catalog access is unavailable |
| `GET /jobs/{job_id}` | One job with ordered requirements, screening criteria and questions | 404 for a missing valid ID; 422 for invalid ID syntax; 503 if catalog access is unavailable |

List fields are `id`, `title`, `client`, `description`, `skills` and `is_demo`. Details add `requirements` (`id`, `category`, `description`, `minimum_years`, `sort_order`), `screening_criteria`, and `questions` (`id`, `text`, `requirement_ids`). There are no candidate records, scenario labels or match scores in these responses. Paths accept stable `demo_...` IDs, at most 64 characters.

Successes and safe errors use `Cache-Control: no-store`. Errors retain the [foundation envelope](backend-foundation.md). Database errors return sanitized 503 responses; invalid stored response data fails with a safe 500. Catalog requests use read-only transactions with a five-second SQL statement timeout. Engine creation is lazy at app lifespan and does not connect; shutdown disposes the pool. Health still makes no database calls.

## Frontend behavior

`/jobs` lists roles with synthetic labels and links to `/jobs/<id>`. Details show the description, skills, requirements grouped by category, screening focus and prepared questions. The Jobs navigation link remains active on details and nested candidate routes. Module 7 adds a **Review demo candidates** link from details. No inactive upload buttons are shown.

The typed client validates response shapes, demo markers, categories and question references before rendering. It validates `NEXT_PUBLIC_API_BASE_URL` as a credential-free origin (HTTPS remotely, HTTP only on loopback); absent configuration defaults to `http://127.0.0.1:8000`. Requests omit browser credentials and caching, reject redirects, time out after 20 seconds and abort on unmount. State remains in React memory; there is no browser storage or mock-data fallback.

Loading has a status announcement. Empty, unavailable and missing-job states are distinct; empty/error views offer refresh/retry. A missing API job returns HTTP 404; because fetching occurs in the browser, the frontend route itself initially returns its normal HTML with HTTP 200 before showing the missing-job view. Unknown frontend routes outside these route patterns still return HTTP 404. The UI is not intended as an indexed public job board.

Use [the local launcher](local-development.md) or configure CORS/API origin when running the apps directly. CORS is not authentication. Production public settings must be supplied before the frontend build.

## Verification

Module 6 checks in the dedicated Conda environment:

- Backend: 77 passed, three opt-in Neon tests skipped; Ruff lint/format and pip dependency checks passed. Tests cover typed success, empty catalog, IDs/404, safe 503/CORS, read-only SQL setup, engine lifecycle and invalid stored data. Job-file authoring tests cover edits, an added role without candidates, invalid filenames, missing/malformed files and duplicate references.
- Frontend: six Node tests passed for API shape validation, public URL validation, request options, error distinctions and cancellation. ESLint, TypeScript and the Webpack production build passed without installing dependencies.
- Packaging: the built backend wheel contains all four job files and the candidate fixture; a comparison with the previous combined fixture confirmed identical job/candidate/membership values.
- Browser: the real local API read all four existing Neon jobs and Data Scientist details. Production-browser edge cases used a temporary mock API with no database configuration, checking loading, empty, error, keyboard retry/recovery, navigation away during loading and missing-job recovery. Listing/details fit 320/375/768/1024/1280 CSS-pixel widths without horizontal scrolling; screenshots and active navigation were inspected.
- Launcher: Bash syntax and four ownership/configuration unit tests passed. Local start, duplicate-start detection, stop, restart/status/log following and refusal to terminate unmanaged test servers were exercised. Logs/PID records remain private and ignored.

No migration, seed, external infrastructure change, AI/voice call, deployment or commit occurred. The opt-in Neon regression suite was not repeated; live verification here was limited to the read-only application jobs path. Browser checks are manual, not an automated browser suite or screen-reader audit. Hosted deployment, other browser engines and cross-platform launcher behavior remain unverified.

Modules 1–10 are reviewed and approved. Module 11 adds the [assessment UI](assessment-ui.md) to job and candidate pages and awaits review. PDF extraction details remain in [PDF extraction](resumes.md).
