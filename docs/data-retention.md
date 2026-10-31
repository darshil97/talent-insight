# Data retention and logs

Uploaded resumes, screening transcripts and reports are temporary: nothing about a real candidate is written to Neon, files or browser storage. Neon holds only the synthetic demo catalog and the counts-only usage table.

## Where data lives

| Data | Where | Deleted | Sent to |
| --- | --- | --- | --- |
| Uploaded resume PDF | The request, then the PDF parser child process over stdin; never written to disk | When the request ends | No one |
| Extracted resume text, facts and assessment | The response, then page memory | Refresh, leaving the page or clearing the upload | Amazon Bedrock (extraction and assessment) |
| Signed screening context (uploads) | Browser memory; fact kinds, short values and statuses, no quotes or identity | Expires after 30 minutes | No one |
| Screening transcript and report | Backend process memory | 15 minutes after the session is created, within 60 s (purge timer, even with no traffic); an unstarted session after 3 minutes; any restart | Deepgram (voice audio, speech recognition and speech), Amazon Bedrock (interviewer turns and the report) |
| Transcript and report on the page | React state | Close, refresh or leaving the page | No one |
| Bot-check token | Browser → backend → Cloudflare | Single use, valid 5 minutes ([Turnstile](provider-research.md#cloudflare-turnstile)) | Cloudflare; the widget also talks to Cloudflare directly |
| Demo jobs, candidates and assessments | Neon and the packaged snapshot | Kept: synthetic demo data | Bedrock only when the snapshot is refreshed by hand |
| Usage rows | Neon `talent_insight.usage_events` | Kept until deleted by hand | No one |

Session timers and limits: [screening sessions](voice-sessions.md#sessions-limits-and-timers).

## Logs

The backend logs codes, counts, timings, model IDs and route templates only; never resume text, transcripts, quotes, names, capabilities, tokens or secrets.
- Request lines use the route template (`/screenings/{session_id}/end`), and Uvicorn runs with `--no-access-log`.
- Only the `app` logger is configured, so SDK and `httpx` INFO lines (which include URLs) are not shown at the defaults.
- An unhandled error logs only its exception class.

**Usage line.** When a screening session is deleted, the backend logs one line of counts:

```text
Screening usage: voice, demo candidate, interviewer, 547 s to last request, 9 answers, 10 interviewer turns, 11 turn requests, 0 reconnects, report built
```

Fields: mode; candidate kind (`demo` or `upload`); how it ended (`interviewer`, `time_limit`, `failure`, `ended_early`, or `not_started` / `not_ended` if no turn ran or it expired while running); seconds from session creation to the last request that used it; candidate answers; finished interviewer turns; all turn requests including replaced ones; voice reconnects; whether a report was built. A restart drops sessions without a line.

## Usage table on Neon

`talent_insight.usage_events` (migrations `0003_usage_events` and `0004_usage_candidate_ref`) gets one row per paid event. Parsing a PDF runs locally and costs nothing, so it gets no row. Rows hold counts, timings, model IDs and prices only: no resume text, transcript, quotes, names, session IDs, capabilities, tokens or secrets.

| `category` | `operation` | One row per | Units |
| --- | --- | --- | --- |
| `pdf` | `resume_extraction`, `resume_interpretation` | Bedrock call attempt for an uploaded resume | `input_tokens`, `output_tokens` |
| `voice_response` | `interviewer_turn` | Interviewer model reply, voice or text | tokens, `first_output_ms` |
| `response_analysis` | `screening_report` | Report call attempt | tokens |
| `deepgram` | `deepgram_session` | Voice session, when it is deleted (`VOICE_MODE=deepgram` only) | estimated `seconds` |

Other columns: `created_at` (UTC); `origin` (`render` when Render's own `RENDER` variable is set, else `local`, since both use this database); `provider`, `model_id`, `region`, `attempt`; `outcome` (`ok`, a safe error code, or `stopped` for an interviewer stream closed by a newer request or a dropped client), `stop_reason`, `latency_ms`; `screening_mode`, `candidate_kind`, `job_id`; `screening_ref` (a random value shared by one screening's rows, unrelated to its session ID); `candidate_ref` (links one candidate's rows, below); `request_id` (matches the log lines, and is shared by an upload's extraction and interpretation rows, which run in one `/assess` request); `details` (JSON; for Deepgram the estimate method, token grants and interviewer turns); `cost_usd`.

**Recording** needs `DATABASE_URL` and is on by default; `USAGE_RECORDING=false` turns it off ([configuration](configuration.md)). Mock model calls are not recorded, and neither is the paid snapshot refresh (`refresh_demo --run`). Rows queue in memory (at most 1,000) and are written every 10 s and once more on a clean shutdown. If Neon is unreachable they are kept and retried; other write errors drop the batch with a count-only warning. A crash loses queued rows, and sessions still in memory at shutdown get no Deepgram row.

**Cost.** `cost_usd` is calculated when the row is created, from `usage.token_prices` (USD per million input and output tokens, per model ID) and `usage.deepgram_minute_price` in `backend/app/config.yaml`. Current values and their sources: [provider research](provider-research.md#prices). A model ID that is not listed exactly gets tokens but no cost. A price change affects new rows only.

**Linking one candidate's costs.** `candidate_ref` joins a candidate's resume, interview and report rows:
- **Uploaded resume:** `/assess` creates a random `up_…` value, tags its extraction and interpretation rows, and puts the value inside the signed screening context it returns. Every screening started from that context carries it into its interviewer, report and Deepgram rows. Uploading the same PDF again gives a new value.
- **Demo candidate:** the synthetic candidate ID, such as `demo_ds_avery`, so all of that candidate's screenings add up. Demo resume assessments come from the saved snapshot and cost nothing at runtime.
- `screening_ref` still separates individual screenings of the same candidate.

**Deepgram rows are an estimate.** Deepgram bills the browser's connection time, which the backend never sees directly. `seconds` runs from session creation to the browser's hang-up: its first `/end`, or its first text turn after leaving voice (`details.estimate = start_to_hang_up`). If no hang-up arrives, it runs to the session's last request instead (`start_to_last_request`), which misses any time a client holds the connection open. For exact minutes, use Deepgram's usage page.

**Example queries** (Neon SQL editor):

```sql
-- Cost and volume by category and day
SELECT date_trunc('day', created_at) AS day, category, count(*) AS events,
       sum(input_tokens) AS input_tokens, sum(output_tokens) AS output_tokens,
       round(sum(seconds) / 60, 1) AS minutes, sum(cost_usd) AS cost_usd
FROM talent_insight.usage_events
GROUP BY 1, 2 ORDER BY 1 DESC, 2;

-- Tokens and failures by model
SELECT model_id, operation, count(*) AS calls,
       count(*) FILTER (WHERE outcome <> 'ok') AS not_ok,
       sum(input_tokens) AS input_tokens, sum(output_tokens) AS output_tokens,
       round(avg(latency_ms)) AS avg_ms
FROM talent_insight.usage_events
WHERE provider = 'bedrock'
GROUP BY 1, 2 ORDER BY 3 DESC;

-- Total cost per candidate: resume, interview (model and Deepgram) and report
SELECT candidate_ref, candidate_kind,
       sum(cost_usd) FILTER (WHERE category = 'pdf') AS resume_cost,
       sum(cost_usd) FILTER (WHERE category IN ('voice_response', 'deepgram')) AS call_cost,
       sum(cost_usd) FILTER (WHERE category = 'response_analysis') AS report_cost,
       sum(cost_usd) AS total_cost
FROM talent_insight.usage_events
WHERE candidate_ref IS NOT NULL
GROUP BY 1, 2 ORDER BY max(created_at) DESC;

-- Everything one screening used
SELECT screening_ref, candidate_ref, category, count(*) AS events, sum(cost_usd) AS cost_usd
FROM talent_insight.usage_events
WHERE screening_ref IS NOT NULL
GROUP BY 1, 2, 3 ORDER BY 1;
```

**Weekly check.** Compare the `deepgram` minutes with Deepgram's usage page, and the Bedrock rows with AWS's cost page. A Deepgram total far above the estimate suggests a connection held open.

## Provider settings

- **Deepgram:** the agent settings send `mip_opt_out: true`, opting out of Deepgram's Model Improvement Program.
- **Amazon Bedrock:** the app requests no tracing or prompt caching. In the Bedrock console, **Settings → Model invocation logging** must stay off; if it is on, AWS stores every prompt, including resume text and transcripts, in CloudWatch or S3. This is an account setting the owner must check.
- **LangChain / LangSmith:** tracing is forced off whenever a Bedrock client is built.
- **Cloudflare Turnstile:** the backend sends only the secret key and the token, not the visitor's IP address.

## Limitations

- Sessions and limits live in one process's memory; several processes would each keep their own.
- Render keeps its logs according to its plan; the app does not control that.
- Provider-side retention is governed by each provider's terms, not by this app.
