# Talent Insight

An AI recruiting and candidate pipeline assistant for technical recruiters and small recruitment agencies.

Planned workflow: select a curated job, review synthetic candidates, upload a temporary resume, inspect evidence-backed matching, conduct an optional AI voice screening, and review a structured report. A recruiter makes the hiring decision.

**Current status: module 9 complete, awaiting review. Module 8 is approved.** Browse synthetic jobs/candidates and inspect temporary PDF text on a job page. New backend APIs provide explicitly labeled mock extraction or Bedrock extraction with validated source quotes. The selected Bedrock model has passed a small synthetic check; structured extraction is not yet wired into the browser assessment UI. Matching, scoring and screening remain pending.

Use the dedicated Anaconda environment:

```sh
conda env create -f environment.yml
conda activate talent-insight
export PATH="$CONDA_PREFIX/bin:$PATH"
```

Skip environment creation if `talent-insight` already exists. Follow [local development instructions](docs/local-development.md) to install the locked dependencies, run both projects and execute checks. No provider credentials are required for this scaffold.

With dependencies installed, start both local servers from the repository root:

```sh
./run_local.sh start
./run_local.sh status
./run_local.sh stop
```

The launcher activates the existing Conda environment, uses loopback HTTP, and also supports `restart` and `logs`. It never installs packages, migrates, seeds or kills arbitrary processes by port. Job browsing requires the configured shared Neon database; health and the overview do not.

The backend's [health endpoint](http://localhost:8000/health) returns `{"status":"ok"}` once running. API docs are at [localhost:8000/docs](http://localhost:8000/docs), controlled by `DOCS_ENABLED`. There is one application configuration, without development/test/production modes. See the [backend contract](docs/backend-foundation.md) for settings, CORS and errors.

- [Project context and module roadmap](PROJECT_CONTEXT.md): current state, architecture, configuration and next action.
- [Development rules](AGENTS.md): module review gates and repository-wide safeguards.
- [Provider research](docs/provider-research.md): official documentation findings and unresolved integration constraints.
- [Local development](docs/local-development.md): Conda setup, environment boundaries, run commands and verification.
- [Backend foundation](docs/backend-foundation.md): health, settings, CORS and error contracts.
- [Database setup](docs/database.md): verified Neon target, private configuration, schema, seeds and read-only integration checks.
- [Frontend layout](docs/frontend-layout.md): routes, accessibility behavior and module 5 browser checks.
- [Jobs and editable JSON](docs/jobs.md): API contracts, job-file editing, validation and module 6 checks.
- [Candidate pools and profiles](docs/candidates.md): membership boundaries, source provenance and module 7 checks.
- [Temporary resume PDFs](docs/resumes.md): upload API, limits, privacy, parser behavior and module 8 checks.
- [Structured extraction](docs/structured-extraction.md): module 9 APIs, explicit providers, AWS configuration, evidence validation and limits.

The planned stack is Next.js/React/TypeScript/Tailwind on Vercel, FastAPI/Pydantic on Render, Neon Postgres, AWS Bedrock via LangChain, and Deepgram for browser voice. Uploaded personal data will not become permanent demo records.

Work proceeds one module at a time with review between modules. After module 9 review and explicit approval, the next module is matching and deterministic scoring. Neon and a small synthetic Bedrock extraction are verified; real-document accuracy, voice integration and hosted deployment remain unverified.
