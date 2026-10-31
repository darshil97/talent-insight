# Talent Insight: project context

The starting brief for a coding assistant. Read [AGENTS.md](AGENTS.md) first: it holds the working rules. This file holds the current state, the decisions to respect and where things are. Update the **Status** and **Open items** sections when work finishes; record history in Git, not here.

## Status (2026-11-01)

- **All 15 roadmap modules are complete and approved.** The app is deployed: backend on Render (Singapore, Free), frontend on Vercel at `talent-insight-jet.vercel.app`. The user confirmed voice, text screening, reports and the Cloudflare check working.
- Commit `fe87961` added the Neon usage table and prices. Render is recording: one upload's extraction and interpretation rows, sharing a `request_id`, were seen on 2026-11-01.
- **Uncommitted:** `candidate_ref` linking, no more PDF-parse rows, and Deepgram time measured to the hang-up. Neon already has migration `0004`, and the one PDF-parse row was deleted. Render needs this code deployed.
- Neon is at migration `0004_usage_candidate_ref`.
- There is no pending module. Wait for the user's task, then propose a plan per AGENTS.md before editing.

## Product

A recruiting assistant for technical recruiters and small agencies, built as a portfolio demo. The workflow: select a job → review candidates → upload a resume → inspect the match and its evidence → optional AI screening (voice or text) → review the report → a **human decides**.

- **Catalog:** four demo jobs (Senior Data Scientist, Backend Engineer, HR and Operations Specialist, Marketing Operations Specialist), twelve clearly synthetic candidates and thirteen job memberships.
- **Non-goals:** ATS features, login, admin UI, job creation, outbound calls, automated hiring decisions, permanent uploaded-candidate records, vector DB, Redis, multi-agent orchestration.

## Architecture

| Part | Technology | Hosting |
| --- | --- | --- |
| Frontend | Next.js 16 (App Router, Webpack builds), React 19, TypeScript, Tailwind 4. Presentation only | Vercel |
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic, LangChain `ChatBedrockConverse`, pypdf | Render, one Uvicorn worker |
| Database | Neon project `talent-insight`, schema `talent_insight`. The catalog is read-only at runtime; the only runtime write is `usage_events` | Neon (one database for local and hosted runs) |
| AI | Bedrock in `ap-southeast-2`: `openai.gpt-oss-120b-1:0` for resume assessment and reports, `au.anthropic.claude-haiku-4-5-20251001-v1:0` for the interviewer | AWS |
| Voice | Deepgram Voice Agent (`flux-general-en` STT, `aura-2-thalia-en` TTS). Audio goes browser ↔ Deepgram; Deepgram calls the backend as a custom LLM | Deepgram |
| Bot check | Cloudflare Turnstile before a screening starts | Cloudflare |

**Flows:**
- **Upload:** a PDF is parsed in a child process (stdin, no files). Bedrock then extracts facts that must quote the resume exactly, and judges each requirement citing those facts. The backend computes the score deterministically and returns the result to the browser only.
- **Screening:**
  1. The candidate consents, then Turnstile runs.
  2. `POST /screenings` creates an in-memory session and returns a capability. Voice also gets a 30-second Deepgram token and the agent Settings.
  3. Deepgram calls `/screenings/{id}/chat/completions`, and the backend asks Haiku for each turn. Text mode uses `/messages` instead.
  4. `/end`, then `/report`: gpt-oss writes the judgments and quotes, the server verifies the quotes and computes the scores, and integrity flags send the report to human review.

## Decisions to respect

**Data and privacy**
- Neon is the only database; never start a local Postgres. There are no `APP_ENV` modes.
- Migrations and seeds against Neon need explicit user approval. Neon tests are opt-in (`--neon`) and read-only.
- Uploaded resumes, transcripts and reports are temporary:
  - They stay in process or browser memory only, never in Neon, files or browser storage.
  - Sessions expire after 15 minutes, and a 60-second timer purges them.
- Logs carry codes, counts and timings only, never resume or transcript text, names, capabilities or tokens.
- `usage_events` rows hold counts and prices only: one per Bedrock call and voice session, none for PDF parses.
  - `candidate_ref` links a candidate's rows. An upload gets a random `up_…` value, carried into its screenings by the signed context; a demo candidate uses its synthetic ID.
  - `screening_ref` groups one screening's rows, and `request_id` groups one request.
- Resumes and transcripts are untrusted input. Prompts keep instructions in Jinja Markdown templates and put data in a JSON message.
- Job-related evidence only. Never infer protected traits, personality or performance. Never judge fluency, accent or tone.

**Evidence and scoring**
- Missing evidence is `unknown`, never a missing skill.
- Statuses: `met`, `transferable` (applied use of a comparable tool), `partial`, `not_met`, `unknown`.
  - Credits are 1, 0.75, 0.5 and 0. Category weights are 50/25/15/10 (illustrative, not validated).
  - Any `unknown` gives a score range instead of a point score.
- Model output is salvaged per item. Unverifiable facts are dropped; invalid judgments become `unknown`. A stage retries once if most items fail.
- Availability gives a ranking bonus only. It never changes the match score.
- Uploaded names and titles are verified source spans used only for display, never for scoring or logs.
- **Demo assessments are a saved snapshot** (`backend/app/fixtures/assessments.json`). Its fingerprint covers `app/pipeline`, `app/llm`, `app/prompts` and `refresh_demo.py`. Changing those files invalidates all 13 entries until a paid `refresh_demo --run` (26 Bedrock calls, needs approval). Avoid touching them, or plan the refresh.

**Screening**
- Consent comes before AI processing and audio, and a text alternative is always available.
- The AI never scores or decides in the conversation; a recruiter reviews.
- Limits:
  - Screenings last 10 minutes, with wrap-up at 9 and a 40-turn cap.
  - Limits are per process: 1 concurrent, 6 per hour (3 on Render) and 20 per day.
  - Uploads carry an HMAC-signed `screening_context` that lasts 30 minutes.
- Reports use the dimensions relevance, specificity, ownership and explanation, plus graded correctness.
  - Every judgment needs a verified candidate quote.
  - Integrity flags (instruction override, score request, answer request, prompt probe) come from rules plus the model, and force human review.
- The Turnstile check fails closed if Cloudflare is down. The site key reaches the browser through `/screenings/notice`.

**Code and tooling**
- Frontend: presentation only. Backend: validation, provider calls and deterministic scoring. Use typed contracts and validate model output server-side.
- Add dependencies only when needed. Prefer small functions and provider adapters.
- Use the Conda env `talent-insight` (Python 3.12, Node 24). Activate it and put its `bin` first, because Homebrew Node 26 otherwise wins.
- Use Webpack, not Turbopack (Turbopack failed in this environment). ESLint stays on 9.x until the Next plugins support 10.
- `Settings` must stay hashable, because the Bedrock client cache is keyed on it. Use tuples, not dicts.

## Repository map

```text
backend/app/
  api/          routes: jobs, candidates, resumes, extraction (assess), availability, screenings, health
  pipeline/     extraction, interpretation, evidence, scoring   (snapshot-fingerprinted)
  llm/          provider registry, Bedrock adapter, invoke      (snapshot-fingerprinted)
  prompts/      resume prompts                                  (snapshot-fingerprinted)
  voice/        sessions, interviewer, deepgram, turnstile, report, integrity, prompts/
  usage.py      usage_events recorder      config.yaml / config.py   settings
  fixtures/     jobs/*.json, candidates.json, assessments.json (snapshot)
backend/alembic/versions/   0001 catalog, 0002 availability, 0003 usage_events, 0004 candidate_ref
backend/tests/              pytest (offline; Neon checks opt-in)
frontend/src/{app,components,lib}   pages, UI, API clients (screenings, voice agent, turnstile)
frontend/tests/             node:test
run_local.sh, scripts/      local launcher
```

## Commands

Run these from the repository root with `conda activate talent-insight`.

```bash
./run_local.sh start
```

```bash
cd backend && python -m pytest -W error && python -m ruff check . && python -m ruff format --check .
```

```bash
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
```

- The backend suite also guards the demo snapshot: `test_versioned_snapshot_is_served_for_every_demo_member` fails when fingerprinted code changes. `python -m app.refresh_demo` without `--run` checks fixture memberships only; `--run` makes paid Bedrock calls.
- This Mac's shell profile exports an old `AWS_BEARER_TOKEN_BEDROCK` that overrides `backend/.env`. Prefix local Bedrock and Alembic commands with `env -u AWS_BEARER_TOKEN_BEDROCK`.
- Migrations: `alembic upgrade head` from `backend/`. It uses `DIRECT_DATABASE_URL` and needs approval.
- Neon read-only checks: `python -m pytest --neon`.

## Docs

- [configuration](docs/configuration.md): every env variable, local vs Render vs Vercel.
- [deployment](docs/deployment.md): Render, Vercel, Turnstile, checks and cost safeguards.
- [local development](docs/local-development.md): setup, running and checks.
- [data retention](docs/data-retention.md): what is stored where, logs, the usage table and SQL.
- [voice sessions](docs/voice-sessions.md) and [screening reports](docs/screening-reports.md): screenings and reports.
- [resumes](docs/resumes.md), [structured extraction](docs/structured-extraction.md), [scoring](docs/scoring.md), [assessment UI](docs/assessment-ui.md): the resume pipeline.
- [jobs](docs/jobs.md), [candidates](docs/candidates.md), [database](docs/database.md), [backend foundation](docs/backend-foundation.md), [frontend layout](docs/frontend-layout.md).
- [provider research](docs/provider-research.md): provider findings and limits.

## Open items and limits

- **Deepgram cost risk (accepted):** a client that passes the bot check can hold a voice connection past 10 minutes, because only the browser can close it. Mitigations: prepaid credit without top-up, the hourly and daily caps, and weekly usage checks. Deepgram usage rows are an estimate: from the session's creation to the browser's hang-up, or to its last request if no hang-up arrives.
- **Scoring and accuracy:** limits and counters are per process and reset on restart. Scoring weights and model judgments have no accuracy evaluation; only synthetic resumes were tested. Scanned PDFs are rejected (no OCR).
- **Frontend test:** "the short fallback waits for the turn's first audio" relies on real timers and can fail under load.
- **AWS setting:** Bedrock model invocation logging must stay off in AWS; this is the user's setting.
- **Optional ideas, not approved:**
  - recruiter-authored accepted equivalents per requirement;
  - a runtime-only Render lock without test tools;
  - removing the stale shell export.
- **Unused code:** the `ResumeUpload` component and `uploadResume()` are imported nowhere, and `/resumes/extract` and `/jobs/{id}/resumes/structure` have no UI caller. The UI uses `/assess`, which parses the PDF itself.
- **Snapshot refresh cost:** the paid `refresh_demo --run` is not recorded in `usage_events`.
- Make no legal-compliance or hiring-outcome claims.
