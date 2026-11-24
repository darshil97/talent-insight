# Deployment

Render runs one backend web service, which serves the browser API and Deepgram's interviewer calls. Vercel serves the frontend, which calls that backend from the browser. Both deploy from GitHub `main`; push to deploy. Neon is shared with local runs and is already at migration `0004_usage_candidate_ref`, so a deploy needs no migration or seed.

Variable meanings, values and the local versus hosted split are in [configuration](configuration.md). You enter every secret yourself in the dashboards.

## 1. Render backend

**New → Web Service → your repository:**

| Field | Value |
| --- | --- |
| Region | Singapore (cannot be changed later) |
| Instance type | Free |
| Root Directory | `backend` |
| Build Command | `pip install -r requirements-dev.lock && pip install --no-deps .` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --no-access-log` |
| Health Check Path | `/health` |

Keep a single Uvicorn worker: screening sessions and limits live in process memory.

**Environment:**

| Kind | Variables |
| --- | --- |
| Plain values | `PYTHON_VERSION=3.12.16`, `DOCS_ENABLED=false`, `LOG_LEVEL=INFO`, `AI_MODE=bedrock`, `AWS_REGION=ap-southeast-2`, `BEDROCK_MODEL_ID=openai.gpt-oss-120b-1:0`, `VOICE_BEDROCK_MODEL_ID=au.anthropic.claude-haiku-4-5-20251001-v1:0`, `RESUME_TIMEOUT_SECONDS=30`, `VOICE_SESSIONS_PER_HOUR=3`, `CORS_ALLOWED_ORIGINS=["https://YOUR-APP.vercel.app","http://127.0.0.1:3000","http://localhost:3000"]` |
| Optional | `AI_ASSESSMENTS_PER_DAY` (upload assessments per rolling 24 hours, default 100), `VOICE_SESSIONS_PER_DAY` (default 20) |
| Secrets | `DATABASE_URL` (pooled Neon URL), `AWS_BEARER_TOKEN_BEDROCK`, `DEEPGRAM_API_KEY`, `SESSION_SIGNING_SECRET` (new random value), `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` |
| After the first deploy | `VOICE_PUBLIC_API_URL=https://YOUR-SERVICE.onrender.com` (the service's own URL, no trailing slash), then `VOICE_MODE=deepgram` |

Text screenings work before the two voice variables are set. Saving any variable restarts the service.

## 2. Vercel frontend

**Add New → Project → your repository:**

| Field | Value |
| --- | --- |
| Root Directory | `frontend` |
| Framework Preset | Next.js |
| Install / Build | `npm ci` / `npm run build` |
| Node.js | 24.x |
| Environment | `NEXT_PUBLIC_API_BASE_URL=https://YOUR-SERVICE.onrender.com` |

The API URL is built into the bundle: **redeploy after changing it**. Put the production origin (e.g. `https://talent-insight-jet.vercel.app`) in Render's `CORS_ALLOWED_ORIGINS`. Per-deployment and branch URLs are not in the list, so screenings work only from the production URL.

## 3. Cloudflare Turnstile (bot check)

1. In the Cloudflare dashboard (free plan; no DNS change), open **Turnstile → Add widget**.
2. **Hostname:** the Vercel production hostname only, e.g. `talent-insight-jet.vercel.app`, with no scheme or path. Add a custom domain here if you add one to Vercel.
3. **Mode:** Managed. **Pre-clearance:** off. Then **Create**.
4. Put the site key and secret key on Render as `TURNSTILE_SITE_KEY` and `TURNSTILE_SECRET_KEY`. Nothing goes on Vercel.

The same widget guards screenings (action `screening_start`) and resume uploads (action `resume_assess`); actions need no Cloudflare setting.

Deploy Render and Vercel together when the guarded routes change. An old page cannot send a token, so every start or upload would be refused with `bot_check_failed`.

## 4. Keep the Free instance awake

Add an UptimeRobot HTTP monitor for `https://YOUR-SERVICE.onrender.com/health` every 10 minutes. This uses about 744 of Render's 750 free hours a month, so run no other Free service in that workspace.

## 5. Checks after a deploy

```bash
curl -s https://YOUR-SERVICE.onrender.com/health
```

```bash
curl -s https://YOUR-SERVICE.onrender.com/screenings/notice
```

- `/health` returns `{"status":"ok"}`.
- `/screenings/notice` shows `text_available: true`, `voice_available: true` (with `VOICE_MODE=deepgram`) and your `bot_check_site_key`.
- **Screening:** on Vercel, open a demo candidate and run a short screening. Render's logs show `Bot check passed in … ms` and then `Screening started`.
  - `Bot check unavailable: invalid-input-secret` means the Turnstile secret is wrong.
  - A missing `POST /screenings/{session_id}/chat/completions` line during a voice call means Deepgram cannot reach `VOICE_PUBLIC_API_URL`.
- **Upload:** `/resumes/limits` shows your `bot_check_site_key`. Pass the check in the add-candidate panel, then upload a text-based PDF. The logs show `Bot check passed in … ms`, then `PDF extracted: … pages, … characters in X ms`. An `extraction_timeout` (HTTP 408) means `RESUME_TIMEOUT_SECONDS=30` is missing. If `X` is often near 30,000, the Free CPU is too slow, and Starter is the fix.
- **Usage rows:** about 10 seconds later, new rows with `origin = 'render'` appear in Neon `talent_insight.usage_events`. A `Screening usage:` log line follows about 15 minutes after a screening, when its session is deleted.

## 6. Cost safeguards

Voice is open to any visitor. A Deepgram connection is billed per minute (about $0.065) and runs browser to Deepgram, where the backend cannot close it. A script that passes the bot check could keep one open after the 10-minute limit. Safeguards:

- Use a dedicated Deepgram project and key with prepaid credit and no automatic top-up.
- Keep `VOICE_SESSIONS_PER_HOUR=3`. `VOICE_SESSIONS_PER_DAY` defaults to 20.
- Uploads need the bot check and are capped by `AI_ASSESSMENTS_PER_DAY` (default 100 per rolling 24 hours, 2–4 Bedrock calls each).
- Check usage weekly. Compare the Neon usage table, or the `Screening usage` lines, with Deepgram's and AWS's usage pages ([data retention](data-retention.md#usage-table-on-neon) has the queries).
- Keep **Bedrock → Settings → Model invocation logging** off in AWS, so prompts containing resume and transcript text are not stored.

To turn voice off, remove `VOICE_MODE`. Text screenings keep working.

## 7. Moving to a new Render service

1. Create the service as in step 1 with the same variables, a new `SESSION_SIGNING_SECRET` and the new `VOICE_PUBLIC_API_URL`.
2. Update Vercel's `NEXT_PUBLIC_API_BASE_URL` and redeploy.
3. Point the UptimeRobot monitor at the new `/health`.
4. Suspend the old service. If its account may have been exposed, replace the Deepgram, Bedrock, Neon and Turnstile secrets.

## Limits

- Render Free can restart at any time, which drops screenings in progress. Queued usage rows are written on a clean shutdown but lost on a crash.
- Limits are per process; extra workers or instances would each apply their own.
- Neon runs in a US region, so each catalog read from Singapore crosses regions. The frontend caches catalog pages briefly.
- The build installs from `requirements-dev.lock`, which includes test tools; a runtime-only lock is an optional improvement.
