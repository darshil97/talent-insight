# Deployment checklist: backend on Render, frontend on Vercel

Prepared in module 13 (2026-10-28) and updated through module 15 (2026-11-01). You create both services in their dashboards and enter every secret yourself; nothing here was deployed from this workspace. Module 15 added the Cloudflare bot check, a daily screening cap and the retention review. A runtime-only dependency lock and limits shared across processes remain optional.

There is **one backend**. A single Render web service serves the browser API (`/jobs`, `/assess`, `/screenings`, …) and Deepgram's interviewer calls (`/screenings/{id}/chat/completions`). `VOICE_PUBLIC_API_URL` is that service's own URL. The Vercel frontend calls it from the browser.

## 1. Push the code

Commit and push on the device that has the Git repository; Render and Vercel deploy from GitHub.

- Never copy `backend/.env` or `frontend/.env.local`; both are private, and `.gitignore` excludes `.env` and `.env.*`.
- Leave out `node_modules/`, `.next/` and `.run_local/`. `.claude/launch.json` is a local preview helper with no secrets; it is optional.
- No database migration or seed is needed. Render uses the same Neon database, already at `0003_usage_events` (the usage table was added on 2026-11-01).

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
- The lock still includes test tools (pytest, Ruff); trimming it is an optional follow-up.

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
| `RESUME_TIMEOUT_SECONDS` | `30` (the maximum). Render Free has 0.1 CPU, and the default 10 s PDF limit timed out on a one-page resume that takes 0.5 s locally. |
| `CORS_ALLOWED_ORIGINS` | `["https://YOUR-APP.vercel.app","http://127.0.0.1:3000","http://localhost:3000"]` |
| `USAGE_TOKEN_PRICES` | Not needed: `config.yaml` already prices both models above. Set it only to override them, as `[["MODEL_ID",INPUT_USD,OUTPUT_USD]]` per million tokens. Recording itself needs no setting. |

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
| `SESSION_SIGNING_SECRET` | A new random value of at least 32 characters, e.g. from `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Use a different value from your local one. |
| `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | The two keys of your Cloudflare Turnstile widget; see the bot check below. The site key is public; the secret is not. |

**After the first deploy, add `VOICE_PUBLIC_API_URL`.**
- Copy the service URL shown at the top of the Render dashboard, e.g. `https://YOUR-SERVICE.onrender.com` (HTTPS, no trailing slash), and add it as `VOICE_PUBLIC_API_URL`. Render restarts the service.
- It is the address Deepgram uses to send interviewer turns to *this* backend. It is checked only when `VOICE_MODE` is set, so the first deploy and text screenings work without it.
- Render's automatic `RENDER_EXTERNAL_URL` is not read by the app; set the variable explicitly.

**`VOICE_MODE`: values.**

| Value | Meaning | Use it |
| --- | --- | --- |
| *(unset)* | Voice off. Text screenings still work, and the consent form shows voice as unavailable. | Locally, and on Render whenever voice should be off. |
| `deepgram` | Real voice calls. Needs `DEEPGRAM_API_KEY`, an HTTPS `VOICE_PUBLIC_API_URL` and `SESSION_SIGNING_SECRET`. | On Render. The portfolio demo keeps it on after the first supervised test (see the decision below). |
| `mock` | A fake Deepgram token, so the voice consent path can be exercised but no call connects. Needs a `VOICE_PUBLIC_API_URL`; loopback `http://127.0.0.1:8000` is accepted. | Local UI development only. |

**Decision (2026-10-28): voice stays on for the public portfolio demo,** so any visitor can try it. The accepted risk and its safeguards:

- **What ends a call.** At 9 minutes the interviewer wraps up. At 10 minutes it returns a closing line and an `end_screening` signal and stops calling Bedrock. Our page then hangs up after the goodbye, with its own backstop 30 seconds after the limit. Visitors using the site are disconnected at about 10 minutes.
- **What doesn't.** The audio connection runs browser ↔ Deepgram. A script that takes a token from `POST /screenings` and ignores `end_screening` keeps the connection, and the Deepgram bill (about $0.065 per minute), running. The backend stops answering at 10 minutes and deletes the session at 15, but it cannot close that connection. Deepgram's own idle timeout is unverified, and a script can send silence.
- **Safeguards (no code):**
  - Use a dedicated Deepgram project and key for the demo, funded with prepaid credit and no automatic top-up if your plan allows, so the worst case is that credit. Confirm in Deepgram's billing settings how usage behaves when the credit runs out.
  - Set `VOICE_SESSIONS_PER_HOUR=3` on Render (default 6). `VOICE_SESSIONS_PER_DAY` caps starts over a rolling 24 hours (default 20, so about 200 call minutes). Limits apply per process and reset on restart; they cap starts, not call length.
  - Check Deepgram usage weekly; an hours-long connection stands out. Compare it with the backend's `Screening usage` log lines ([data retention](data-retention.md)).
  - In the AWS Bedrock console, keep **Settings → Model invocation logging** off, so AWS does not store resume and transcript prompts.
- **Bot check (module 15a):** Cloudflare Turnstile must pass before a screening starts; see below. It keeps the demo open to people without a login while stopping simple scripts from collecting tokens. A person, or a script that pays a solving service, can still pass it once per screening, so the safeguards above still apply.

**Bot check: Cloudflare Turnstile (module 15a).** `POST /screenings` verifies a Turnstile token before it reads the catalog, creates a session or asks Deepgram for a token, for voice and text alike. A failed check therefore never uses the hourly or daily limit.

Set it up once (Cloudflare's free plan; your domain does not move and DNS does not change):
1. In the Cloudflare dashboard, open **Turnstile** → **Add widget**.
2. **Widget name:** anything, e.g. `talent-insight`.
3. **Hostnames:** your Vercel production hostname only, e.g. `your-app.vercel.app`, without `https://`, port or path. A Vercel preview URL is a separate hostname; add it only to test there (10 per widget on the free plan). Don't add `localhost`: local runs use Cloudflare's test keys (see [local development](local-development.md)). Add a custom domain here if you add one to Vercel.
4. **Widget mode:** Managed (most visitors see nothing or a checkbox). Leave **pre-clearance** off. Select **Create**.
5. Add both keys to Render as `TURNSTILE_SITE_KEY` and `TURNSTILE_SECRET_KEY`. Keep the secret in a password manager, never in Git or chat. **Nothing goes on Vercel:** the backend sends the public site key with `/screenings/notice`, so the frontend shows the widget exactly when the backend requires it.

Behaviour:
- Both keys unset: no check. One key without the other: the backend refuses to start.
- The consent form shows the widget and the line "Cloudflare checks that you're a person before the screening starts."; **Agree and start** stays disabled until it passes.
- A token is valid for 5 minutes and works once. A rejected or expired token returns 403 `bot_check_failed`, and the form shows a fresh widget.
- If Cloudflare cannot be reached, screenings do not start (503 `bot_check_unavailable`) rather than skipping the check.
- The backend sends Cloudflare only the secret and the token, not the visitor's IP address, and requires the token's action to be `screening_start`. Logs show only Cloudflare's error codes, never the token or secret.

Changing an environment variable on Render restarts the service and drops any screening in progress.

**Local `backend/.env`:** don't copy the Render URL into it. Deepgram can't reach a backend on your machine, and screening sessions live in each backend's own memory, so a local session announced at the Render address would not exist there. Locally, leave `VOICE_PUBLIC_API_URL` and `VOICE_MODE` unset, or use the `mock` pair above for UI work.

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
- `/screenings/notice` should report `text_available: true`, and `voice_available` only while `VOICE_MODE=deepgram`. With the Turnstile keys set, `bot_check_site_key` shows the public site key.
- In the Vercel app: open Jobs, a role and a demo candidate. Run a short text screening on the profile page. With the bot check on, the widget should pass, and the Render log should show `Bot check passed in N ms` before `Screening started: text`. A `Bot check rejected: …` or `Bot check unavailable: …` line names Cloudflare's error code; `invalid-input-secret` means the secret key is wrong.
- Upload a text-based resume PDF to a role. The Render log should show `PDF extracted: … pages, … characters in X ms`.
  - If the upload fails with "PDF processing took too long" (log: `PDF extraction failed with extraction_timeout`, HTTP 408), check that `RESUME_TIMEOUT_SECONDS=30` is set.
  - 30 is the highest value the backend accepts; a higher value stops it starting.
  - If `X` is regularly near 30,000 ms, the Free plan's 0.1 CPU is too slow for PDF parsing, and a paid instance (Starter, 0.5 CPU) is the fix.

## 5. First live voice test (supervised)

1. In Render, confirm `VOICE_PUBLIC_API_URL` is set, then set `VOICE_MODE=deepgram` and wait for the restart.
2. Open a demo candidate in Chrome or Safari. Choose Voice, consent, allow the microphone, and talk for 2–3 minutes. Headphones avoid echo. Include one "I don't know" answer, then say you need to stop. Check that the status says you are muted during the greeting and each question, that talking over the interviewer does not cut it off, that "Listening" appears only after its audio finishes, and that the mic glow follows your voice and stays flat while muted.
3. In the Render logs, look for:
   - `Screening started: voice`
   - `POST /screenings/{session_id}/chat/completions`: the request from Deepgram. If it never appears, Deepgram could not reach the URL or calls a different path.
   - `Interviewer turn: … first text … ms`: per-turn latency.
   - Any `Screening request failed with …` code.
4. Keep `VOICE_MODE=deepgram` for the portfolio demo if the test looks good, with the safeguards above; otherwise remove it.

Expected cost: about $0.065 per connected minute on Deepgram plus a few cents of Bedrock.

Still unverified until this test:
- Deepgram accepts the browser's `bearer` token (scope `asr:write`).
- Deepgram calls the exact `endpoint.url`.
- How Deepgram uses streaming, and whether SSE passes through Render's proxy.
- `end_screening` is relayed to the browser.
- Real turn latency.
