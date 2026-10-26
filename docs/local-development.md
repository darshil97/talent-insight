# Local development

Modules 2–11 provide the frontend, read-only job/candidate APIs, Neon demo catalog, temporary PDF extraction, backend structured extraction and assessment APIs, and the assessment UI. Module 11 browser checks remain unconfirmed. Health/plain PDF parsing need no credentials; catalog browsing uses the existing Neon database. Structured extraction and assessment require an explicit provider choice; Bedrock mode uses private backend AWS settings. Local and hosted catalog runs share the same Neon database; no local PostgreSQL server is used.

## 1. Create and activate the Conda environment

From the repository root, once per machine:

```sh
conda env create -f environment.yml
```

The environment already exists on the original development machine; skip creation there. Activate it in each terminal:

```sh
conda activate talent-insight
export PATH="$CONDA_PREFIX/bin:$PATH"
python --version
node --version
```

Use Python 3.12 and Node 24. The PATH line ensures the environment's Node takes precedence if a shell configuration puts Homebrew first. It affects only the current shell. If activation reports that the shell is not initialized, follow your existing Anaconda shell setup, reopen the terminal and retry.

`environment.yml` selects compatible runtime families, allowing patch updates. `.python-version`, `.nvmrc` and frontend `engines` record the same runtime families. Application dependencies are version-locked separately. The verified environment uses Python 3.12.15, Node 24.13.0 and npm 11.6.2 on macOS arm64; Linux/Render and Vercel builds have not been tested.

The Conda manifest requires Python, Node and pip. PostgreSQL server tools are not required. Default checks run without a database; optional integration checks read the shared Neon catalog.

## 2. Install dependencies

From the repository root with Conda active:

```sh
python -m pip install -r backend/requirements-dev.lock
python -m pip install --no-build-isolation --no-deps -e backend
cd frontend
npm ci
```

The backend lock contains exact runtime, test and build dependency versions. The editable installation makes `app` importable without manipulating `PYTHONPATH`; its build dependency is included in the lock. `pyproject.toml` declares direct runtime and optional development dependencies. The npm lockfile captures the frontend dependency tree. Use `npm ci` after cloning; use `npm install` only for deliberate dependency updates.

Dependency updates should change the manifest and lock together, run all checks below, and be reviewed. Do not freeze an unrelated Conda environment into this project's lock. The backend lock was verified on macOS arm64 and is not yet a tested cross-platform or production lock.

## 3. Local configuration

From the repository root, optionally create local files without overwriting existing ones:

```sh
cp -n frontend/.env.example frontend/.env.local
cp -n backend/.env.example backend/.env
```

The examples contain no secrets. Both projects run without copying them; without a backend `.env` or process settings, API docs are enabled and cross-origin browser access is disabled. There is one application configuration and no environment-mode selection.

| Example | Setting | Current behavior |
| --- | --- | --- |
| `frontend/.env.example` | `NEXT_PUBLIC_API_BASE_URL` | FastAPI origin used by the browser jobs client; defaults to `http://127.0.0.1:8000` when absent |
| `backend/app/config.yaml` | Nested API, resume, AI and matching settings | Committed non-secret defaults loaded and validated at app creation |
| `backend/.env.example` | Optional `DOCS_ENABLED`, `CORS_ALLOWED_ORIGINS` | Private local overrides for docs visibility and permitted frontend origins |
| `backend/.env.example` | `DATABASE_URL`, `DIRECT_DATABASE_URL` | Placeholder examples for the same Neon database; the ignored local `backend/.env` is already configured privately on this machine; see [database setup](database.md) |
| `backend/.env.example` | `AI_MODE`, `AWS_REGION`, `BEDROCK_MODEL_ID`, `AWS_BEARER_TOKEN_BEDROCK` | Explicit mock/Bedrock provider selection and private credentials; [structured extraction](structured-extraction.md) documents the verified local model and limits |
| `backend/app/config.yaml` | Matching weights | Backend-only integer category weights totaling 100; see [scoring](scoring.md) |

Next.js loads `.env.local` automatically. The jobs client validates the API setting as an origin with no credentials, path, query or fragment; remote origins require HTTPS and loopback may use HTTP. Invalid settings show the safe unavailable state. Public settings are bundled into production builds, so rebuild after changing them. The backend loads packaged `app/config.yaml` and private `backend/.env` independently of the current directory. Explicit settings override process variables, which override dotenv, which overrides YAML. Empty values fall through; `${NAME}` and `${NAME:-fallback}` placeholders in YAML read exported variables. Restart the backend after changes. Unknown YAML or `.env` keys and malformed settings fail startup with a safe diagnostic. The CORS list accepts exact origins, not URL paths or wildcards. The launcher supplies both `http://localhost:3000` and `http://127.0.0.1:3000`, which are distinct browser origins. See [the configuration contract](backend-foundation.md).

Remove `APP_ENV` from older local files. Set `DOCS_ENABLED=false` if you want to hide API docs. Remote frontend origins require HTTPS consistently; HTTP is supported only for loopback origins. Secrets belong only in backend-local environment configuration or a deployment secret store. Configure the hosted backend with the same two Neon URL values when deploying. Never prefix provider keys with `NEXT_PUBLIC_`.

## 4. Start and stop both apps

From the repository root, after installing dependencies once:

```sh
./run_local.sh start
./run_local.sh status
./run_local.sh restart
./run_local.sh logs
./run_local.sh stop
```

The Bash wrapper activates the existing `talent-insight` environment using the current Conda installation or this machine's `/opt/anaconda3` installation. It prepends that environment's runtime directory and verifies Python 3.12/Node 24. It fails if dependencies are missing; it does not install them. On another machine, activate the same named environment first if Conda cannot be found.

The Python process manager starts Uvicorn with reload and access logging disabled, and uses the existing `npm run dev` Webpack command. Both bind to `127.0.0.1` using HTTP. It sets process defaults for the public API origin and the two local CORS origins; explicitly exported settings take precedence. It does not modify either dotenv file or any database/provider configuration. No authentication, shared API keys, certificates or HTTPS bypass instructions from the reference script were carried over.

Ports default to backend 8000/frontend 3000. To override them, export `BACKEND_PORT` and `FRONTEND_PORT` before `start` (stop existing managed servers first). The corresponding API/CORS process defaults follow those ports. No application environment modes or new databases are introduced.

Readiness checks request `/health` and the frontend overview only; they do not assert database readiness. Private PID records and logs are stored in ignored `.run_local/` (directory mode 0700, files 0600). The launcher verifies process start identity and a dedicated process group before stopping that server and its children. It refuses occupied unmanaged ports and never kills by port. If ownership cannot be verified after an abnormal exit or changed PID, it leaves that process alone; inspect and stop it manually. Start failures clean up only servers launched during that attempt.

Use Ctrl+C to exit log following. It leaves servers running. `stop` retains logs for inspection. These commands are verified on macOS; Linux process supervision and Windows are unverified. Direct run commands remain available below.

## 5. Run the frontend directly

In a terminal with Conda active:

```sh
cd frontend
npm run dev
```

Open [the local frontend](http://127.0.0.1:3000). The overview (`/`) and guide (`/guide`) need no backend; jobs (`/jobs`), job details and nested candidate pools/profiles require FastAPI, matching CORS origins and the existing Neon configuration. Open a job's **Candidates** tab to view the table. Choosing a text-based PDF there immediately requests a temporary assessment; the new row appears after completion and can open its evidence detail. Synthetic profiles display the current precomputed snapshot without a provider call. Uploaded PDFs use the backend's configured `AI_MODE`; the saved local value is Bedrock and makes provider calls. Set `AI_MODE=mock` explicitly in the backend process for no-cost upload workflow checks. See [assessment UI](assessment-ui.md), [jobs](jobs.md), [candidate checks](candidates.md) and [upload limits/privacy](resumes.md). Unknown routes show a recovery link. Press Ctrl+C to stop.

To build and serve the production bundle locally:

```sh
cd frontend
npm run build
npm start
```

Run these from the repository root or omit `cd frontend` if already there. Development and production servers use the same port, so stop one before starting the other. Both bind to loopback for local development. No external font download is required during the build. Set `NEXT_TELEMETRY_DISABLED=1` in your shell to opt out of Next.js telemetry.

The scripts explicitly use Webpack, a [supported Next.js CLI option](https://nextjs.org/docs/app/api-reference/cli/next). Turbopack could not bind its internal worker socket in this development environment, including on an approved retry outside the sandbox. The Webpack production build passed. Reconsider the bundler only after reproducing a successful Turbopack build; this does not change the application stack.

## 6. Run the backend directly

In another terminal, activate Conda and prepend its bin directory as above, then from the repository root:

```sh
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

The ASGI server runs at [localhost:8000](http://localhost:8000). [GET /health](http://localhost:8000/health) returns `{"status":"ok"}` with `Cache-Control: no-store`. It reports process liveness, not database/provider readiness. [GET /jobs](http://127.0.0.1:8000/jobs) and `/jobs/{job_id}` read the shared catalog. Missing/unavailable database configuration returns safe 503 responses. [API docs](http://localhost:8000/docs) and `/openapi.json` are controlled by `DOCS_ENABLED`; `/redoc` is disabled. `/` remains a structured 404. Press Ctrl+C to stop.

The factory can also be started as `python -m uvicorn app.application:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log`. Both entry points validate settings before serving. Access logging is disabled in these commands to avoid recording request URLs; startup logs and sanitized application exception logs remain available.

## 7. Verify the application

With Conda active, from `frontend/`:

```sh
npm run lint
npm run typecheck
npm test
npm run build
```

From `backend/`:

```sh
python -m pytest -W error
python -m ruff check .
python -m ruff format --check .
python -m pip check
python -m app.seed --validate-only
python -m app.refresh_demo
```

From the repository root, also run `bash -n run_local.sh`, `python -m unittest discover -s scripts -p 'test_*.py'`, `python -m ruff check scripts` and `python -m ruff format --check scripts`. Launcher unit tests mock process ownership and ports; they do not start servers. Frontend `npm test` uses Node 24's built-in test runner for job/candidate API contracts, public URL validation, evidence/Unicode validation and failure/cancellation behavior, without network calls or additional dependencies.

Configuration and HTTP tests exercise settings, health/docs, CORS and errors through HTTPX's in-process ASGI transport. They require no database, provider or HTTP server and isolate real dotenv/AWS configuration. Structured-extraction tests use synthetic PDFs, explicit mock mode and AWS SDK Stubber; they never invoke paid Bedrock. The transitive LangSmith pytest plugin is disabled to keep test tracing off. Frontend type generation runs before TypeScript checks, so a fresh checkout does not depend on stale generated route types. Next.js build does not replace the separate lint command.

The default suite also validates seed evidence and previews migration SQL without connecting. To include the shared Neon catalog checks, explicitly run `python -m pytest --neon -W error`. These checks use read-only transactions for migration revision, schema/model parity, membership and source evidence. They never migrate, seed or reset shared data. No local database fixture is started. See [database verification](database.md) for details.

Known tooling constraint: ESLint 9 is deprecated by its maintainer, but the installed Next.js React/accessibility plugins declare ESLint support through version 9. It is pinned to the latest 9.x release compatible with that dependency tree. Revisit when those plugins support ESLint 10; do not bypass peer checks with `--force` or `--legacy-peer-deps`.

## Deployment boundary

The Neon catalog is initialized; no frontend or backend deployment is configured or authorized in this module. The intended Vercel project root is `frontend/`, with Node 24 and `NEXT_PUBLIC_API_BASE_URL` set to the HTTPS FastAPI origin before building. The intended Render root is `backend/`, with Python 3.12 and backend-only settings, including the same Neon URLs used locally. Runtime support was checked against [Vercel's Node documentation](https://vercel.com/docs/functions/runtimes/node-js/node-js-versions) and [Render's Python documentation](https://render.com/docs/python-version). Deployment commands, validated hosted origins, provider secrets and deployment verification belong to later modules.
