# Talent Insight — project context

Last updated: 2026-10-24 (Asia/Kolkata). Modules 1–9 are complete; modules 5, 6, 7 and 8 have all been reviewed and approved by the user. Module 9 awaits completion review. Modules 10–15 remain pending and unauthorized. The user's private Bedrock bearer token successfully invoked `openai.gpt-oss-120b-1:0` in `ap-southeast-2` with a small source-validated synthetic extraction. The selected configuration is saved privately; shared Neon data and existing credentials are preserved. Read `AGENTS.md` first.

## 1. Project overview

Build a focused AI recruiting assistant for technical recruiters, staffing firms and small agencies, suitable for a portfolio demonstration and later client adaptation.

Core workflow: **select job → review candidates → upload resume → inspect job match and evidence → optional browser screening → review report → human decision**.

MVP: a curated set of Data Scientist, ML Engineer, AI/LLM Engineer and Backend Engineer jobs; a fixed pool of clearly synthetic candidates per job; anonymous PDF upload; transparent requirement matching; temporary results; later voice screening with text fallback and structured reports. Profiles should include strong, partial, weak, transferable, ambiguous and incomplete evidence.

Non-goals: complete ATS, public job creation, admin UI, login, outbound calls, automated hiring decisions, permanent uploaded-candidate records, vector database, Redis or multi-agent orchestration. DOCX and object storage are optional later work.

First functional milestone spans modules 2–11: local run instructions, seeded jobs/candidates, PDF upload/extraction, structured parsing, deterministic matching, evidence views and tests. Completing module 1 alone does not satisfy that milestone.

## 2. Architecture and technology stack

Agreed stack (frontend/backend installed, Neon catalog verified and a small synthetic Bedrock extraction verified; broader AI/voice evaluation and deployment pending):

| Component | Technology and responsibility | Deployment |
| --- | --- | --- |
| Frontend | Next.js App Router, React, TypeScript, Tailwind; pages, upload interactions, in-memory results and voice UI | Vercel |
| Backend | Python, FastAPI, Pydantic; validation, file processing, scoring, provider calls, session preparation and reports | Render |
| Database | Existing Neon project `talent-insight`; SQLAlchemy 2.0, psycopg 3 and Alembic; curated demo data only | Neon; same database for local and hosted runs |
| Recruiting AI | LangChain `ChatBedrockConverse` / AWS SDK; configurable model; validated extraction, interpretation, questions and reports | AWS Bedrock |
| Voice | Deepgram Voice Agent; browser audio directly to provider with backend-issued short-lived token | Deepgram |
| Storage | In-memory file processing initially; no object storage dependency | None initially |

Browser → FastAPI over HTTPS for application operations; only FastAPI accesses Postgres and Bedrock. Browser → Deepgram for real-time audio. Reusable interviewer rules stay separate from server-prepared job/candidate context. No AWS key or permanent Deepgram key may reach the browser. Deepgram-to-Bedrock credential handling remains unresolved; see section 9 and [provider research](docs/provider-research.md).

## 3. Finalized decisions

- User update for module 4: the database remains on Neon for both local and hosted runs. The actual existing project is **`talent-insight`** (singular), ID `<NEON_PROJECT_ID>`. Use its existing branch `<NEON_BRANCH_ID>`, named `production`, and database `neondb`; no new project, branch or database was created. There are no application environment modes or separate development/test/production branches. `APP_ENV` is removed.
- Neon MCP is configured and working; the earlier OAuth credential-lock issue is resolved. Direct and pooled application connectivity are verified. The ignored local `backend/.env` contains both URLs with owner-only permissions. Configure those same values as hosted backend secrets at deployment; never place them in frontend settings or chat. No local PostgreSQL server is used. Default tests need no database; opt-in Neon checks are read-only and never reset shared data.
- Work in one approved module at a time. Finish, verify, update this document and stop for review. The final module-gate instruction in the brief overrides the earlier broad instruction to begin Phase 1 immediately.
- Keep presentation and business logic separate. Do not use Next.js as a second recruiting backend.
- Module 6 user decision: keep one editable JSON file per job, under `backend/app/fixtures/jobs/<job_id>.json`. The existing Neon database remains the runtime source; JSON edits are validated offline and reach Neon only through an explicitly approved seed. No runtime file fallback or startup synchronization. New job files may have no candidates; existing synthetic candidate/membership data remains unchanged.
- The user supplied a reference launcher and authorized adapting it. Root `run_local.sh` manages local start/stop/status/restart/logs using the existing Conda environment. It binds to loopback HTTP, sets API/CORS process defaults, preserves dotenv/database configuration and never installs, migrates, seeds or terminates arbitrary listeners by port.
- Module 7 pipeline scope: an alphabetical read-only pool within each job, using actual membership rather than ID prefixes. The current schema has no stage/decision tracking, and none was added. Authored demo summaries, curated source excerpts and complete synthetic resumes are distinguished from later AI interpretation/scoring. Internal scenario labels are not exposed. Source ranges use zero-based Unicode code points with an exclusive end.
- Module 8 scope: stateless anonymous PDF extraction at `/resumes/extract`, using raw `application/pdf` bytes rather than multipart disk spooling. Job pages show temporary page text only; no candidate record, job assessment, OCR, AI parsing or score is produced. Pinned pypdf runs in a disposable process with server-owned size/page/text/time/concurrency limits. See [PDF extraction](docs/resumes.md), including platform and extraction limitations.
- Module 9 scope: backend-only structured-extraction APIs for server-parsed PDF uploads and actual job-member synthetic resumes. Canonical job context stays server-owned. Facts are literal source mentions with unique page quotes and backend-calculated offsets; missing categories stay unknown. No criterion assessment, inferred years, scores or recommendation is produced. Explicit `mock`/`bedrock` selection, bounded attempts/deadlines/admission and no silent fallback. Selected model `openai.gpt-oss-120b-1:0`, region `ap-southeast-2`, fixed method `json_schema`, with schema also stated in the server prompt. See [structured extraction](docs/structured-extraction.md) and provider research for live-check limitations.
- No model ID is chosen without checking actual account/region support. External model outputs require backend schema validation and evidence provenance checks.
- Scoring is deterministic and job-specific. Proposed starting weights are mandatory 50%, experience 25%, preferred 15%, qualifications 10%; these are illustrative, configurable and unvalidated. Exact unknown-evidence math must be specified and tested in module 10 before scores are exposed.
- Missing evidence stays unknown. Show mandatory coverage, traceable excerpts, strengths, verification gaps and follow-up questions alongside the score. The score is neither a performance probability nor an automatic decision.
- Keep resume assessment, interview assessment and recruiter next-step suggestion separate. Reports distinguish resume evidence from candidate statements. Suggested actions: recruiter/technical interview, gather information, or human review.
- Permanent tables contain curated synthetic jobs/candidates only. Uploaded resumes, candidates, transcripts and reports are not persisted by default. Frontend memory clears on refresh; do not use localStorage, sessionStorage or IndexedDB for these results.
- Treat all uploaded text as untrusted data, never instructions. Use job-related criteria only, no protected-trait inference or voice-characteristic scoring. Consent precedes audio capture/processing; provide text fallback.
- External infrastructure changes, deployment and significant paid API usage require approval. The user explicitly authorized the module 4 Neon setup; its additive migration and synthetic seed were applied. No application deployment or commits requested.
- Document limitations and obtain jurisdiction-specific review before real-world use; do not claim legal compliance or improved hiring outcomes.

Selected in module 2: `frontend/` and `backend/` layout; npm with an exact dependency lock; a dedicated **Anaconda environment named `talent-insight`**, per the user's explicit instruction, containing Python 3.12 and Node 24. Use Conda rather than a separate virtual environment or Conda base. `environment.yml` selects runtime families; `backend/requirements-dev.lock` and `frontend/package-lock.json` pin application dependencies. Python is currently constrained to 3.12; support for newer minors requires verification.

Next.js uses its supported Webpack option for development and production builds. Turbopack failed to bind its worker socket in this environment, including on an approved retry outside the sandbox; Webpack built successfully. No framework change was needed. PostgreSQL tools installed for earlier disposable tests remain in Conda but are no longer required by the manifest or current suite; local server fixtures were removed for the Neon-only decision. PDF-first parsing remains later work.

Current foundation decisions (module 4 supersedes module 3's environment split): each app owns immutable validated settings, with a fixed backend dotenv path and process variables taking precedence. `APP_ENV` is removed; `DOCS_ENABLED` controls docs consistently everywhere. CORS defaults to no origins; remote origins require HTTPS and loopback may use HTTP. `GET /health` is process liveness without external calls. Debug tracebacks remain disabled. Typed errors omit input/internal details, and documented Uvicorn commands disable URL access logging.

Catalog decisions: own only the `talent_insight` database schema plus the public `talent_insight_alembic_version` table. Do not adopt an unknown existing schema. Migrations/seeds are explicit commands, never app startup effects. Seed stable demo IDs atomically, preserving unrelated rows and avoiding automatic deletes. Source resumes and evidence offsets are retained only for synthetic demo records; no uploaded-candidate persistence is introduced.

## 4. Repository structure

Important files after module 9:

```text
AGENTS.md                   Stable development rules and review gates
PROJECT_CONTEXT.md          Architecture, state, roadmap and handoff
README.md                   Entry point and honest implementation status
.gitignore, .editorconfig    Secret/build exclusions and editing conventions
.nvmrc, .python-version      Node 24 and Python 3.12 runtime families
environment.yml             Single Conda environment: Python/Node/pip
run_local.sh                Conda-aware entry point for local server management
scripts/local_runner.py     Private PID/log records and verified process-group lifecycle
scripts/test_local_runner.py Offline launcher ownership/configuration tests
frontend/                   Next.js App Router shell, TS/Tailwind/ESLint config
  AGENTS.md                 Next.js-generated frontend guidance; read with root rules
  package.json              Commands and exact direct dependencies
  package-lock.json         Resolved npm dependency tree
  .env.example              Validated public FastAPI origin for browser catalog requests
  src/app/                  Overview, guide, jobs/list-detail routes, 404 and root styles
  src/components/           Shell/navigation, job/candidate views and request-state handling
  src/lib/catalog.ts        Typed job contracts, runtime decoding and bounded API fetch
  src/lib/candidates.ts     Candidate context/provenance decoding and Unicode source slicing
  src/lib/resumes.ts        Temporary PDF contracts, file checks and upload transport
  src/components/resume-upload.tsx Memory-only upload, errors, clear/cancel and page text
  tests/catalog.test.ts     Offline Node tests for API contracts and failures
  tests/candidates.test.ts  Offline candidate context, provenance and Unicode checks
  tests/resumes.test.ts     Offline upload contracts, privacy, errors and cancellation
backend/
  pyproject.toml            Installable app package, dependencies, pytest/Ruff config
  requirements-dev.lock     Exact runtime/build/test dependency versions
  .env.example              Docs/CORS settings and commented same-database URL examples
  app/main.py               ASGI entry point that validates settings at import
  app/application.py        Independent app factory, CORS and router composition
  app/config.py             Immutable Pydantic settings and safe startup failures
  app/errors.py             Typed JSON errors and sanitized ASGI error boundary
  app/api/health.py         Typed process liveness endpoint
  app/api/jobs.py           Read-only jobs list/detail schemas, routes and session dependency
  app/api/candidates.py     Job-scoped pool/profile schemas and source provenance validation
  app/api/resumes.py        Stateless raw PDF upload and effective-limits endpoints
  app/resumes.py            Typed temporary output and killable parser orchestration
  app/pdf_worker.py         Disposable strict pypdf extraction with resource limits
  app/api/extraction.py     Canonical catalog snapshots, structured routes and admission limits
  app/extraction_contracts.py Strict fact/source schemas and page/phrase provenance checks
  app/extraction.py         Explicit mock/Bedrock adapters, retries and killable worker lifecycle
  app/bedrock_worker.py     Isolated LangChain Converse call with no tracing/tool execution
  app/database.py           Validated Postgres URLs, bounded lazy engines, direct migrations
  app/models.py             Jobs, requirements, synthetic candidates and membership
  app/catalog.py            Read-only, job-scoped catalog queries
  app/seed.py               Validated, atomic repeatable demo seeding CLI
  app/fixtures/jobs/*.json   Four editable job definitions with 24 requirements
  app/fixtures/candidates.json Unchanged 12 candidates and 12 memberships
  alembic.ini, alembic/     Initial owned-schema migration and configuration
  tests/                    Foundation, evidence, URL, offline SQL and opt-in read-only Neon checks
docs/provider-research.md    Official sources, findings and open constraints
docs/local-development.md    Conda setup, run/check commands and limitations
docs/backend-foundation.md   Settings, HTTP/CORS/error contracts and limitations
docs/database.md             Verified Neon target, private configuration, schema/seed and checks
docs/frontend-layout.md      Implemented routes, accessibility behavior and browser checks
docs/jobs.md                 API contracts, JSON authoring and module 6 verification
docs/candidates.md           Membership, evidence/source behavior and module 7 verification
docs/resumes.md              Upload contracts, settings, privacy and parser limitations
docs/structured-extraction.md API, provider settings, evidence rules and module 9 limitations
```

Recommended future layout, to create only as each approved module needs it:

```text
frontend/                   Next.js app, components, typed API client, UI tests
backend/app/                API routers, schemas, services, models, config
backend/alembic/            Versioned database migrations
backend/tests/              Unit and API/integration tests with provider mocks
backend/fixtures/           Synthetic seed and evaluation records
docs/                       Setup, scoring, integration and deployment guidance
```

Do not create empty feature directories or placeholder endpoints for all future modules.

## 5. Implementation roadmap

These are review gates, not authorization to implement every row. Dependencies indicate implementation order; each module still requires user approval.

| # | Module | Status | Depends on | Reviewable result and checks |
| --- | --- | --- | --- | --- |
| 1 | Assessment, instructions and context | Completed | — | Repository/environment inventory, research, roadmap and documentation checks |
| 2 | Project setup and configuration | Completed | 1 + approval received | Minimal frontend/backend scaffolds, pinned dependencies, ignore rules, safe env examples, run instructions; lint/type/build/ASGI/lock checks passed |
| 3 | Backend foundation | Completed | 2 + approval received | App factory, validated dotenv/process settings, exact CORS, health and safe errors; 48 tests, lint/format/dependency and local startup checks passed |
| 4 | Database, migrations and seed data | Completed | 3 + approval received | Shared Neon initialized at `0001_demo_catalog`; four jobs, 24 requirements, 12 synthetic candidates and memberships; 66 tests including read-only Neon checks passed; repeat seed preserved counts |
| 5 | Frontend layout and navigation | Completed, reviewed and approved | 2 + approval received | Responsive shared shell, overview/guide navigation, keyboard skip/focus and 404 recovery; lint/type/build and manual browser checks passed |
| 6 | Jobs listing and details | Completed, reviewed and approved | 3–5 + approval received | Typed read-only API, job listing/details, per-job JSON, local launcher; 77 backend tests, six frontend tests, four launcher tests and browser state checks passed |
| 7 | Candidate pipeline and profiles | Completed, reviewed and approved | 6 + approval received | Read-only job-scoped pool/profile APIs, authored summaries, validated source evidence and highlighting; 99 backend/11 frontend tests and manual browser checks passed |
| 8 | Resume upload and PDF extraction | Completed, reviewed and approved | 7 + approval received | Anonymous bounded stateless PDF extraction, page text, temporary job-page UI and actionable errors; malformed/empty/scanned/encrypted/size/complexity/deadline/concurrency tests |
| 9 | Structured extraction with Bedrock | Completed; awaiting review | 8 + approval received | Canonical job/source schemas, explicit mock/Bedrock providers, strict schema/page/phrase validation, bounded retries/admission; SDK-mocked tests and one accepted synthetic live result |
| 10 | Matching and deterministic scoring | Pending | 9 | Per-requirement interpretation, documented weights/denominators/unknowns, deterministic rubric; evidence, boundary and synthetic evaluation tests |
| 11 | Evidence-backed assessment UI | Pending | 10 | Resume-to-job workflow, excerpts, coverage, gaps and follow-ups; temporary-state refresh and end-to-end checks |
| 12 | Voice configuration and token issuance | Pending | 11 + architecture review | Approve credential-safe design; authoritative job/candidate context, consent validation, expiry/replay rules, bounded token endpoint; mocked provider/security tests |
| 13 | Browser voice and text fallback | Pending | 12 | Consent modal, direct audio, live transcript, mute/end/error controls, interruption/disconnect handling; browser scenarios and approved live test |
| 14 | Structured screening reports | Pending | 13 | Validated report, explicit completion, idempotency, incomplete-session behavior; evidence/report schema/duplicate tests |
| 15 | Hardening and deployment readiness | Pending | 14 | End-to-end demo, abuse/cost controls, retention review, usage logging, Vercel/Render instructions, authorized integration verification |

Dependencies are installed when needed. Security and tests accompany each module; module 15 consolidates them. Split large modules into smaller review gates if needed. Phase 1 = modules 2–11, Phase 2 = modules 12–14, Phase 3 = module 15.

## 6. Current implementation state

- At inspection the repository contained only `.git`, no tracked application files, no commits, and no applicable ancestor `AGENTS.md`. Initial status: `main`, unborn branch, upstream displayed as gone. No remote repair attempted.
- No previous application code or CI existed to reuse. Module 1 created the development documentation; module 2 created the project scaffolds and tooling.
- Frontend: Next.js 16.4.3, React 19.3.1, TypeScript 5.9.3 and Tailwind 4.3.3. The shared shell/overview/guide/404 includes jobs at `/jobs` and `/jobs/<id>`, with module 7 pools/profiles at nested `/candidates` and `/candidates/<candidate_id>` routes. Static content remains in server components; job/candidate views fetch directly from FastAPI. Runtime decoders reject invalid/non-demo/context-mismatched data. Requests omit credentials/cache, reject redirects, time out at 20 seconds and abort on unmount. Loading, empty, unavailable/retry and missing-record states are distinct. No browser storage or mock fallback exists. No dependencies were added.
- Candidate UI: job details link to the actual synthetic pool; profiles show authored summaries, grouped experience/qualification/skill excerpts and complete source text. Source links focus the resume section and highlight exact ranges; selection is React memory only. Code-point slicing avoids JavaScript/Python offset differences with emoji. Text/HTML/instructions remain literal data. Missing excerpt categories use unknown-evidence wording; no ranking, stage controls, scores or recommendations are shown.
- Module 5 accessibility behavior: semantic navigation/header/main/footer, one h1 per page, a keyboard skip link that moves focus to main, visible focus outlines, 48-pixel navigation targets, reduced-motion support and an always-visible mobile navigation area. The 1024-pixel breakpoint switches between horizontal navigation and a sticky desktop sidebar. See [frontend layout](docs/frontend-layout.md) for scope and reproducible checks.
- Next.js automatically generated `frontend/AGENTS.md` during development startup. Preserve its framework guidance and read it in addition to root instructions for frontend work; it does not replace the module review gates.
- Backend: the existing FastAPI/Pydantic/Uvicorn/SQLAlchemy stack exposes GET `/jobs`, `/jobs/{job_id}`, `/jobs/{job_id}/candidates` and `/jobs/{job_id}/candidates/{candidate_id}`. Candidate lookups use actual membership joins and return safe 404 for cross-job/missing profiles. Detail validation checks the demo marker, stored profile shape, source display context, range bounds, quote equality and supporting labels before serialization. Corrupt stored provenance fails with a safe 500. Catalog failures return sanitized 503 and invalid IDs 422. `/health` stays typed no-store liveness; `DOCS_ENABLED` controls docs/schema, `/redoc` is disabled and `/` remains 404. Module 8 adds GET `/resumes/limits` and POST `/resumes/extract`. Module 9 adds POST `/jobs/{job_id}/resumes/structure` (raw PDF) and `/jobs/{job_id}/candidates/{candidate_id}/structure` (empty body), with canonical read-only context closed before provider work.
- Structured extraction: strict fact/evidence schemas reject extra fields, malformed/repaired JSON, invalid categories, invented values, ambiguous quotes, page mismatches, duplicate facts and invalid tool calls. Offsets are computed on exact source text using page-local Unicode code points. Model reasoning is discarded. A fact is a documented text mention, not proof of competence or semantic correctness. Source verification does not guarantee completeness, truth or immunity to injection; human review remains required. The mock provider extracts only literal job-skill mentions and leaves other categories unknown. No Bedrock failure becomes a mock success. The existing upload UI remains local PDF text review; structured assessment UI is still module 11.
- Provider runtime: `langchain-aws==1.9.0`, `boto3==1.43.118` and `botocore==1.43.118` plus their exact dependency closure are installed/pinned in the existing Conda environment, without changing earlier lock versions. Each paid attempt runs in a disposable process, with SDK retries disabled, an overall deadline and parent kill/reap on timeout/cancellation. Credentials are passed to the child environment only. No prompt cache or tracing is requested; LangSmith/LangChain tracing and the transitive LangSmith pytest plugin are disabled. Input/output/attempt/concurrency/minute limits are backend-owned; admission state stores counters/timestamps only, per process, and resets on restart. These are not distributed quotas or a monetary budget.
- PDF extraction: `pypdf==6.19.0` is the only new dependency, installed in the existing Conda environment and pinned in manifest/lock; editable backend metadata was refreshed. Raw request bytes are checked for MIME/signature and actual streaming size. Body-read and extraction deadlines, per-process admission, page/text limits and reduced decoded-stream/tree/form limits bound processing. The worker is killed/reaped on timeout/task cancellation; diagnostics/core dumps are disabled. Linux has an additional 512 MiB address-space cap (unverified here); macOS lacks that hard memory bound. No uploaded content is written to files, Neon, browser storage or routine logs. Errors distinguish size/page/text/complexity, malformed, encrypted, empty and no-text/scanned cases. Mixed PDFs may yield partial text; OCR and extraction accuracy guarantees are absent.
- Upload UI: each loaded job has a labeled PDF selector, effective limits, extract action, safe actionable errors, cancel/clear and page-numbered text rendered literally. Selected files are released after success. React memory clears on refresh, job navigation and Clear; pagehide/history restoration also discards data. Requests omit credentials/cache/redirects and abort on unmount, with a 95-second browser deadline covering the maximum configured upload/parse durations. A disconnected backend request may finish within its server deadline. No filename is transmitted in the raw upload contract, and no candidate/job association is stored.
- A lazy engine is created per app lifespan without connecting and disposed on shutdown. Jobs/candidate requests use `SET TRANSACTION READ ONLY` and a five-second local statement timeout; session close rolls back. Successes/errors remain no-store. Response models expose public job/candidate fields and validated synthetic source data, never internal scenario labels. Default API tests override data access and never connect.
- Job authoring: four job JSON files and `candidates.json` replace the combined fixture with identical values and stable IDs. `python -m app.seed --validate-only` validates files, names/IDs, question references, evidence and memberships without settings/database access. Tests verify an edited/added job needs no Python/UI changes or candidate pool. Package data includes nested job JSON; a built wheel was inspected. File edits are not automatically reflected in Neon, and removing a file does not prune database rows.
- Local launcher: `run_local.sh` activates the existing `talent-insight` Conda environment and invokes `scripts/local_runner.py`. It verifies runtimes/dependencies without installing, uses the documented Webpack/Uvicorn commands and loopback ports, checks liveness, and stores ignored mode-0600 records/logs under mode-0700 `.run_local/`. It verifies process start identity and a dedicated group before stopping children. Stale/unverifiable processes and unmanaged ports are left alone. It has no certificate/API-key/authentication behavior from the reference project.
- Backend foundation: environment/dotenv precedence, immutable per-app settings, exact origin CORS (GET/POST/Content-Type, no browser credentials), typed HTTP/validation errors and a sanitized unexpected-error boundary. CORS headers remain on allowed-origin errors. Invalid config fails before serving. Unexpected errors log class names, not exception messages or request bodies; interrupted streams terminate with a sanitized error. See [backend contract](docs/backend-foundation.md).
- Database code: four SQLAlchemy tables in `talent_insight`, revision `0001_demo_catalog`, schema constraints, explicit seeding CLI and read-only queries. The fixture has four technical roles, 24 categorized requirements and three synthetic candidates per role (12 total), with screening questions, exact quote offsets and varied evidence scenarios. No opaque match scores, uploaded records, transcripts or reports are persisted.
- Hosted database state: existing `talent-insight` / `<NEON_PROJECT_ID>`, branch `<NEON_BRANCH_ID>` (`production`), database `neondb`, PostgreSQL 18.6 in AWS us-east-2. Inspection found no app schema/tables before initialization and an existing public helper function, which was preserved. The approved migration and seed are applied; independent MCP reads confirm revision and exact counts. No new project/branch/database was created. Module 9 performed small synthetic Bedrock calls; no Deepgram calls, hosted deployment or commits were made. Matching/scoring/voice remain unimplemented. Uploads and structured results remain temporary and are not written to Neon.
- Created Conda environment `talent-insight` at `/opt/anaconda3/envs/talent-insight` on this machine. Verified Python 3.12.15, Node 24.13.0 and npm 11.6.2. A temporary `.venv` created before the user's Conda instruction was removed. Conda base and system Node were not modified.
- This shell's PATH prefers Homebrew Node 26 even after Conda activation. `export PATH="$CONDA_PREFIX/bin:$PATH"` selects the intended runtime. Frontend strict engines correctly rejected the first Node 26 install attempt; retry with Conda Node 24 succeeded.
- Neon credentials were obtained privately through the configured MCP connection and written to ignored `backend/.env` with mode `0600`; no credential values were printed. Shared AWS configuration files and account capabilities remain uninspected.
- Current module 4 verification on macOS arm64 in Conda: **66 tests passed with warnings treated as errors** using `python -m pytest --neon -W error`; three opt-in Neon tests verify revision/model parity, job membership and exact synthetic resume evidence inside read-only transactions. Default credential-free execution: **63 passed, 3 skipped**. Ruff lint/format and pip dependency checks passed. Offline SQL needs no credentials. Both pooled/runtime and direct/migration connections reach the same verified database, and `alembic current` / `alembic check` report head with no pending operations.
- Initial seed and a repeat on Neon both produced exactly four jobs, 24 requirements, 12 candidates and 12 memberships, independently confirmed through MCP. Every candidate is synthetic. Earlier 71-test PostgreSQL 17.9 verification included rollback, constraints and unrelated-data preservation; those disposable server fixtures were subsequently removed rather than directed at the shared Neon database. Destructive mutation/rollback tests are not run against Neon.
- New database packages were added in the dedicated Conda environment with prior dependency versions constrained; editable metadata and dependency/lock consistency were verified during module 4. Module 3's earlier Uvicorn startup checks remain historical evidence; its environment modes are removed. Neon is now verified; AI integration is not.
- Module 5 frontend verification: lint, route generation/TypeScript and Webpack production build passed in Conda. Manual checks of the production build verified overview/guide links, keyboard navigation, active labels, skip-link focus, direct reload/history, titles and 404 recovery. Both pages fit 320/375/768/1024/1280 CSS-pixel widths without horizontal scrolling; desktop/mobile screenshots were inspected. Browser warning/error logs were empty. The default backend suite passed 63 tests and skipped the three opt-in Neon checks. Backend code, configuration and shared Neon were unchanged; no external integration checks were repeated.
- Module 6 verification: 77 backend tests passed with warnings treated as errors; three opt-in Neon tests skipped. Ruff lint/format, pip dependency checks, offline seed validation, JSON value preservation and packaged fixture checks passed. Six Node API-client tests, frontend lint/typecheck and Webpack production build passed. Four launcher unit tests/Bash syntax passed; actual start, duplicate start, stop, restart/status/log following and preservation of unmanaged test servers were checked. Normal browser reads loaded the four existing Neon jobs and Data Scientist details. Production-browser edge cases used a temporary mock API without database configuration; loading, empty/error, keyboard retry/recovery, request cancellation/navigation and missing-job recovery passed. Listing/details fit 320/375/768/1024/1280 CSS-pixel widths. No migration, seed, provider call, infrastructure change, deployment or commit ran.
- Module 7 verification: 99 backend tests passed with warnings treated as errors; three opt-in Neon checks skipped. Tests validate all twelve fixture profiles/four pools, membership filters, cross-job/missing/invalid IDs, empty pools, provenance corruption/redaction and Unicode/empty evidence. Eleven Node tests, frontend lint/typecheck/build and backend lint/format/dependency checks passed. Real local application reads loaded the Data Scientist pool and Avery Chen profile from Neon. Production-browser edge cases used a temporary mock API without database configuration: loading, empty/error, keyboard retry/recovery, navigation away, cross-job recovery, empty evidence, highlighting/focus/clearing and inert HTML/instruction rendering. Pool/profile reflow passed at 320/375/768/1024/1280 CSS pixels. No fixture edits, migrations, seeds, dependencies, provider calls, infrastructure changes, deployment or commits were introduced.
- Module 8 verification: 130 backend tests passed/three Neon checks skipped; seventeen frontend tests, lint/type/build, backend checks and four launcher tests passed. Synthetic PDF cases and manual development-browser success/scanned/error/clear/refresh/history checks passed, including 320–1280 CSS-pixel reflow. No AI/voice calls, shared-database mutations, migrations, seeds or deployment ran in module 8. The user approved module 8. Linux hard memory enforcement and real-resume extraction accuracy remain unverified.
- Module 9 verification: 195 backend tests passed/three opt-in Neon checks skipped; seventeen frontend tests and frontend lint/typecheck passed. Backend lint/format/dependency/lock checks, offline seed validation and four launcher tests/Bash syntax passed. SDK Stubber tests exercise actual native JSON/tool serialization and strict raw-output validation; source tests cover all twelve synthetic mock profiles, Unicode/ambiguous quotes, unknowns, injection-shaped invalid fields, retry/failure handling, deadlines and actual child cancellation cleanup. API tests check membership/corruption, canonical context, closed transactions, PDF/JSON boundaries, safe CORS/no-store errors and admission/rate limits. Running local health and OpenAPI returned 200 and included both new routes, without database/provider calls. Six small synthetic-only Bedrock checks culminated in two source-verified facts using the saved native JSON method plus explicit schema instructions. See provider research for failed exploratory checks; no success-rate claim. No real resume, shared-database check/write, migration, seed, infrastructure change, deployment or commit ran. Frontend presentation was unchanged in module 9; production build/browser UI checks were not repeated (module 8 evidence remains historical).
- Module 2's npm install audit reported zero vulnerabilities at installation time; it is historical and not a full security review. No automated browser suite, screen-reader audit, other-browser verification, Linux build, Vercel/Render deployment or live voice verification has occurred. Live AI verification is limited to module 9's synthetic checks.
- Documentation links/structure, Git whitespace and secret/build ignore rules verified. No unrelated files introduced.

## 7. Environment and configuration

Examples contain no secrets. See [local setup](docs/local-development.md), [backend contract](docs/backend-foundation.md), [PDF extraction](docs/resumes.md), [structured extraction](docs/structured-extraction.md) and [database setup](docs/database.md). The backend validates docs/CORS, PDF/AI limits, provider selection and optional same-database URLs from process variables or fixed `backend/.env`, with process precedence and unknown dotenv keys rejected. There are no application environment modes. Both database URLs and the user-provided Bedrock token remain private; selected region/model/method and explicit Bedrock mode are saved alongside them with mode 0600. Health/startup/plain PDF extraction make no database or provider call. Structured routes first read canonical catalog context; only explicit Bedrock extraction calls inference. Deepgram/session variables remain future contracts. Do not request secrets in chat.

| Name | Owner | Purpose / handling |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | Frontend / Vercel | Implemented validated FastAPI origin; absent value defaults to `http://127.0.0.1:8000`; supply before production build |
| `DOCS_ENABLED` | Backend | Implemented: boolean, defaults true; explicitly controls docs without mode-specific behavior |
| `CORS_ALLOWED_ORIGINS` | Backend | Implemented: defaults `[]`; exact HTTPS remote origins or HTTP loopback, no wildcards/paths/credentials |
| `DATABASE_URL` | Backend | Configured redacted pooled runtime URL for existing `talent-insight`; remote TLS required |
| `DIRECT_DATABASE_URL` | Backend migration command | Implemented optional direct URL for the same database; rejects pooled hosts; no environment separation |
| `RESUME_MAX_BYTES` | Backend | Implemented upload cap; default 5,242,880 bytes, allowed 1,024–10,485,760 |
| `RESUME_MAX_PAGES` | Backend | Implemented PDF page cap; default 20, allowed 1–50 |
| `RESUME_MAX_CHARACTERS` | Backend | Implemented extracted Unicode character cap; default 100,000, allowed 100–200,000 |
| `RESUME_UPLOAD_TIMEOUT_SECONDS` | Backend | Implemented full body-read deadline; default 15, allowed 0.1–60 |
| `RESUME_TIMEOUT_SECONDS` | Backend | Implemented disposable-parser deadline; default 10, allowed 0.1–30 |
| `RESUME_MAX_CONCURRENT` | Backend | Implemented upload/parser admissions per API process; default 2, allowed 1–4; no queue |
| `AI_MODE` | Backend | Implemented explicit `mock` or `bedrock`; absent disables structured extraction. Local saved value is `bedrock`; no silent fallback |
| `AWS_REGION` | Backend | Implemented, no default; user selected and verified `ap-southeast-2` |
| `BEDROCK_MODEL_ID` | Backend | Implemented, no default; selected and verified `openai.gpt-oss-120b-1:0` |
| `AWS_BEARER_TOKEN_BEDROCK` | Backend only | Implemented SecretStr; user-provided private token loaded from ignored dotenv and passed only to the worker environment |
| `BEDROCK_STRUCTURED_METHOD` | Backend | Implemented `json_schema` (default and saved selection) or explicit `function_calling`; no automatic switching |
| `AI_MAX_INPUT_CHARACTERS` | Backend | Implemented job-context JSON plus source-text limit; default 20,000, allowed 100–50,000; no truncation |
| `AI_MAX_OUTPUT_TOKENS` | Backend | Implemented per-attempt cap; default 3,000, allowed 256–8,192 |
| `AI_TIMEOUT_SECONDS` | Backend | Implemented total provider-attempt deadline; default 45, allowed 5–120 |
| `AI_MAX_ATTEMPTS` | Backend | Implemented, default 2, allowed 1–2; one SDK attempt each |
| `AI_MAX_CONCURRENT` | Backend | Implemented, default 1, allowed 1–2 per API process; no queue |
| `AI_REQUESTS_PER_MINUTE` | Backend | Implemented rolling per-process admission count; default 5, allowed 1–20; timestamps only |
| `AWS_PROFILE` | Backend / local only | Optional local AWS profile via SDK credential chain |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | Backend only | Standard AWS SDK credentials where necessary; prefer temporary/role-based access; never browser settings |
| `DEEPGRAM_API_KEY` | Backend / Render | Permanent key used only server-side to issue temporary tokens |
| `SESSION_SIGNING_SECRET` | Backend, proposed for voice | If signed temporary context/session capabilities are selected; exact mechanism pending module 12 |

PDF/AI limits are implemented above; the frontend loads PDF limits from GET `/resumes/limits` but does not yet call structured extraction. Provider mode/credentials are server-owned. Scoring weights, distributed/public usage controls and session expiry remain future work. No storage credentials are required. CORS and per-process admission are not authentication or a substitute for a public monetary budget.

To resume tooling on this machine, use the existing environment rather than recreating it:

```sh
cd /Users/darshil/Darshil/Projects/talent-insight
source /opt/anaconda3/etc/profile.d/conda.sh
conda activate talent-insight
export PATH="$CONDA_PREFIX/bin:$PATH"
```

Use root `./run_local.sh start|stop|status|restart|logs` for both apps. `BACKEND_PORT`/`FRONTEND_PORT` default to 8000/3000; local API/CORS process defaults follow them, without editing dotenv. Run frontend checks from `frontend/` (`npm run lint`, `npm run typecheck`, `npm test`, `npm run build`) and backend checks from `backend/` (`python -m pytest -W error`, `python -m ruff check .`, `python -m ruff format --check .`, `python -m app.seed --validate-only`). Root launcher tests: `python -m unittest discover -s scripts -p 'test_*.py'`. `python -m pytest --neon -W error` explicitly opts into the three read-only shared-database checks. Existing dependencies are installed; direct run commands and boundaries are in [local development](docs/local-development.md).

## 8. Important technical details

- Current HTTP contracts: `/health` is liveness only; application errors are `{"error":{"code":"...","message":"..."}}` with preserved status and no-store caching. Raw HTTP exception details and Pydantic validation inputs are not echoed. Trusted `Allow`/`Retry-After` headers are preserved. Denied CORS preflights use Starlette's plain-text HTTP 400 protocol response. Add deliberately safe typed domain errors when recruiting features need actionable messages.
- Current settings contract: fixed dotenv path, explicit init > process > dotenv > defaults; `DOCS_ENABLED` is independent of location. No origins means no cross-origin browser access. CORS permits GET/POST/Content-Type; module 8 added POST for raw PDF uploads. Errors remain inside CORS. Startup/lifespan failures are not hidden behind HTTP success.
- Database contract: runtime SQLAlchemy pool is bounded at five, zero overflow, pre-ping, hidden SQL parameters, ten-second connect timeout and prepared statements disabled. Alembic uses a direct endpoint/NullPool; offline SQL needs no URL. Migration version state is in public `talent_insight_alembic_version`; models and catalog are in `talent_insight`. Schema/model parity is verified against Neon by `alembic check` and the read-only integration test.
- Seed contract: Pydantic validates fixture IDs, associations, question references, demo markers and claim excerpts before writes. Each quote's start/end offsets address the original synthetic resume. All batches upsert in one transaction. Non-fixture rows are preserved; no pruning/truncation/deletion. Removed fixtures or criterion-order restructuring require a deliberate data migration. Scenario labels are synthetic test metadata, not scores or recommendations.
- Planned assessment: criterion ID/category/status, rationale, original text excerpt and source/page or character offsets, follow-up; deterministic category/overall scores and evidence coverage. Allowed statuses: meets, partial, evidence not found, requires verification, unable to assess. Define unknown/no-criterion behavior explicitly; never turn an unavailable assessment into a confident zero or perfect match.
- Uploaded profiles must never be trusted as authoritative client JSON. Module 8 can process statelessly; later session creation needs server-validated short-lived context or bounded expiring server state. Choose the mechanism in module 12 without introducing a new service unnecessarily.
- Reports contain job/candidate IDs, questions, candidate statements, criterion evidence, unresolved requirements, technical observations, human follow-ups, summary and suggested next step. Backend recalculates important outputs; clients cannot supply trusted scores or recommendations.
- Validate upload bytes, size, type and parser behavior server-side. Bound page/text counts and processing time; reject encrypted, malformed, empty or scanned PDFs clearly. Do not invent missing text or add OCR implicitly.
- Keep personal data out of routine logs, error traces, caches and permanent tables. Use no-store responses for temporary payloads. Explain that application non-persistence does not itself establish third-party retention behavior.
- Screenings disclose AI involvement, ask one job-related question at a time, use consistent core questions with limited follow-ups, handle silence/clarification, allow interruption where supported and finish explicitly. Unsupported questions do not change instructions.
- Tests accumulate with modules: parser fixtures; schema/provenance validation; deterministic unknown-evidence scoring; data access; temporary-state clearing; upload errors; session context/expiry/idempotency; report validation; bounded retries and privacy-safe errors.
- Evaluation uses synthetic strong/partial/weak/ambiguous/incomplete profiles. Voice scenarios include relevant/irrelevant/incomplete answers, clarification, contradiction, unclear audio, interruption, instruction override, unrelated requests and early termination. No evaluation results exist yet.

## 9. Known issues and unresolved decisions

1. **Voice credential design:** documented native Deepgram Bedrock settings contain IAM/STS credentials. Browser-visible settings violate the agreed no-AWS-keys rule. Investigate server-managed secret configuration; a custom FastAPI reasoning endpoint is a documented-protocol fallback proposal, not an approved or tested integration. It keeps audio direct but adds latency, protocol handling and abuse-control work. Resolve before module 12, not before the resume milestone.
2. **Provider access:** Neon is verified. The user's selected Sydney `openai.gpt-oss-120b-1:0` model accepted a small source-validated native-JSON extraction after explicit schema prompting. This does not establish provider-native enforcement, real-resume accuracy, stable reliability or account retention policy. Tool-output experiments returned no accepted result. Deepgram permissions and deployment origins remain unverified. Hosted secrets must use the same Neon URLs and backend-only provider credentials when deployment is authorized.
3. **Local runtime selection:** Python availability is resolved through the dedicated Conda environment. Always activate `talent-insight` and prepend its bin directory on this machine, because shell PATH ordering otherwise selects Homebrew Node 26. Required project runtime families are Python 3.12 and Node 24.
4. **Scoring semantics:** exact partial credits, denominator behavior, category normalization and unknown-evidence handling are pending module 10. Document and test before exposing scores; weights are not validated hiring science.
5. **Untrusted client and usage controls:** CORS and a short-lived token cannot guarantee trusted settings, transcript authenticity or a maximum open voice session. Design server-enforceable cost limits before public voice. In-memory state/quotas require an explicit single-process limitation or later shared enforcement.
6. **Resume parsing and third-party privacy:** module 8 clearly rejects documents with no extractable text, including scans. Mixed PDFs may yield partial text, and strict parsing may reject repairable documents. Only synthetic PDFs are tested; real-document accuracy and future provider retention need review. macOS has no hard per-worker address-space cap; the Linux cap remains unverified. No claim of legal compliance.
7. **Deployment and platform verification:** Vercel Node 24 and Render's configurable Python versions were checked in official docs. Local production compilation is verified; neither hosted application deployment nor Linux dependency installation is verified. Neon setup is complete, but no frontend/backend deployment configuration exists yet. Backend lock currently includes development tools; production dependency packaging remains deployment-readiness work.
8. **Tooling compatibility:** ESLint 9.39.5 is deprecated upstream but is the latest 9.x version compatible with the installed Next.js React/accessibility plugins' declared peers. Keep it pinned until those plugins support ESLint 10; do not force unsupported peers. HTTPX's ASGI transport is used directly for the smoke test, avoiding Starlette's deprecated HTTPX TestClient path. Turbopack is not verified here; use the documented Webpack scripts.
9. **Foundation boundaries:** health does not verify provider/database readiness. PDF and AI input/output/time/attempt/concurrency limits plus per-process extraction admission counts are implemented; distributed budgets, public abuse controls and voice-session limits remain pending. Restart resets counters and multiple API processes multiply capacity. CORS does not authenticate callers. Swagger's default UI uses external CDN assets; `/openapi.json` and health do not need them. Non-editable deployments should use process settings rather than the source-tree dotenv path.

## 10. Last completed milestone and next action

**Last completed module:** 9 — structured extraction with Bedrock, using the existing `talent-insight` Conda environment (Python 3.12.15 / Node 24.13.0). Modules 1–9 are complete. The user confirmed on 2026-10-24 that modules 5, 6, 7 and 8 are all reviewed and approved. Module 9 awaits completion review. Modules 10–15 remain pending and unauthorized.

**Module 9 result:** backend-only POST `/jobs/{job_id}/resumes/structure` for raw PDFs and `/jobs/{job_id}/candidates/{candidate_id}/structure` for actual synthetic members. The server snapshots canonical job/source context and closes its read-only transaction before provider processing. Explicit mock/Bedrock selection, strict schemas, bounded worker calls, at most one service retry, size/token/deadline/admission limits, literal quotes and computed page-local Unicode offsets are implemented. Unsupported/invalid output fails safely without fallback. Results are temporary and no-store; no uploaded data, profiles or outputs enter Neon, browser storage, application files or routine logs. No matching, scoring, inferred experience totals, recommendation, voice or assessment UI was added.

**Saved private configuration:** `AI_MODE=bedrock`, `AWS_REGION=ap-southeast-2`, `BEDROCK_MODEL_ID=openai.gpt-oss-120b-1:0`, `BEDROCK_STRUCTURED_METHOD=json_schema`. The user-provided bearer token and both existing Neon URLs were preserved without displaying values; `backend/.env` is ignored and mode 0600. The full output schema is also stated in the system prompt. LangSmith/LangChain tracing and the transitive pytest tracing plugin are disabled. Health/catalog/plain PDF extraction do not call Bedrock. Only the new explicit structured POSTs consume inference.

**Verification performed:** 195 backend tests passed with warnings treated as errors; three opt-in Neon checks skipped. Seventeen frontend tests, frontend lint/typecheck, backend lint/format/dependency/lock checks, offline seed validation, four launcher tests/Bash syntax, Git whitespace and local documentation-link checks passed. The real LangChain/SDK serializer was exercised with AWS Stubber, including native/tool payloads, raw-output validation and safe errors. Tests cover all twelve synthetic mock profiles, Unicode/ambiguous evidence, unknowns, invalid/injection-shaped output, server-owned job/source context, membership/corruption, PDF/JSON boundaries, retries, actual service deadline/child cleanup, CORS/no-store and admission recovery. Running `/health` and `/openapi.json` returned 200 with both structured routes present, without Neon/provider calls. Frontend presentation was unchanged in module 9; production build and browser UI checks were not repeated (module 8 checks remain historical).

**External verification and limitations:** six small synthetic-only Converse checks, each with a 2,048-output-token cap, one SDK attempt and no service retry. Initial native outputs failed validation and tool-output experiments returned no accepted result. The final native request, with explicit schema prompting, returned two facts that passed strict schema and source verification. This confirms limited account/model/region access, not a success rate, semantic accuracy, completeness or provider-enforced schema guarantees. No real resume/transcript, AWS retention/invocation-logging setting, Linux runtime or hosted deployment was tested. Per-process limits reset on restart and are not a distributed spend budget. Linux worker memory limits remain unverified; macOS lacks a hard address-space cap. No database check/write, migration, seed, IAM/infrastructure change, deployment or commit ran.

**Current blocker:** none for the completed local module 9 result; stopped for user review. The assessment UI remains module 11. Shared Neon data/credentials are preserved, and JSON edits still require an explicitly approved seed. Future real-document use needs provider privacy/retention review and broader extraction evaluation.

**Exact next task after module 9 review and explicit approval:** module 10 — matching and deterministic scoring. Read instructions/context, extraction contracts, canonical job requirements, existing source evidence and synthetic cases. Explain purpose/dependencies/files and specify exact per-requirement statuses, partial-credit rules, unknown-evidence handling, category denominators/normalization and no-criterion behavior before coding. Keep model interpretation distinct from verified source evidence and deterministic calculation; do not turn unavailable assessment into a confident zero or perfect score. Treat the proposed 50% mandatory / 25% experience / 15% preferred / 10% qualification weights as configurable and unvalidated. Add offline boundary/unknown/provenance/repeatability and synthetic scenario tests, preserving temporary data and human decisions. No voice, deployment, permanent uploads, migrations or unapproved paid evaluation. Stop for review after module 10; it is not authorized by completion of module 9.
