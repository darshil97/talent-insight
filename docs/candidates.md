# Candidates

Each job has a read-only pool of synthetic candidates, with profiles and precomputed demo assessments. There are no workflow stages or recommendations. For uploads, see [assessment UI](assessment-ui.md).

## Demo data

`backend/app/fixtures/candidates.json` holds 12 synthetic candidates in 13 memberships: three per role, plus one Backend Engineer candidate who is also in the Senior Data Scientist pool.

Each candidate has:

- a stable `demo_...` `id`;
- `display_name`, `headline` and `summary`, which must appear verbatim in `resume_text`;
- `claims`: curated excerpts (`kind` of `skill`, `experience` or `qualification`, plus `label` and `quote`). The quote must be in the resume and the label in the quote;
- optional `availability`: `{"status": "immediate"}`, `{"status": "serving_notice", "last_working_day": "YYYY-MM-DD"}`, `{"status": "not_serving", "notice_days": 30}`, or `null`. See [ranking](scoring.md#availability-and-ranking);
- `memberships`, for example `[{"job_id": "demo_ds", "demo_scenario": "partial"}]`.

`demo_scenario` (`strong`, `partial`, `weak`, `transferable`, `ambiguous` or `incomplete`) is private authoring intent. It is not returned by the API and is not a score target. Membership, not the ID prefix, places a candidate in a job.

`python -m app.seed --validate-only` checks IDs, links, quotes and display context. Every candidate must be in a pool, and each job must have 0 or 3–5 members. Publish as for [jobs](jobs.md#job-definitions).

## API

| Route | Response |
| --- | --- |
| `GET /jobs/{job_id}/candidates` | `{"job": JobDetail, "candidates": CandidateTableSummary[]}` |
| `GET /jobs/{job_id}/candidates/{candidate_id}` | `{"job": JobDetail, "candidate": CandidateDetail, "availability": Availability, "assessment": Assessment \| null}` |

- Candidates load only through `job_candidates` membership.
- **Errors:** a missing job, or a candidate outside the job, returns 404; invalid IDs return 422; database failure returns 503.
- Responses are `no-store`.
- **List rows** (alphabetical; the UI re-sorts):
  - `id`, `display_name`, `headline`, `summary`, `is_demo`;
  - `stated_experience`: the first experience claim's label, a source claim rather than verified years;
  - `snapshot_available`, `match_score`, `score_lower`, `score_upper`, `match_estimate`, `confidence`, `availability`, `ranking_score`. The score fields are `null` without a current snapshot.
- **Detail** adds `resume_text`, `claims` (`kind`, `label`, `quote`, `start`, `end`) and `offset_unit: "unicode_code_point"`. The shapes are in [scoring](scoring.md).
- **Provenance:** before returning, the backend checks that the display context is in the resume and that each claim's exact slice equals its quote and contains its label. Invalid data fails with a safe 500, and no resume text goes into errors or logs.
- **Offsets:** zero-based Unicode code points with an exclusive end. The frontend checks them again with code-point slicing.

## Pages

- **Pool** (`/jobs/<job_id>/candidates`):
  - Columns: name, title, stated experience, match estimate with confidence ("Pending snapshot" when none), availability, source (Demo or Temporary), **Start** screening and **View ↗**.
  - Rows sort by `ranking_score`, highest first, with ties by name. Rows without a score follow.
  - The [upload](assessment-ui.md) lives here.
- **Profile** (`/jobs/<job_id>/candidates/<candidate_id>`):
  - availability (self-reported, used only for ranking) and the authored summary;
  - the [screening panel](voice-sessions.md);
  - excerpts by kind, with **View in source resume** highlighting the exact span in the full resume;
  - the [precomputed assessment](assessment-ui.md#demo-profiles).
- Text renders literally, so HTML and embedded instructions are inert.
- An empty excerpt group is not a finding that a requirement is unmet.
- Neither page calls an AI provider.

## Demo assessment snapshot

`backend/app/fixtures/assessments.json` holds one Bedrock assessment per membership. At runtime, `cached_for_candidate` serves an entry only when all of these hold:

- its fingerprint and digest match;
- its job and source equal the current ones;
- its mode is `bedrock`.

Otherwise the pool shows "Pending snapshot".

- **Fingerprint inputs:**
  - job context (ID, title, skills, requirements);
  - resume text;
  - category weights and middle credits;
  - hashes of every `.py` and `.md` file in `app/pipeline`, `app/llm` and `app/prompts`, plus `app/refresh_demo.py`.
- **Invalidation:** any code or prompt change invalidates every entry. Availability is not included.
- **Neon must match the fixtures:** the API compares entries with Neon, but the refresh reads the JSON fixtures.
- **Test guard:** `tests/test_candidates.py::test_versioned_snapshot_is_served_for_every_demo_member` fails when the snapshot no longer matches, for example after a pipeline or prompt change.

### Refreshing

```sh
python -m app.refresh_demo         # checks 3–5 memberships per job only; no provider calls
python -m app.refresh_demo --run   # paid: needs AI_MODE=bedrock and approval
```

- **Without `--run`:** the command does not validate the snapshot, and `AI_MODE` has no effect.
- **With `--run`:** makes two to four Bedrock calls per membership. It replaces the file atomically only if all succeed, and never touches Neon.
- **Failures:** the old file stays. Validated work is kept in the Git-ignored files `fixtures/.extractions-progress.json` and `fixtures/.assessments-progress.json`. Rerunning resumes from them after rechecking, and success deletes them.
- Never hand-edit these files.

## Limits

- Demo last working days are fixed dates. Once one passes, that candidate counts as available now.
- Displayed availability can be up to 60 seconds old because catalog reads are cached.
