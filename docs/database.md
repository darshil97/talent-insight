# Database

The Neon project `talent-insight` is the only database, for local and hosted runs. There is no local PostgreSQL server and no per-environment branch.

| Item | Value |
| --- | --- |
| Neon project | `talent-insight` (`<NEON_PROJECT_ID>`) |
| Branch | `production` (`<NEON_BRANCH_ID>`), the single shared branch |
| Database | `neondb`, PostgreSQL 18, AWS us-east-2 |
| Schema | `talent_insight` |
| Migration head | `0004_usage_candidate_ref` |

## Connection

- `DATABASE_URL` (pooled) is used by the app and seeding; `DIRECT_DATABASE_URL` (non-`-pooler`) by Alembic. Both are secrets in `backend/.env` or the Render environment, never in the frontend. See [configuration](configuration.md).
- URLs must be PostgreSQL with host, user and database; remote hosts need `sslmode=require`, `verify-ca` or `verify-full`.
- App engine: created lazily, pool of 5 with no overflow, pre-ping, hidden SQL parameters, 10-second connect timeout. Alembic uses `NullPool`.

## Reads and writes

- Catalog routes read in a read-only transaction with a 5-second statement timeout. Runtime reads use Neon, never the JSON fixtures.
- The app writes only `usage_events`: counts, timings, model IDs and prices, never candidate content. Rows queue in memory and are inserted every 10 seconds; a clean shutdown writes them once more, and a crash loses them. Recording needs `DATABASE_URL` and stops with `USAGE_RECORDING=false`. Columns and queries are in [data retention](data-retention.md).
- Uploaded candidates, resumes, transcripts, reports and scores are never stored.

## Schema

| Table | Contents | Rows |
| --- | --- | --- |
| `jobs` | Synthetic roles, skills, screening criteria, questions | 4 |
| `job_requirements` | Requirements by category (`mandatory`, `experience`, `preferred`, `qualification`), year thresholds, order | 24 |
| `demo_candidates` | Synthetic profiles, resume text, evidence claims, optional availability | 12 |
| `job_candidates` | Job memberships with an internal scenario label | 13 |
| `usage_events` | Metered events, insert-only | grows |

- Constraints enforce demo-only rows, non-empty text, JSON shapes, categories and valid availability combinations. Alembic's revision is in `public.talent_insight_alembic_version`.
- Scenario labels (`strong`, `partial`, `weak`, `transferable`, `ambiguous`, `incomplete`) are fixture metadata, not scores.
- `0001_demo_catalog` creates the schema and catalog tables, failing if `talent_insight` already exists.
- `0002_candidate_availability` adds nullable `notice_status`, `last_working_day` and `notice_days` (0–365) to `demo_candidates`; all null means not provided. See [candidates](candidates.md).
- `0003_usage_events` adds `usage_events`, indexed on `created_at` and `(category, created_at)`.
- `0004_usage_candidate_ref` adds the nullable `usage_events.candidate_ref`.

## Fixtures and seeding

- Sources: `backend/app/fixtures/jobs/<job_id>.json` (filename must match the ID) and `backend/app/fixtures/candidates.json`, where each candidate lists its job memberships. See [jobs](jobs.md) and [candidates](candidates.md).
- Evidence claims store the original quote and exact character offsets: provenance, not proof of truth.
- `python -m app.seed` validates all fixtures, then upserts by stable ID in one transaction. It never deletes; removals need separate reviewed SQL, such as the already executed [`four-domain-catalog-transition.sql`](four-domain-catalog-transition.sql).

## Commands

From the repository root with the Conda environment active. Preview migration SQL without connecting:

```bash
python -m alembic -c backend/alembic.ini upgrade head --sql
```

Validate fixtures without settings or a connection:

```bash
python -m app.seed --validate-only
```

Inspect Neon read-only:

```bash
python -m alembic -c backend/alembic.ini current
```

```bash
python -m alembic -c backend/alembic.ini check
```

These modify the shared database and need explicit user approval each time:

```bash
python -m alembic -c backend/alembic.ini upgrade head
```

```bash
python -m app.seed
```

Never run downgrade, reset, drop or destructive fixtures against Neon.

## Verification

From `backend/`. The default suite never connects; it validates fixtures and previews migration SQL:

```bash
python -m pytest -W error
```

Opt-in Neon checks run in `SET TRANSACTION READ ONLY` and cover the revision, model/schema parity, memberships and evidence quotes against source resumes:

```bash
python -m pytest --neon -W error
```

Destructive migration paths (downgrade, rollback) are untested because the only database is shared.
