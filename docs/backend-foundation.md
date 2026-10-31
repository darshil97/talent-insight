# Backend foundation

The FastAPI app factory, configuration loading, and the HTTP behaviour shared by every route. Feature details are in the linked docs; variables are in [configuration](configuration.md).

## Application

- `app.application.create_app(settings=None)` builds an independent app; tests pass their own `Settings`. `app.main:app` loads settings once at startup. `debug` is always off.
- The lifespan creates a lazy database engine when `DATABASE_URL` is set and disposes it on shutdown. Startup never connects, migrates or seeds.
- Background tasks: purge expired screening sessions every 60 seconds; flush queued `usage_events` rows every 10 seconds and once more on shutdown. See [database](database.md).
- Admission limits (AI calls, PDF parsers, screening sessions) are per-process counters that reset on restart. Run one Uvicorn worker.

## Configuration

- `app/config.py` defines one immutable settings model. Sources, highest first: explicit arguments, process environment, `backend/.env`, packaged `backend/app/config.yaml`. Empty values fall through; YAML `${NAME}` / `${NAME:-fallback}` placeholders read exported variables.
- File paths are resolved from the package, not the working directory.
- Unknown or duplicate keys, invalid values and broken cross-field rules (weights totaling 100, ordered credits and tiers, voice time ordering, paired Turnstile keys) stop app creation with a message that never echoes values.
- Secrets are `SecretStr`. Restart after any change.

## Routes

| Route | Purpose | Details |
| --- | --- | --- |
| `GET /health` | Liveness only: `{"status":"ok"}`, `Cache-Control: no-store`; no database or provider check | — |
| `GET /jobs`, `GET /jobs/{job_id}` | Synthetic job catalog | [jobs](jobs.md) |
| `GET /jobs/{job_id}/candidates[/{candidate_id}]` | Synthetic pool and profiles | [candidates](candidates.md) |
| `POST /availability` | Availability summary and ranking score | [candidates](candidates.md) |
| `GET /resumes/limits`, `POST /resumes/extract` | Temporary PDF text | [resumes](resumes.md) |
| `POST /jobs/{job_id}/resumes/structure`, `.../assess` | Uploaded PDF extraction and assessment | [structured extraction](structured-extraction.md) |
| `/screenings/...` | Notice, start, token, messages, end, report, Deepgram `chat/completions` | [voice sessions](voice-sessions.md), [screening reports](screening-reports.md) |

- `/docs` and `/openapi.json` exist only when `DOCS_ENABLED` is true (default). `/redoc` is off. Swagger UI loads assets from a public CDN.
- `/` returns the 404 envelope; trailing slashes are not redirected.
- Catalog routes use one read-only transaction with a 5-second statement timeout. A missing `DATABASE_URL` or database error returns a sanitized 503.

## CORS

- Exact origins from `CORS_ALLOWED_ORIGINS` (default empty: no cross-origin access). HTTPS except loopback; no wildcards, paths, credentials, queries or fragments.
- Methods `GET` and `POST`, request header `Content-Type`, exposed header `X-Request-ID`, no credentials.
- CORS wraps the error boundary, so sanitized 500s carry CORS headers. A rejected preflight gets Starlette's plain-text 400.
- CORS is not authentication or rate limiting.

## Errors

```json
{"error":{"code":"not_found","message":"Not Found."}}
```

- Every application error uses this envelope with `Cache-Control: no-store`. Status codes are kept; `Allow` and `Retry-After` headers are preserved; exception details are never echoed.
- Generic codes follow the status (`not_found`, `validation_error`, `rate_limit_exceeded`, `service_unavailable`, `internal_error`, ...). Features add their own safe codes, such as `resume_busy` or `ai_rate_limited`.
- Validation errors return 422 without Pydantic details, since inputs may hold resume text.
- `SafeErrorsMiddleware` turns anything unhandled into a generic 500 and logs only the exception class. If the response already started, it ends it with a sanitized error.

## Request IDs and application logs

- Middleware order, outermost first: CORS, request ID, error boundary.
- A caller may send `X-Request-ID` (1–64 characters of `A–Z a–z 0–9 . _ -`); otherwise a 32-character hex ID is generated. Every response returns it.
- Only the `app` logger is configured, at `LOG_LEVEL`, to stderr as `time | request_id | level | logger | message`.
- Each request logs one line: method, route template (never the raw URL), status, duration. `/health` logs at DEBUG.
- Other lines hold identifiers, counts, durations and safe codes only. Resume text, transcripts, prompts, model output, names, credentials and exception messages are never logged. Run Uvicorn with `--no-access-log`. See [data retention](data-retention.md).
- `python -m app.refresh_demo --run` uses `refresh-<job>-<candidate>` request IDs.

## Limitations

- `/health` does not report database or provider readiness.
- No authentication. Abuse controls are per-process limits and the optional Cloudflare Turnstile check before a screening.
