# Deployment checklist: backend on Render, frontend on Vercel

Prepared in module 13 (2026-10-28). Nothing here has been deployed from this workspace, and no secrets were handled; you create both services in their dashboards. This is a minimal deployment for testing. Production hardening (a runtime-only lock, distributed limits, abuse controls) remains module 15.

There is **one backend**. A single Render web service serves the browser API (`/jobs`, `/assess`, `/screenings`, …) and Deepgram's interviewer calls (`/screenings/{id}/chat/completions`). `VOICE_PUBLIC_API_URL` is that service's own URL. The Vercel frontend calls it from the browser.

## 1. Move the code

Copy the changed files to the device that has the Git repository, then commit and push there.

- Never copy `backend/.env` or `frontend/.env.local`; both are private, and `.gitignore` excludes `.env` and `.env.*`.
- Leave out `node_modules/`, `.next/` and `.run_local/`. `.claude/launch.json` is a local preview helper with no secrets; it is optional.
- No database migration or seed is needed. Render uses the same Neon catalog, already at `0002_candidate_availability`.

## 2. Render backend (Dashboard → New → Web Service → your repository)

| Field | Value |
| --- | --- |
| Language | Python 3 |
| Region | Singapore. This can't be changed later. |
| Instance type | Free |
| Root Directory | `backend` |
| Build Command | `pip install -r requirements-dev.lock && pip install --no-deps .` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --no-access-log` |
| Health Check Path | `/health` (Settings → Health Checks) |

Notes on these values:
- Keep a single Uvicorn worker. Screening sessions and admission limits live in process memory, so more workers would split them.
- The install is non-editable: configuration, fixtures, the demo snapshot and prompts ship as package data, and `backend/.env` is simply absent on Render.
- The lock still includes test tools (pytest, Ruff); trimming it is module 15 work.

**Environment, plain values:**

| Key | Value |
| --- | --- |
| `PYTHON_VERSION` | `3.12.16` (the locally verified version). Render needs a full `x.y.z` here, and its default for new services is Python 3.14, which this backend does not support. |
| `DOCS_ENABLED` | `false` |
| `LOG_LEVEL` | `INFO` |
| `AI_MODE` | `bedrock` |
| `AWS_REGION` | `ap-southeast-2` |
| `BEDROCK_MODEL_ID` | `openai.gpt-oss-120b-1:0` (resume assessment) |
| `VOICE_BEDROCK_MODEL_ID` | `au.anthropic.claude-haiku-4-5-20251001-v1:0` (interviewer) |
| `CORS_ALLOWED_ORIGINS` | `["https://YOUR-APP.vercel.app","http://127.0.0.1:3000","http://localhost:3000"]` |

`CORS_ALLOWED_ORIGINS` notes:
- Use your exact Vercel production origin, with no wildcard, path or trailing slash.
- Each Vercel preview URL works only if it is added too.
- The two loopback entries let your local frontend call Render.

**Environment, secrets (enter these yourself):**

| Key | Value |
| --- | --- |
| `DATABASE_URL` | The same pooled Neon URL as in your local `backend/.env`. |
| `AWS_BEARER_TOKEN_BEDROCK` | Your Bedrock API key. |
| `DEEPGRAM_API_KEY` | Your Deepgram key, with Member permission. |
| `SESSION_SIGNING_SECRET` | A new random value of at least 32 characters, e.g. from `python -c "import secrets; print(secrets.token_urlsafe(32))"`. |
| `VOICE_PUBLIC_API_URL` | Your service URL, e.g. `https://YOUR-SERVICE.onrender.com` (HTTPS, no trailing slash). |

**Leave `VOICE_MODE` unset by default.**
- With it unset, text screenings still work and the UI offers voice as unavailable.
- Set `VOICE_MODE=deepgram` only for a test window you supervise, then remove it.
- Why: anyone who finds a public backend could start voice sessions and hold Deepgram connections open. Those are billed per minute, and only the browser can close them. The backend allows at most 1 concurrent and 6 screenings per hour per process, but that is not a spending cap.
- Changing an environment variable on Render restarts the service.

**Keeping the Free instance awake (UptimeRobot):**
- Add an HTTP monitor for `https://YOUR-SERVICE.onrender.com/health` every 10 minutes.
- An always-on Free instance uses about 744 of the 750 free instance hours a month, so run no other Free web service in the same Render workspace, or both will be suspended when the hours run out.

**Free-tier limits:**
- Render may restart a Free instance at any time, which drops in-progress screening sessions.
- The instance is small; PDF parsing speed and memory there are unverified.
- Neon is in Ohio, so catalog reads from Singapore cross regions, similar to reads from India today.

## 3. Vercel frontend (Add New → Project → your repository)

| Field | Value |
| --- | --- |
| Root Directory | `frontend` |
| Framework Preset | Next.js |
| Install Command | `npm ci` |
| Build Command | `npm run build` (uses Webpack, as locally) |
| Node.js Version | 24.x. This is the default, and `package.json` `engines` also requires it. |
| Environment variable | `NEXT_PUBLIC_API_BASE_URL=https://YOUR-SERVICE.onrender.com` |

`NEXT_PUBLIC_API_BASE_URL` is inlined at build time, so set it before the first build and redeploy after changing it. After the first deploy:
1. Copy the production origin into Render's `CORS_ALLOWED_ORIGINS`. Render restarts automatically.
2. Vercel serves HTTPS, which the browser requires for microphone access.

To test against Render from your local frontend instead, put the same `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local` and restart `npm run dev`.

## 4. Checks after deploying

```bash
curl -s https://YOUR-SERVICE.onrender.com/health
```

```bash
curl -s https://YOUR-SERVICE.onrender.com/screenings/notice
```

- `/health` should return `{"status":"ok"}`.
- `/screenings/notice` should report `text_available: true`, and `voice_available` only while `VOICE_MODE=deepgram`.
- In the Vercel app: open Jobs, a role and a demo candidate. Run a short text screening on the profile page.

## 5. Supervised live voice test

1. In Render, set `VOICE_MODE=deepgram` and wait for the restart.
2. Open a demo candidate in Chrome or Safari. Choose Voice, consent, allow the microphone, and talk for 2–3 minutes. Headphones avoid echo. Include one "I don't know" answer and one interruption, then say you need to stop.
3. In the Render logs, look for:
   - `Screening started: voice`
   - `POST /screenings/{session_id}/chat/completions`: the request from Deepgram. If it never appears, Deepgram could not reach the URL or calls a different path.
   - `Interviewer turn: … first text … ms`: per-turn latency.
   - Any `Screening request failed with …` code.
4. Remove `VOICE_MODE` afterwards.

Expected cost: about $0.065 per connected minute on Deepgram plus a few cents of Bedrock.

Still unverified until this test:
- Deepgram accepts the browser's `bearer` token (scope `asr:write`).
- Deepgram calls the exact `endpoint.url`.
- How Deepgram uses streaming, and whether SSE passes through Render's proxy.
- `end_screening` is relayed to the browser.
- Real turn latency.
