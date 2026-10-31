# Local development

The backend (FastAPI) and frontend (Next.js) run on `127.0.0.1` against the shared Neon database. There is no local PostgreSQL server and no environment-mode switch. Variable details are in [configuration](configuration.md).

## Conda environment

Use the dedicated `talent-insight` environment for both Python and Node. Do not install project packages into Conda base or create a virtual environment.

Create it once per machine, from the repository root:

```bash
conda env create -f environment.yml
```

Activate it in each terminal:

```bash
conda activate talent-insight
```

If a shell profile puts Homebrew's Node first, prepend the environment's runtime for the current shell:

```bash
export PATH="$CONDA_PREFIX/bin:$PATH"
```

- `environment.yml` pins Python 3.12 and Node 24 (patch updates allowed). `.python-version`, `.nvmrc` and the frontend `engines` field record the same versions.
- PostgreSQL server tools are not needed.

## Install dependencies

From the repository root, with the environment active:

```bash
python -m pip install -r backend/requirements-dev.lock
```

```bash
python -m pip install --no-build-isolation --no-deps -e backend
```

Then, from `frontend/`:

```bash
npm ci
```

- `backend/requirements-dev.lock` pins exact runtime, test and build versions; the editable install makes `app` importable.
- Use `npm ci` after cloning. Use `npm install` only for deliberate dependency updates, and change manifest and lock together.

## Local configuration

Optionally copy the examples (they contain placeholders only, and `-n` never overwrites):

```bash
cp -n backend/.env.example backend/.env
```

```bash
cp -n frontend/.env.example frontend/.env.local
```

- Committed defaults live in `backend/app/config.yaml`; secrets go only in the ignored `backend/.env`.
- Precedence, highest first: process variables, `backend/.env`, `config.yaml`. Empty values fall through.
- Unknown keys in `backend/.env` or `config.yaml` (including the retired `APP_ENV`) and invalid values stop startup with a message that never echoes values. Restart after any change.
- The catalog needs `DATABASE_URL`; uploads and screenings need `AI_MODE`. See [configuration](configuration.md).
- This machine's shell profile may export a stale `AWS_BEARER_TOKEN_BEDROCK`, which overrides `backend/.env`. Prefix local Bedrock commands (including `./run_local.sh start`) with `env -u AWS_BEARER_TOKEN_BEDROCK`.

## Start and stop both apps

From the repository root:

```bash
./run_local.sh start
```

```bash
./run_local.sh status
```

```bash
./run_local.sh logs
```

```bash
./run_local.sh restart
```

```bash
./run_local.sh stop
```

- The wrapper activates `talent-insight` (from the current Conda install or `/opt/anaconda3`) and checks Python 3.12, Node 24 and installed dependencies. It never installs anything.
- Backend: `uvicorn app.main:app --reload --no-access-log` on port 8000. Frontend: `npm run dev` on port 3000. Override with `BACKEND_PORT` and `FRONTEND_PORT` (stop the servers first).
- For that run it sets `NEXT_PUBLIC_API_BASE_URL`, `CORS_ALLOWED_ORIGINS` (both `localhost` and `127.0.0.1` frontend origins) and `NEXT_TELEMETRY_DISABLED=1`, unless already exported in the shell. Because process variables win, these replace any value in `backend/.env` or `frontend/.env.local`. To point the frontend elsewhere, export the variable before `start`.
- Readiness checks `/health` and the frontend `/` only; they do not test the database.
- PID records and logs live in the ignored `.run_local/` (owner-only permissions). `logs` follows both logs; Ctrl+C leaves the servers running.
- `stop` signals only processes whose recorded identity still matches. It never kills by port, refuses to start on an occupied port, and leaves unverifiable processes for you to stop manually.
- Verified on macOS only.

## Run each app directly

Backend, from `backend/`:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

Frontend development server, from `frontend/`:

```bash
npm run dev
```

Frontend production build and server, from `frontend/` (same port as `dev`, so stop one first):

```bash
npm run build
```

```bash
npm start
```

- Keep `--no-access-log`; access logs would record request URLs.
- Run this way, nothing sets CORS for you: put the frontend origins in `CORS_ALLOWED_ORIGINS` in `backend/.env`.
- The frontend's `/` and `/guide` need no backend. `/jobs` pages need the backend, matching CORS origins and `DATABASE_URL`.
- Synthetic candidates show a saved assessment snapshot with no provider call. PDF uploads use `AI_MODE`: `bedrock` makes paid calls, `mock` is free. Uploads and results are temporary; see [resumes](resumes.md) and [assessment UI](assessment-ui.md).
- Text screenings need `AI_MODE` and a `SESSION_SIGNING_SECRET` of 32+ characters. `VOICE_MODE=mock` (with `VOICE_PUBLIC_API_URL=http://127.0.0.1:8000`) exercises the consent flow but cannot open a real call. Live voice needs a public HTTPS backend that Deepgram can reach, such as the Render service. See [voice sessions](voice-sessions.md) and [deployment](deployment.md).
- Backend log format and request IDs are in [backend foundation](backend-foundation.md#request-ids-and-application-logs).

## Checks

Backend, from `backend/`:

```bash
python -m pytest -W error
```

```bash
python -m ruff check .
```

```bash
python -m ruff format --check .
```

```bash
python -m pip check
```

```bash
python -m app.seed --validate-only
```

```bash
python -m app.refresh_demo
```

- The default test suite needs no database, provider or server: it isolates real configuration, uses in-process ASGI requests, mock AI mode and stubbed AWS calls, and previews migration SQL offline.
- `app.seed --validate-only` validates the catalog JSON without loading settings or connecting.
- `app.refresh_demo` without `--run` only checks that each demo job has 3–5 memberships; it makes no provider call and does not touch the snapshot. `--run` regenerates the snapshot with paid Bedrock calls and needs approval.
- The demo snapshot is guarded by `tests/test_candidates.py::test_versioned_snapshot_is_served_for_every_demo_member`, which fails when code under `app/pipeline`, `app/llm`, `app/prompts` or `refresh_demo.py` changes.
- Optional read-only Neon checks: `python -m pytest --neon -W error`. See [database](database.md#verification).

Frontend, from `frontend/`:

```bash
npm run lint
```

```bash
npm run typecheck
```

```bash
npm test
```

```bash
npm run build
```

- `typecheck` runs `next typegen` before `tsc`, so a fresh checkout needs no stale generated types.
- `npm test` runs Node's built-in test runner on `tests/*.test.ts` (API decoding, URL validation, ordering, caching, screening and voice helpers) with no network calls.

Launcher, from the repository root:

```bash
bash -n run_local.sh
```

```bash
python -m unittest discover -s scripts -p 'test_*.py'
```

```bash
python -m ruff check scripts
```

```bash
python -m ruff format --check scripts
```

The launcher tests mock processes and ports; they start no servers.

## Limitations

- Frontend scripts use Webpack (`--webpack`). Turbopack could not bind its worker socket in this environment.
- ESLint is pinned to 9.x because the Next.js React and accessibility plugins declare support only up to 9. Do not bypass peer checks with `--force` or `--legacy-peer-deps`.
- The backend lock and launcher are verified on macOS arm64. Hosted builds are covered in [deployment](deployment.md); Windows is untested.
