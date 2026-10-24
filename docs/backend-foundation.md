# Backend foundation — modules 3–4

## Application and configuration

`app.application.create_app(settings=None)` constructs an independent FastAPI app. Tests can pass an immutable `Settings` instance. Normal startup loads settings once per app through `app.main:app` or Uvicorn's `--factory` mode. There is no process-global settings cache. Debug tracebacks are disabled in every environment.

The backend uses [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) with this precedence: explicit constructor arguments, process environment, `backend/.env`, defaults. The dotenv path is resolved from the installed package, not the shell's current directory. This repository uses an editable package installation. A non-editable wheel deployment must supply process environment variables rather than assume a source-tree dotenv location.

| Setting | Accepted values | Default |
| --- | --- | --- |
| `DOCS_ENABLED` | Boolean controlling API docs/schema visibility | `true` |
| `CORS_ALLOWED_ORIGINS` | JSON array of exact HTTP(S) browser origins | `[]` |
| `DATABASE_URL` | Secret PostgreSQL runtime URL for `talent-insight` | unset |
| `DIRECT_DATABASE_URL` | Secret direct URL for the same database, used by migrations | unset |

There are no application environment modes. Local and hosted runs use the same Neon database; the ignored local `backend/.env` has both URLs configured privately, and the host will need those same values in its secret settings. Remove `APP_ENV` from older dotenv files. Explicit settings apply consistently everywhere. Example settings are in `backend/.env.example`. Origin hostnames/default ports are canonicalized and duplicates removed; an optional root slash is removed. Credentials, non-root paths, queries, fragments, wildcards, surrounding whitespace and non-HTTP(S) schemes are rejected. Non-loopback origins require HTTPS; loopback origins may use HTTP. An empty list permits no cross-origin browser access.

Unknown dotenv keys fail validation to catch typos. Unrelated process environment variables are ignored. Configuration decoding/validation/read failures abort app creation with a generic diagnostic naming the settings, without echoing values. Restart after changing settings; the app does not hot-reload them. Database URLs are optional until catalog features need them; when provided, they are validated and stored as redacted secrets. The application does not connect, migrate or seed on startup.

## HTTP contract

`GET /health` returns HTTP 200:

```json
{"status":"ok"}
```

It includes `Cache-Control: no-store`. This is a process liveness endpoint. It does not query Neon, contact a provider, check credentials or assert readiness of unimplemented features. No other recruiting routes exist yet.

`/docs` and `/openapi.json` are enabled by default and return 404 when `DOCS_ENABLED=false`; `/redoc` is always disabled. This explicit flag replaces the previous environment-specific rule. The Swagger page uses FastAPI's default external UI assets, so it needs internet access; health and the JSON schema do not. `/health/` is not redirected to `/health`.

## CORS

Following [FastAPI's CORS interface](https://fastapi.tiangolo.com/tutorial/cors/), the app allows exact configured origins with `GET` and `Content-Type`. Browser CORS credentials are disabled. Explicit method/header permissions will be extended when future modules add POST uploads or session endpoints. No wildcard or origin regex is used.

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

## Verification and scope

Automated tests cover dotenv/process/explicit setting precedence, CWD-independent file loading, invalid and unknown configuration, HTTPS remote origins, isolated factories, docs flags, health behavior, exact origin/preflight matching, CORS on errors, invalid requests/responses, safe exception logging, midstream failure and preserved protocol headers. They use synthetic values and in-process ASGI requests, with real settings files excluded from tests.

Module 4 adds the [database catalog](database.md), independently of health and application startup. Request quotas, upload limits, provider retries, authentication, voice and public deployment remain future work. There is no database or provider readiness claim in `/health`. The frontend remains the module 2 starter.
