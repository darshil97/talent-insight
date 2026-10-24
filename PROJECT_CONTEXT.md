# Talent Insight — project context

Last updated: 2026-10-24 (Asia/Kolkata). Modules 1–4 are complete. The shared Neon catalog is initialized and verified. Module 5 awaits review and approval. Read `AGENTS.md` first.

## 1. Project overview

Build a focused AI recruiting assistant for technical recruiters, staffing firms and small agencies, suitable for a portfolio demonstration and later client adaptation.

Core workflow: **select job → review candidates → upload resume → inspect job match and evidence → optional browser screening → review report → human decision**.

MVP: a curated set of Data Scientist, ML Engineer, AI/LLM Engineer and Backend Engineer jobs; a fixed pool of clearly synthetic candidates per job; anonymous PDF upload; transparent requirement matching; temporary results; later voice screening with text fallback and structured reports. Profiles should include strong, partial, weak, transferable, ambiguous and incomplete evidence.

Non-goals: complete ATS, public job creation, admin UI, login, outbound calls, automated hiring decisions, permanent uploaded-candidate records, vector database, Redis or multi-agent orchestration. DOCX and object storage are optional later work.

First functional milestone spans modules 2–11: local run instructions, seeded jobs/candidates, PDF upload/extraction, structured parsing, deterministic matching, evidence views and tests. Completing module 1 alone does not satisfy that milestone.

## 2. Architecture and technology stack

Agreed stack (frontend/backend installed and Neon catalog verified; AI integrations and application deployment pending):

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

Important files during module 4:

```text
AGENTS.md                   Stable development rules and review gates
PROJECT_CONTEXT.md          Architecture, state, roadmap and handoff
README.md                   Entry point and honest implementation status
.gitignore, .editorconfig    Secret/build exclusions and editing conventions
.nvmrc, .python-version      Node 24 and Python 3.12 runtime families
environment.yml             Single Conda environment: Python/Node/pip
frontend/                   Next.js App Router starter, TS/Tailwind/ESLint config
  AGENTS.md                 Next.js-generated frontend guidance; read with root rules
  package.json              Commands and exact direct dependencies
  package-lock.json         Resolved npm dependency tree
  .env.example              Public API base URL example; not consumed yet
  src/app/                  Starter page, root layout and global styles
backend/
  pyproject.toml            Installable app package, dependencies, pytest/Ruff config
  requirements-dev.lock     Exact runtime/build/test dependency versions
  .env.example              Docs/CORS settings and commented same-database URL examples
  app/main.py               ASGI entry point that validates settings at import
  app/application.py        Independent app factory, CORS and router composition
  app/config.py             Immutable Pydantic settings and safe startup failures
  app/errors.py             Typed JSON errors and sanitized ASGI error boundary
  app/api/health.py         Typed process liveness endpoint
  app/database.py           Validated Postgres URLs, bounded lazy engines, direct migrations
  app/models.py             Jobs, requirements, synthetic candidates and membership
  app/catalog.py            Read-only, job-scoped catalog queries
  app/seed.py               Validated, atomic repeatable demo seeding CLI
  app/fixtures/catalog.json Four jobs, 24 requirements, 12 candidates and memberships
  alembic.ini, alembic/     Initial owned-schema migration and configuration
  tests/                    Foundation, evidence, URL, offline SQL and opt-in read-only Neon checks
docs/provider-research.md    Official sources, findings and open constraints
docs/local-development.md    Conda setup, run/check commands and limitations
docs/backend-foundation.md   Settings, HTTP/CORS/error contracts and limitations
docs/database.md             Verified Neon target, private configuration, schema/seed and checks
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
| 5 | Frontend layout and navigation | Pending | 2 | Accessible responsive shell and navigation; build/type/lint and navigation checks |
| 6 | Jobs listing and details | Pending | 3–5 | Read-only backend contracts and frontend job views; API and loading/empty/error checks |
| 7 | Candidate pipeline and profiles | Pending | 6 | Curated candidates per job, profile evidence, synthetic labels; relationship and UI checks |
| 8 | Resume upload and PDF extraction | Pending | 7 | Anonymous bounded upload, content validation, text extraction and temporary frontend state; malformed/empty/scanned/oversized tests |
| 9 | Structured extraction with Bedrock | Pending | 8 | Job/candidate schemas, provider adapter, explicit mock mode, Pydantic validation and provenance; mocked extraction/retry/injection tests |
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
- Frontend: Next.js 16.4.3, React 19.3.1, TypeScript 5.9.3 and Tailwind 4.3.3. `/` renders a static, responsive introduction that clearly states future features are unavailable. System fonts avoid build-time font downloads. No navigation shell, API client, recruiting features or browser persistence exists yet.
- Next.js automatically generated `frontend/AGENTS.md` during development startup. Preserve its framework guidance and read it in addition to root instructions for frontend work; it does not replace the module review gates.
- Backend: installable `talent-insight-backend` with the existing FastAPI/Pydantic/Uvicorn stack plus SQLAlchemy 2.0.55, Alembic 1.20.1 and psycopg 3.3.6. `app.main:app` and the factory validate settings. `/health` returns typed no-store HTTP 200 `{"status":"ok"}`. `DOCS_ENABLED` now controls `/docs` and `/openapi.json`; `/redoc` is disabled. `/` and `/jobs` remain structured 404s. No recruiting endpoints yet.
- Backend foundation: environment/dotenv precedence, immutable per-app settings, exact origin CORS (GET/Content-Type, no browser credentials), typed HTTP/validation errors and a sanitized unexpected-error boundary. CORS headers remain on allowed-origin errors. Invalid config fails before serving. Unexpected errors log class names, not exception messages or request bodies; interrupted streams terminate with a sanitized error. See [backend contract](docs/backend-foundation.md).
- Database code: four SQLAlchemy tables in `talent_insight`, revision `0001_demo_catalog`, schema constraints, explicit seeding CLI and read-only queries. The fixture has four technical roles, 24 categorized requirements and three synthetic candidates per role (12 total), with screening questions, exact quote offsets and varied evidence scenarios. No opaque match scores, uploaded records, transcripts or reports are persisted.
- Hosted database state: existing `talent-insight` / `<NEON_PROJECT_ID>`, branch `<NEON_BRANCH_ID>` (`production`), database `neondb`, PostgreSQL 18.6 in AWS us-east-2. Inspection found no app schema/tables before initialization and an existing public helper function, which was preserved. The approved migration and seed are applied; independent MCP reads confirm revision and exact counts. No new project/branch/database was created. No Bedrock/Deepgram calls, frontend/backend deployment or commits made. Upload/scoring/AI/voice functionality remains unimplemented.
- Created Conda environment `talent-insight` at `/opt/anaconda3/envs/talent-insight` on this machine. Verified Python 3.12.15, Node 24.13.0 and npm 11.6.2. A temporary `.venv` created before the user's Conda instruction was removed. Conda base and system Node were not modified.
- This shell's PATH prefers Homebrew Node 26 even after Conda activation. `export PATH="$CONDA_PREFIX/bin:$PATH"` selects the intended runtime. Frontend strict engines correctly rejected the first Node 26 install attempt; retry with Conda Node 24 succeeded.
- Neon credentials were obtained privately through the configured MCP connection and written to ignored `backend/.env` with mode `0600`; no credential values were printed. Shared AWS configuration files and account capabilities remain uninspected.
- Current module 4 verification on macOS arm64 in Conda: **66 tests passed with warnings treated as errors** using `python -m pytest --neon -W error`; three opt-in Neon tests verify revision/model parity, job membership and exact synthetic resume evidence inside read-only transactions. Default credential-free execution: **63 passed, 3 skipped**. Ruff lint/format and pip dependency checks passed. Offline SQL needs no credentials. Both pooled/runtime and direct/migration connections reach the same verified database, and `alembic current` / `alembic check` report head with no pending operations.
- Initial seed and a repeat on Neon both produced exactly four jobs, 24 requirements, 12 candidates and 12 memberships, independently confirmed through MCP. Every candidate is synthetic. Earlier 71-test PostgreSQL 17.9 verification included rollback, constraints and unrelated-data preservation; those disposable server fixtures were subsequently removed rather than directed at the shared Neon database. Destructive mutation/rollback tests are not run against Neon.
- New database packages were added in the dedicated Conda environment with prior dependency versions constrained; editable metadata and dependency/lock consistency were verified during module 4. Module 3's earlier Uvicorn startup checks remain historical evidence; its environment modes are removed. Neon is now verified; AI integration is not.
- Previous module 2 verification remains valid for the unchanged frontend: lint, route generation/TypeScript, Webpack production build and local development/production HTTP/CSS checks passed then. npm install audit reported zero vulnerabilities at that installation time; this is not a full security review. Frontend checks were not repeated in modules 3–4 because no frontend files changed. No automated real-browser/accessibility test, Linux build, Vercel/Render deployment or live AI/voice verification has occurred.
- Documentation links/structure, Git whitespace and secret/build ignore rules verified. No unrelated files introduced.

## 7. Environment and configuration

Examples contain no secrets. See [local setup](docs/local-development.md), [backend contract](docs/backend-foundation.md) and [database setup](docs/database.md). The frontend API URL remains unused. The backend validates docs, CORS and optional same-database connection URLs from process variables or fixed `backend/.env`, with process precedence and unknown dotenv keys rejected. Remove legacy `APP_ENV`; there are no environment modes. Both URLs are privately configured in the ignored local file; hosted backend secret settings must use the same values at deployment. Health/startup do not connect to the database. Other provider variables below remain future contracts. Do not request secrets in chat.

| Name | Owner | Purpose / handling |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | Frontend / Vercel | Public FastAPI base URL; the only proposed browser-public application setting |
| `DOCS_ENABLED` | Backend | Implemented: boolean, defaults true; explicitly controls docs without mode-specific behavior |
| `CORS_ALLOWED_ORIGINS` | Backend | Implemented: defaults `[]`; exact HTTPS remote origins or HTTP loopback, no wildcards/paths/credentials |
| `DATABASE_URL` | Backend | Configured redacted pooled runtime URL for existing `talent-insight`; remote TLS required |
| `DIRECT_DATABASE_URL` | Backend migration command | Implemented optional direct URL for the same database; rejects pooled hosts; no environment separation |
| `AI_MODE` | Backend | Explicit `mock` or `bedrock`; label mock outputs and prohibit silent fallback |
| `AWS_REGION` | Backend | Bedrock region; verify model access here |
| `BEDROCK_MODEL_ID` | Backend | Verified model or inference profile identifier; no arbitrary default |
| `AWS_PROFILE` | Backend / local only | Optional local AWS profile via SDK credential chain |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | Backend only | Standard AWS SDK credentials where necessary; prefer temporary/role-based access; never browser settings |
| `DEEPGRAM_API_KEY` | Backend / Render | Permanent key used only server-side to issue temporary tokens |
| `SESSION_SIGNING_SECRET` | Backend, proposed for voice | If signed temporary context/session capabilities are selected; exact mechanism pending module 12 |

File/page/text limits, provider timeouts/retries/token caps, scoring weights, request/concurrency quotas and session expiry must be backend-owned validated settings when the corresponding module is implemented. Names/defaults remain pending. No storage credentials required. CORS is not authentication or a substitute for rate/cost limits.

To resume tooling on this machine, use the existing environment rather than recreating it:

```sh
cd /Users/darshil/Darshil/Projects/talent-insight
source /opt/anaconda3/etc/profile.d/conda.sh
conda activate talent-insight
export PATH="$CONDA_PREFIX/bin:$PATH"
```

Run frontend commands from `frontend/` (`npm run dev`, `npm run lint`, `npm run typecheck`, `npm run build`). Run backend commands from `backend/` (`python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log`, `python -m pytest -W error`, `python -m ruff check .`, `python -m ruff format --check .`). `python -m pytest --neon -W error` explicitly opts into the three read-only shared-database checks. The environment and dependencies are already installed on this machine; detailed setup and command boundaries are in [local development](docs/local-development.md).

## 8. Important technical details

- Current HTTP contracts: `/health` is liveness only; application errors are `{"error":{"code":"...","message":"..."}}` with preserved status and no-store caching. Raw HTTP exception details and Pydantic validation inputs are not echoed. Trusted `Allow`/`Retry-After` headers are preserved. Denied CORS preflights use Starlette's plain-text HTTP 400 protocol response. Add deliberately safe typed domain errors when recruiting features need actionable messages.
- Current settings contract: fixed dotenv path, explicit init > process > dotenv > defaults; `DOCS_ENABLED` is independent of location. No origins means no cross-origin browser access. CORS permits GET/Content-Type only; extend explicit methods/headers with future POST features. Errors remain inside CORS. Startup/lifespan failures are not hidden behind HTTP success.
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
2. **Provider access:** Neon access and catalog initialization are verified; the credential-lock blocker is resolved. AWS model access, Deepgram permissions and deployment origins remain unverified. Hosted backend secrets still need the same Neon URLs when the application is deployed.
3. **Local runtime selection:** Python availability is resolved through the dedicated Conda environment. Always activate `talent-insight` and prepend its bin directory on this machine, because shell PATH ordering otherwise selects Homebrew Node 26. Required project runtime families are Python 3.12 and Node 24.
4. **Scoring semantics:** exact partial credits, denominator behavior, category normalization and unknown-evidence handling are pending module 10. Document and test before exposing scores; weights are not validated hiring science.
5. **Untrusted client and usage controls:** CORS and a short-lived token cannot guarantee trusted settings, transcript authenticity or a maximum open voice session. Design server-enforceable cost limits before public voice. In-memory state/quotas require an explicit single-process limitation or later shared enforcement.
6. **Resume parsing and third-party privacy:** scanned PDFs need clear rejection initially; real document fixtures and provider data/retention settings need review. No claim of legal compliance.
7. **Deployment and platform verification:** Vercel Node 24 and Render's configurable Python versions were checked in official docs. Local production compilation is verified; neither hosted application deployment nor Linux dependency installation is verified. Neon setup is complete, but no frontend/backend deployment configuration exists yet. Backend lock currently includes development tools; production dependency packaging remains deployment-readiness work.
8. **Tooling compatibility:** ESLint 9.39.5 is deprecated upstream but is the latest 9.x version compatible with the installed Next.js React/accessibility plugins' declared peers. Keep it pinned until those plugins support ESLint 10; do not force unsupported peers. HTTPX's ASGI transport is used directly for the smoke test, avoiding Starlette's deprecated HTTPX TestClient path. Turbopack is not verified here; use the documented Webpack scripts.
9. **Foundation boundaries:** health does not verify provider/database readiness; no request quotas or upload/session limits exist before their corresponding features. CORS does not authenticate callers. Swagger's default UI uses external CDN assets; `/openapi.json` and health do not need them. Non-editable package deployments should use process settings instead of relying on the source-tree dotenv path.

## 10. Last completed milestone and next action

**Last completed module:** 4 — database, migrations and synthetic seed data, using the dedicated `talent-insight` Conda environment and the existing shared Neon database.

**Module 4 result:** revision `0001_demo_catalog` is applied on `talent-insight` / `neondb`; four jobs, 24 requirements, 12 synthetic candidates and 12 memberships are initialized. Repeated seeding preserved those counts. Local and hosted runs use the same database; there are no application environment modes, new Neon branches or local PostgreSQL servers.

**Verification performed:** 66 tests passed with warnings treated as errors including three read-only Neon checks. Default execution passed 63 and skipped those three. Ruff lint/format and pip dependency checks passed; offline migration SQL, current revision and schema drift were checked. Pooled/direct connectivity and seed counts were independently verified. Earlier disposable PostgreSQL regression coverage is historical; those fixtures are removed. Frontend unchanged and not re-tested. No AI/voice integration or application deployment verified.

**Current blocker:** none for module 4. Neon MCP works, and local credentials are configured in the ignored owner-only backend dotenv file. Do not print or commit its values.

**Exact next task after approval:** module 5 — accessible responsive frontend layout and navigation. Read root and frontend `AGENTS.md`, inspect the existing starter and explain purpose, dependencies, affected files and approach before editing. Do not add jobs APIs, candidate features or future provider scaffolding during that module.
