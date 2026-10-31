# Talent Insight

An AI recruiting assistant for technical recruiters and small agencies, built as a portfolio demo. The workflow: pick a job, review its synthetic candidates, upload a resume for an evidence-backed match, run an optional AI screening (voice or text), and read a structured report. **A recruiter makes every decision.**

- **Matching:** each requirement is judged only from quotes found in the resume. Missing evidence is "unknown", not a gap, and gives a score range instead of a false point score.
- **Screening:** a ten-minute, consent-based conversation with an AI interviewer, by voice (Deepgram) or text. The report verifies every quote it uses and flags attempts to game the AI.
- **Privacy:** uploaded resumes, transcripts and reports are temporary; nothing about a real candidate is stored. The demo catalog (four jobs, twelve synthetic candidates) lives in Neon.

**Stack:** Next.js on Vercel · FastAPI on Render · Neon Postgres · Amazon Bedrock (gpt-oss-120b, Claude Haiku 4.5) · Deepgram Voice Agent · Cloudflare Turnstile.

## Run locally

```bash
conda env create -f environment.yml
```

```bash
conda activate talent-insight && export PATH="$CONDA_PREFIX/bin:$PATH"
```

```bash
./run_local.sh start
```

Skip the first command if the `talent-insight` environment already exists. Install dependencies and set `backend/.env` first (see [local development](docs/local-development.md) and [configuration](docs/configuration.md)). The app runs at http://localhost:3000 and the API at http://localhost:8000 (`/health`, `/docs`). `./run_local.sh` also accepts `status`, `logs`, `restart` and `stop`.

## Documentation

- [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md): current state, decisions and the repository map; the starting point for coding work.
- [AGENTS.md](AGENTS.md): working rules for contributors and coding assistants.
- [Configuration](docs/configuration.md): every environment variable, local vs Render vs Vercel.
- [Deployment](docs/deployment.md): Render, Vercel, Cloudflare Turnstile, post-deploy checks and cost safeguards.
- [Local development](docs/local-development.md): setup, commands and checks.
- [Data retention and logs](docs/data-retention.md): what is stored where, logging rules and the usage table.
- Feature reference: [jobs](docs/jobs.md), [candidates](docs/candidates.md), [resumes](docs/resumes.md), [structured extraction](docs/structured-extraction.md), [scoring](docs/scoring.md), [assessment UI](docs/assessment-ui.md), [voice sessions](docs/voice-sessions.md), [screening reports](docs/screening-reports.md).
- Platform: [backend foundation](docs/backend-foundation.md), [database](docs/database.md), [frontend layout](docs/frontend-layout.md), [provider research](docs/provider-research.md).
