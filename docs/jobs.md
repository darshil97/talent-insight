# Jobs

The job catalog is read-only: four synthetic demo roles in Neon, served by FastAPI and shown in the Next.js app.

## Job definitions

Each role is one JSON file in `backend/app/fixtures/jobs/`: `demo_ds` (Senior Data Scientist), `demo_backend` (Backend Engineer), `demo_hr_ops` (HR and Operations Specialist) and `demo_marketing_ops` (Marketing Operations Specialist).

- **Fields:** `id`, `title`, `client`, `description`, `skills`, `screening_criteria`, `questions` (`id`, `text`, `requirement_ids`), `requirements` (`id`, `category`, `description`, `minimum_years`) and `is_demo: true`.
- **Categories:** `mandatory`, `experience`, `preferred` and `qualification`. Only `experience` requirements may set `minimum_years` (0–99).
- **Order:** the order of the requirements is their display order.
- **Provenance:** descriptions are original summaries informed by public [Airbnb](https://careers.airbnb.com/positions/7662244?gh_jid=7662244), [Stripe](https://stripe.com/careers/listing/backend-engineer-developer-end-user-experience-platform/7476555), [ShopBack](https://jobs.lever.co/shopback-2/0d1daa50-91c1-49b7-93d0-42fe23570001) and [Stripe](https://stripe.com/careers/listing/marketing-technology-program-manager/8257939) postings. Client names are invented.
- **Candidates:** they and their job links are in [`candidates.json`](candidates.md).

To edit or add a role:

1. Edit the JSON and keep existing IDs stable. A new role gets a unique `demo_...` ID (lowercase letters, digits and underscores, at most 64 characters) in a file named `<id>.json`.
2. Keep requirement and question IDs unique across all jobs, and point each question's `requirement_ids` at requirements in the same job.
3. Never add real candidate data.
4. Validate offline from `backend/` with `python -m app.seed --validate-only`. This checks IDs, references, quotes and pool sizes without dotenv or a database.
5. Publish with an approved `python -m app.seed`, an atomic upsert (see [database](database.md)). Startup never seeds.
6. Refresh the [demo snapshot](candidates.md#demo-assessment-snapshot); job changes invalidate it.

The app reads only Neon; the JSON is not a runtime fallback. Deleting a file does not delete its rows, so retiring a role needs a separate, reviewed data change.

## API

| Route | Success | Errors |
| --- | --- | --- |
| `GET /jobs` | `{"jobs": [...]}` sorted by title (empty list when none) | 503 |
| `GET /jobs/{job_id}` | One job | 404 missing, 422 invalid ID, 503 |

- **List items:** `id`, `title`, `client`, `description`, `skills`, `is_demo` and `candidate_count`, counted from memberships.
- **Details:** the same without the count, plus:
  - `requirements` (`id`, `category`, `description`, `minimum_years`, `sort_order`);
  - `screening_criteria`;
  - `questions` (`id`, `text`, `requirement_ids`).
- **IDs:** must match `^demo_[a-z0-9_]+$`, at most 64 characters.
- Responses contain no candidates or scores and are `no-store`.
- **Errors:** the [standard envelope](backend-foundation.md). Database failures return a sanitized 503 and invalid stored data a safe 500.
- **Transactions:** every catalog request, including candidate routes, runs in a read-only transaction with a 5-second statement timeout.

## Frontend

- **`/jobs`:** role cards showing the number of synthetic candidates.
- **`/jobs/<id>`:**
  - description, requirements by category (with minimum years), skills, screening focus and questions;
  - **Job details** and **Candidates** tabs.
- **States:** loading, empty (refresh), unavailable (retry) and not found are separate.
- **Missing jobs:** an invalid ID shows the not-found view without a request. Pages fetch in the browser, so `/jobs/<missing>` returns HTTP 200 before showing not found; the API returns 404.

**API client and cache** (all catalog pages):

- `NEXT_PUBLIC_API_BASE_URL` must be a bare origin, HTTPS or loopback HTTP, and defaults to `http://127.0.0.1:8000`. See [configuration](configuration.md).
- Requests send no credentials, skip HTTP caching, reject redirects and time out after 20 seconds.
- Responses are shape-checked before rendering. There is no fixture fallback.
- Catalog GETs for jobs, pools and profiles share in-flight requests and keep validated responses in module memory: 60 seconds, 64 paths.
  - Hovering or focusing a role card, tab or candidate link prefetches.
  - Errors are not cached, **Try again** bypasses the cache, and a reload clears it.
- Uploads, resume limits and availability calls never use this cache.

## Limits

- No admin UI and no automatic sync from JSON to Neon.
- Cached reads can be up to 60 seconds old.
