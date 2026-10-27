# Backend foundation — modules 3–7

## Application and configuration

`app.application.create_app(settings=None)` constructs an independent FastAPI app. Tests can pass an immutable `Settings` instance. Normal startup loads settings once per app through `app.main:app` or Uvicorn's `--factory` mode. There is no process-global settings cache. Debug tracebacks are disabled in every environment.

The backend uses [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) with this precedence: explicit constructor arguments, process environment, `backend/.env`, then the committed nested `backend/app/config.yaml`. Empty process/dotenv values fall through to the next source. The YAML file is packaged with `app`; its `${NAME}` and `${NAME:-fallback}` placeholders read exported environment variables, while matching field names in `backend/.env` are read by Pydantic at higher precedence. The YAML and dotenv paths are fixed relative to the installed package, not the shell's current directory. A non-editable wheel deployment must supply process secrets rather than assume a source-tree dotenv location.

| Setting | Accepted values | Default |
| --- | --- | --- |
| `DOCS_ENABLED` | Boolean controlling API docs/schema visibility | `true` |
| `CORS_ALLOWED_ORIGINS` | JSON array of exact HTTP(S) browser origins | `[]` |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING` or `ERROR` for the `app` logger | `INFO` |
| `DATABASE_URL` | Secret PostgreSQL runtime URL for `talent-insight` | unset |
| `DIRECT_DATABASE_URL` | Secret direct URL for the same database, used by migrations | unset |

There are no application environment modes. Local and hosted runs use the same Neon database; the ignored local `backend/.env` has both URLs configured privately, and the host will need those same values in its secret settings. Remove `APP_ENV` from older dotenv files. Explicit settings apply consistently everywhere. Example settings are in `backend/.env.example`. Origin hostnames/default ports are canonicalized and duplicates removed; an optional root slash is removed. Credentials, non-root paths, queries, fragments, wildcards, surrounding whitespace and non-HTTP(S) schemes are rejected. Non-loopback origins require HTTPS; loopback origins may use HTTP. An empty list permits no cross-origin browser access.

Unknown dotenv or YAML keys, duplicate YAML keys and unsafe YAML tags fail validation to catch typos. Unrelated process environment variables are ignored. Configuration decoding/validation/read failures abort app creation with a generic diagnostic naming the settings, without echoing values. Restart after changing settings; the app does not hot-reload them. Database URLs are optional until catalog features need them; when provided, they are validated and stored as redacted secrets. The application does not connect, migrate or seed on startup.

## HTTP contract

`GET /health` returns HTTP 200:

```json
{"status":"ok"}
```

It includes `Cache-Control: no-store`. This is a process liveness endpoint. It does not query Neon, contact a provider, check credentials or assert readiness of unimplemented features. Module 6 adds [read-only jobs routes](jobs.md), independently of health.

`/docs` and `/openapi.json` are enabled by default and return 404 when `DOCS_ENABLED=false`; `/redoc` is always disabled. This explicit flag replaces the previous environment-specific rule. The Swagger page uses FastAPI's default external UI assets, so it needs internet access; health and the JSON schema do not. `/health/` is not redirected to `/health`.

## CORS

Following [FastAPI's CORS interface](https://fastapi.tiangolo.com/tutorial/cors/), the app allows exact configured origins with `GET`, `POST` and `Content-Type` (POST was added for module 8 PDF extraction). Browser CORS credentials are disabled. No wildcard or origin regex is used.

CORS wraps the error boundary, so allowed origins receive CORS headers even for sanitized HTTP 500 responses. A rejected preflight receives Starlette's HTTP 400 protocol response, which is plain text. Other application errors use the JSON contract below. A disallowed simple request can still execute server-side, but lacks an allow-origin response header. CORS is not authentication, rate limiting or protection from non-browser clients.

## Errors and logging

Application HTTP errors use a stable envelope, for example:

```json
{"error":{"code":"not_found","message":"Not Found."}}
```

Status codes are preserved; common codes include `bad_request`, `not_found`, `method_not_allowed`, `validation_error`, `rate_limit_exceeded`, `service_unavailable` and `internal_error`. HTTP exception details are not echoed. Trusted handler headers such as `Allow` and `Retry-After` are preserved, with `Cache-Control: no-store` enforced. Future user-facing domain errors should introduce deliberately safe typed messages, rather than return provider exceptions through `detail`.

Invalid request data returns HTTP 422 with `validation_error` and `Request validation failed.` Pydantic's raw input/error details are omitted because they may contain resumes or other private values. Unexpected failures and invalid response models return HTTP 500 with `internal_error` and a generic message.

A small ASGI error boundary catches pre-response failures inside CORS, logs only the exception class, and returns the safe envelope. This avoids the ordinary unhandled-error rethrow exposing the original message through a server traceback. After response headers have been sent, HTTP status/body cannot be replaced; the boundary logs the class and raises a sanitized error to terminate the incomplete response. Provider streaming/session adapters must handle their own completion and recovery when implemented. Lifespan/startup failures are not converted to successful HTTP responses.

The documented Uvicorn commands disable access logs, which would otherwise record request URLs. There is no request body, transcript, settings-value or exception-message logging. A future centralized logging/instrumentation setup must preserve these boundaries.

### Request IDs and application logs

`app/core/request_context.py` adds a pure-ASGI middleware between CORS and the error boundary. It accepts a caller's `X-Request-ID` only when it is 1–64 characters of `A–Z a–z 0–9 . _ -`; otherwise it generates a 32-character hex ID. The ID is stored in a context variable for the request, returned in the `X-Request-ID` response header on every response (including 404, 422 and sanitized 500 responses) and exposed to allowed browser origins through `Access-Control-Expose-Headers`.

`app/core/logging.py` configures only the `app` logger, at `LOG_LEVEL`, with the format `time | request_id | level | logger | message`. Uvicorn and SDK loggers keep their own configuration. Each request ends with one line containing the method, the **route template** (for example `/jobs/{job_id}/resumes/assess`, never the raw URL or query), status and duration; `/health` logs at DEBUG. The main points also log identifiers, counts and codes only:

- PDF parsing: page and character counts and duration, or the failure code; busy rejections.
- AI admission rejections (`ai_busy`, `ai_rate_limited`) and every `ExtractionFailure` code with its HTTP status.
- Each model attempt: stage, provider, model, attempt number, stop reason, input/output tokens and duration, or the failure code and exception class.
- Validation outcomes: facts kept/returned with discard counts by reason, requirements forced to unknown, retries and their reason, and whether a point score is available.

Resume text, prompts, model output, names, credentials and exception messages are never logged. The manual demo refresh binds `refresh-<job>-<candidate>` as its request ID so batch logs are traceable per synthetic membership.

## Verification and scope

Automated tests cover nested YAML loading, placeholders, YAML/dotenv/process/explicit precedence, CWD-independent file loading, invalid and unknown configuration, HTTPS remote origins, isolated factories, docs flags, health behavior, exact origin/preflight matching, CORS on errors, invalid requests/responses, safe exception logging, midstream failure and preserved protocol headers. They use synthetic values and in-process ASGI requests, with real dotenv secrets excluded from tests.

Module 4 adds the [database catalog](database.md). Module 6 creates a lazy per-app engine during lifespan and disposes it on shutdown; connections begin only on catalog requests. Jobs and module 7 [candidate requests](candidates.md) use read-only transactions and a five-second SQL statement timeout, with sanitized 503 responses on database failures. Candidate details validate exact resume provenance before serialization. Module 8 adds [bounded stateless PDF extraction](resumes.md), independent of catalog/provider access. Module 9 adds [structured extraction](structured-extraction.md) with canonical job/membership snapshots, bounded provider attempts, source validation and per-process admission/rate limits. Public abuse controls, authentication, voice and deployment remain future work. There is no database or provider readiness claim in `/health`.
