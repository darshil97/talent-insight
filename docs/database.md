# Curated catalog on Neon — module 4

## One shared database

The application uses the existing Neon project **`talent-insight`** for both local backend runs and hosted deployment. There is no local PostgreSQL server and no separate database environment.

Verified target on 2026-10-24:

- Project: `<NEON_PROJECT_ID>` (`talent-insight`).
- Existing branch: `<NEON_BRANCH_ID>`, named `production` by Neon; it is the single shared branch, not an application environment selector.
- Database: `neondb`, PostgreSQL 18.6, AWS us-east-2.
- App schema: `talent_insight`.
- Migration revision: `0001_demo_catalog`.

The earlier OAuth-lock issue is resolved. The database was inspected before initialization: no application tables or app schema existed. The reviewed migration and seed have now been applied. No project, branch or additional database was created. The existing public helper function was left in place.

## Private configuration

The ignored `backend/.env` is configured locally with owner-only permissions. It contains:

- `DATABASE_URL`: the pooled Neon endpoint for runtime catalog access.
- `DIRECT_DATABASE_URL`: the direct endpoint for Alembic operations on the same database.

Connection strings are intentionally omitted from documentation and output. Copy those same values into the hosted backend's secret environment settings when deploying. There is no server deployment yet, and no database URL belongs in frontend configuration. Do not paste credentials into chat.

The backend validates PostgreSQL URLs and requires TLS for remote connections. Credentials use redacted `SecretStr` settings. SQLAlchemy maintains a lazy pool of five connections with zero overflow, health checks, hidden SQL parameters and a ten-second connection timeout. Alembic uses the direct endpoint and `NullPool`. Neither application startup nor `/health` migrates, seeds or checks external readiness. No local-database fallback exists.

See [Neon's pooling guidance](https://neon.com/docs/connect/connection-pooling), [SQLAlchemy's psycopg dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#psycopg) and [Alembic's migration workflow](https://alembic.sqlalchemy.org/en/latest/tutorial.html).

## Schema and seed

| Table | Contents | Initialized rows |
| --- | --- | --- |
| `talent_insight.jobs` | Synthetic roles/clients, descriptions, skills, screening criteria and questions | 4 |
| `talent_insight.job_requirements` | Categorized requirements, experience thresholds and ordering | 24 |
| `talent_insight.demo_candidates` | Synthetic profiles, resume text and traceable evidence claims | 12 |
| `talent_insight.job_candidates` | Fixed job-specific pools and internal synthetic scenario labels | 12 |

`public.talent_insight_alembic_version` tracks the migration. Foreign keys, uniqueness and check constraints protect relationships and basic demo-data integrity. The initial migration refuses to adopt an unknown existing app schema. It does not replace unrelated public tables.

The versioned source is `backend/app/fixtures/catalog.json`. Each role has three candidate profiles; the complete set covers strong, partial, weak, transferable, ambiguous and incomplete evidence. Scenario labels are internal fixture metadata, not calculated match scores or hiring recommendations. Every candidate is marked synthetic. Claims include original quotes and exact character offsets; this validates provenance, not independent truth. No uploaded candidates, transcripts, reports or match scores are stored.

Seeding validates the entire fixture and upserts only its stable IDs atomically. Repeated runs do not duplicate rows; both the initial seed and a repeat have been verified on Neon. Other rows are preserved; there is no automatic delete, truncate or pruning. Removed fixtures and criterion-order restructuring require a reviewed data migration.

Read-only helpers in `app/catalog.py` list jobs, load ordered requirements, list candidate pools and fetch candidates through actual job membership. API/frontend catalog views remain later modules.

## Explicit administration

Activate the Conda environment following [local setup](local-development.md). From the repository root:

```sh
# Preview SQL without connecting.
python -m alembic -c backend/alembic.ini upgrade head --sql

# Inspect the shared database without modifying its catalog.
python -m alembic -c backend/alembic.ini current
python -m alembic -c backend/alembic.ini check
```

The following commands have already initialized this project and are not startup requirements:

```sh
python -m alembic -c backend/alembic.ini upgrade head
python -m app.seed
```

Future migrations/seeding require approval appropriate to the change. Never point destructive tests or reset/downgrade/drop commands at the shared Neon catalog. The existing downgrade function is not invoked by the test suite.

## Verification

From `backend/` in the same Conda environment:

```sh
# Credential-free unit, schema-preview and ASGI checks; Neon checks are skipped.
python -m pytest -W error

# Explicitly include shared Neon checks, all in read-only transactions.
python -m pytest --neon -W error

python -m ruff check .
python -m ruff format --check .
python -m pip check
```

There is no local server fixture or PostgreSQL installation requirement. Default checks isolate application settings and make no database connections. The opt-in Neon tests validate migration revision, schema/model parity, catalog membership and exact source evidence, using `SET TRANSACTION READ ONLY`. They never migrate, seed, alter, reset or delete shared data.

Earlier disposable PostgreSQL regression checks passed before the Neon-only instruction. Those fixtures have been removed rather than redirected to Neon; destructive rollback/constraint-mutation scenarios are not run on the shared database. Current live verification uses actual Neon PostgreSQL 18.6. UI features and AI/provider integrations remain unimplemented or unverified as recorded in the project context.
