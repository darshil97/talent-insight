# Configuration

Every backend setting has a default in [`backend/app/config.yaml`](../backend/app/config.yaml). You only set the ones listed here.

- **Order:** process variables (Render) override `backend/.env` (local), which overrides `config.yaml`.
- **Empty values** fall through to the next source.
- **Unknown keys** in `.env` or YAML, and invalid values, stop the backend at startup. The error message never echoes the value.
- **Changes** need a restart. On Render, saving a variable restarts the service, which drops any screening in progress.
- **Secrets** go only in `backend/.env` (ignored by Git) or Render's environment. Never put them in the frontend or in `NEXT_PUBLIC_` variables.

## Backend: what to set where

"Local" means `backend/.env`; [`backend/.env.example`](../backend/.env.example) lists placeholders. "Render" means the web service's environment.

### Core

| Variable | Local | Render | What it does and values |
| --- | --- | --- | --- |
| `DATABASE_URL` | Required | Required (secret) | Pooled Neon URL, the only database. Remote URLs need `sslmode=require`. |
| `DIRECT_DATABASE_URL` | Only for migrations | — | Direct (non-pooler) Neon URL that Alembic uses. |
| `CORS_ALLOWED_ORIGINS` | Set by `run_local.sh`; put it in `.env` only when running Uvicorn directly | Required | JSON array of exact browser origins, e.g. `["https://talent-insight-jet.vercel.app","http://127.0.0.1:3000","http://localhost:3000"]`. Remote origins must be HTTPS; no paths or wildcards. Empty means no cross-origin access. |
| `DOCS_ENABLED` | Optional | `false` | Shows the API docs at `/docs`. Default `true`. |
| `LOG_LEVEL` | Optional | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. Default `INFO`. |
| `PYTHON_VERSION` | — | `3.12.16` | Render's Python version. Its own default (3.14) is not supported. |
| `RESUME_TIMEOUT_SECONDS` | Optional | `30` | PDF parse limit, 0.1–30 s, default 10. Render Free's 0.1 CPU needs the maximum. |

### AI (Amazon Bedrock)

| Variable | Local | Render | What it does and values |
| --- | --- | --- | --- |
| `AI_MODE` | `bedrock` or `mock` | `bedrock` | `bedrock` makes paid calls. `mock` uses offline scripted results for UI work. Unset turns AI off: no upload assessments or screenings, though demo assessments still show from the saved snapshot. |
| `AWS_REGION` | `ap-southeast-2` | `ap-southeast-2` | Bedrock region, required for `bedrock`. |
| `BEDROCK_MODEL_ID` | `openai.gpt-oss-120b-1:0` | same | Resume assessment and screening reports. |
| `AWS_BEARER_TOKEN_BEDROCK` | Secret | Secret | Bedrock API key. Alternatively, locally, use `AWS_PROFILE` or `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_SESSION_TOKEN`. |
| `VOICE_BEDROCK_MODEL_ID` | `au.anthropic.claude-haiku-4-5-20251001-v1:0` | same | Interviewer model. Unset reuses `BEDROCK_MODEL_ID`, which is too slow for voice. |
| `VOICE_AWS_REGION` | Optional | Optional | Interviewer region; unset reuses `AWS_REGION`. |
| `BEDROCK_STRUCTURED_METHOD` | Optional | Optional | `json_schema` (default) or `function_calling`. |
| `BEDROCK_REASONING_EFFORT` | Optional | Optional | `low`, `medium` or `high` for assessment calls. Unset sends nothing. |

On this Mac the shell profile exports an old `AWS_BEARER_TOKEN_BEDROCK`, which overrides `backend/.env`. Prefix local Bedrock commands with `env -u AWS_BEARER_TOKEN_BEDROCK`, or remove the export.

### Screening, voice and bot check

| Variable | Local | Render | What it does and values |
| --- | --- | --- | --- |
| `SESSION_SIGNING_SECRET` | Required for screenings | Required (secret) | At least 32 random characters. Signs upload screening context. Use a different value on Render, e.g. from `python -c "import secrets; print(secrets.token_urlsafe(32))"`. |
| `VOICE_MODE` | Unset (or `mock`) | `deepgram` | `deepgram` gives real voice calls. `mock` gives a fake token for UI work, with no call. Unset turns voice off; text screenings still work. |
| `DEEPGRAM_API_KEY` | — | Secret | Deepgram key with Member permission; it only issues 30-second browser tokens. Needed for `deepgram`. |
| `VOICE_PUBLIC_API_URL` | Unset (or `http://127.0.0.1:8000` with `mock`) | Required with voice | The backend's own public HTTPS URL, which Deepgram calls for interviewer turns, e.g. `https://YOUR-SERVICE.onrender.com`. Deepgram cannot reach a local backend. |
| `VOICE_SESSIONS_PER_HOUR` | Optional | `3` | Screening starts per process per rolling hour, 1–60, default 6. |
| `VOICE_SESSIONS_PER_DAY` | Optional | Optional | Screening starts per process per rolling 24 hours, 1–500, default 20. |
| `TURNSTILE_SITE_KEY` | Unset | Required | Cloudflare Turnstile site key (public). The backend sends it to the page. |
| `TURNSTILE_SECRET_KEY` | Unset | Secret | Turnstile secret. Set both keys or neither, otherwise startup fails. Locally, Cloudflare's always-pass test pair (`1x00000000000000000000AA` / `1x0000000000000000000000000000000AA`) works on `localhost`. |

### Usage tracking

| Variable | Local | Render | What it does and values |
| --- | --- | --- | --- |
| `USAGE_RECORDING` | Optional | Optional | Default `true`: with `DATABASE_URL` set, every Bedrock call and voice session writes a counts-only row to Neon `usage_events`. `false` stops it. |
| `USAGE_TOKEN_PRICES` | Optional | Optional | Overrides the Bedrock prices in `config.yaml`, as JSON `[["MODEL_ID", INPUT_USD, OUTPUT_USD]]` per million tokens. The defaults cover both models above. |
| `USAGE_DEEPGRAM_MINUTE_PRICE` | Optional | Optional | Deepgram USD per minute; `config.yaml` default 0.065. |

Rows are marked `origin = render` on Render, using the `RENDER` variable that Render sets itself, and `local` elsewhere. See [data retention](data-retention.md#usage-table-on-neon).

### Tuning (rarely changed)

Defaults are in `config.yaml`. Set the variable named here to override one.

| Group | Variables (default) |
| --- | --- |
| Resume PDFs | `RESUME_MAX_BYTES` (5 MB, max 10 MB), `RESUME_MAX_PAGES` (20), `RESUME_MAX_CHARACTERS` (100,000), `RESUME_UPLOAD_TIMEOUT_SECONDS` (15), `RESUME_MAX_CONCURRENT` (2) |
| AI calls | `AI_TEMPERATURE` (0), `AI_MAX_INPUT_CHARACTERS` (20,000), `AI_MAX_OUTPUT_TOKENS` (8,192), `AI_TIMEOUT_SECONDS` (130), `AI_MAX_ATTEMPTS` (2), `AI_MAX_CONCURRENT` (1), `AI_REQUESTS_PER_MINUTE` (5) |
| Matching | `MATCH_WEIGHT_MANDATORY` / `_EXPERIENCE` / `_PREFERRED` / `_QUALIFICATION` (50/25/15/10, must total 100), `MATCH_CREDIT_TRANSFERABLE` (0.75), `MATCH_CREDIT_PARTIAL` (0.5), `RANKING_AVAILABILITY_TIERS` (`[[15,5],[30,4],[45,3],[60,2],[90,1]]`: days to join, bonus) |
| Screening | `VOICE_SCREENING_SECONDS` (600), `VOICE_WRAP_UP_SECONDS` (540), `VOICE_SESSION_EXPIRY_SECONDS` (900); these must satisfy wrap-up < screening < expiry. Also `VOICE_CONTEXT_TTL_SECONDS` (1,800), `VOICE_MAX_TURNS` (40), `VOICE_MAX_RECONNECTS` (2), `VOICE_MAX_CONCURRENT` (1), `VOICE_MAX_MESSAGES` (80), `VOICE_MAX_HISTORY_CHARACTERS` (60,000), `VOICE_TOKEN_TTL_SECONDS` (30), `VOICE_TURN_TIMEOUT_SECONDS` (20), `VOICE_MAX_OUTPUT_TOKENS` (300), `VOICE_REASONING_EFFORT` (`low`, sent only to gpt-oss models) |
| Deepgram | `VOICE_LISTEN_MODEL` (`flux-general-en`), `VOICE_SPEAK_MODEL` (`aura-2-thalia-en`), `VOICE_AGENT_URL`, `VOICE_API_URL` (general region) |

Limits and counters live in each process's memory and reset on restart. Run one Uvicorn worker.

## Frontend

| Variable | Local | Vercel | What it does |
| --- | --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | Set by `run_local.sh` (`http://127.0.0.1:8000`); to use another backend, export it before `start`. `frontend/.env.local` applies only to a direct `npm run dev` | Required: the Render URL, e.g. `https://YOUR-SERVICE.onrender.com` | The backend origin the browser calls. HTTPS remotely, no path. It is built into the bundle, so **redeploy after changing it**. |

No other frontend variable exists. The Turnstile site key comes from the backend.

## Launcher

`./run_local.sh` uses `BACKEND_PORT` (8000) and `FRONTEND_PORT` (3000). Unless they are already exported, it sets the matching `NEXT_PUBLIC_API_BASE_URL` and `CORS_ALLOWED_ORIGINS` as process variables for that run. These override `backend/.env` and `frontend/.env.local`; no file is edited.
