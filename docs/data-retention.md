# Data retention and logs

Module 15b reviewed where candidate data lives, when it is deleted and what the logs contain. Uploaded resumes, screening transcripts and reports are temporary: nothing about a real candidate is written to Neon, files or browser storage. Neon holds only the synthetic demo catalog and the counts-only usage table.

## Where data lives

| Data | Where it lives | When it is deleted | Sent to |
| --- | --- | --- | --- |
| Uploaded resume PDF | The request, then the PDF parser child process over stdin. Never written to disk. | When the request ends. | No one. |
| Extracted resume text, facts and assessment | Returned to the browser and held in page memory. | Refresh, leaving the page or clearing the upload. | Amazon Bedrock, for extraction and assessment. |
| Signed screening context (uploads) | Browser memory, sent back to start a screening. It holds fact kinds, short values and statuses, never quotes or identity. | Its signature expires after `VOICE_CONTEXT_TTL_SECONDS` (30 minutes). | No one. |
| Screening session: transcript and report | Backend process memory. | At `VOICE_SESSION_EXPIRY_SECONDS` (15 minutes after the start), removed within 60 seconds by the purge timer, even when no request arrives. An unstarted session goes after 3 minutes. A restart drops everything. | Deepgram (voice audio and speech), Amazon Bedrock (interviewer turns and the report). |
| Report on the page | React component state. | Close, refresh or leaving the page. | No one. |
| Bot-check token | Sent once from the browser to the backend, then to Cloudflare. | Single use; valid for 5 minutes. | Cloudflare. The widget itself runs in the visitor's browser and talks to Cloudflare directly. |
| Demo jobs, candidates and assessments | Neon and the packaged snapshot. | Kept: they are synthetic demo data. | Bedrock only when the snapshot is refreshed by hand. |

## Logs

The backend logs codes, counts, timings, model IDs and route templates only, never resume text, transcripts, quotes, names, session capabilities, tokens or secrets. Request lines use the route template (`/screenings/{session_id}/end`), Render runs with `--no-access-log`, and an unhandled error logs only its exception class. Tests check that capabilities, tokens and candidate answers stay out of the app's log records.

**Usage line.** When a screening session is deleted, the backend logs one line of counts:

```text
Screening usage: voice, demo candidate, interviewer, 547 s to last request, 9 answers, 10 interviewer turns, 11 turn requests, 0 reconnects, report built
```

- Mode and candidate kind (`demo` or `upload`).
- How it ended: `interviewer`, `time_limit`, `failure` or `ended_early`; `not_started` if no interviewer turn ran; `not_ended` if it expired while running.
- Seconds from the start to the last request that used the session.
- Candidate answers, finished interviewer turns, all interviewer requests (including replaced ones) and voice reconnects.
- Whether a report was built.

A restart drops sessions without a usage line, and the seconds are a lower bound for voice: Deepgram bills the connection, which a client can hold open after its last request.

**Weekly check.** In the Render logs, search for `Screening usage` and `Screening report` for the past week. Compare the count of voice lines and their seconds with Deepgram's usage page, and the interviewer turns and reports with Bedrock's cost page. A Deepgram total far above the logged seconds suggests a held connection.

## Usage table on Neon

`talent_insight.usage_events` gets one row per metered event, written in the background every 10 seconds (added 2026-11-01, migration `0003_usage_events`). Rows hold counts, timings, model IDs and prices only: no resume text, transcript, quotes, names, session IDs, capabilities, tokens or secrets.

| `category` | `operation` | One row per | Units |
| --- | --- | --- | --- |
| `pdf` | `pdf_parse` | uploaded PDF parse | pages, characters, latency; no model, so no cost |
| `pdf` | `resume_extraction`, `resume_interpretation` | Bedrock call (each attempt) for an uploaded resume | input and output tokens |
| `voice_response` | `interviewer_turn` | interviewer reply, voice or text | input and output tokens, time to first text |
| `response_analysis` | `screening_report` | report call (each attempt) | input and output tokens |
| `deepgram` | `deepgram_session` | voice screening, when its session is deleted | estimated seconds |

Other columns:
- **When and where:** `created_at` (UTC), and `origin`, which is `render` on Render or `local` for a run on another machine, since both use this database.
- **Which call:** `provider`, `model_id`, `region` and `attempt`.
- **How it went:** `outcome` is `ok` or a safe error code. A cut-off interviewer stream is `stopped`. Also `stop_reason`, `latency_ms` and `first_output_ms`.
- **Context:** `screening_mode`, `candidate_kind` and `job_id`.
- **Grouping:** `screening_ref` is a random value shared by one screening's rows, unrelated to its session ID. `request_id` matches the log lines.
- **Details:** a small JSON field. For Deepgram it says how the estimate was made and holds the number of token grants and interviewer turns.

Recording rules:
- Mock calls are not recorded.
- Recording needs `DATABASE_URL` and is on by default. `USAGE_RECORDING=false` turns it off.
- Rows are kept until you delete them.
- If Neon is unreachable, rows are kept in memory and retried, up to 1,000. Other write errors drop the batch with a log line. Rows still queued when the process stops are lost.

**Cost.** `cost_usd` is calculated when the row is written, at the configured prices:
- **Bedrock:** per million tokens, set with `usage.token_prices` in `app/config.yaml` or `USAGE_TOKEN_PRICES`. Each entry is `[model ID, input USD, output USD]`. Current prices, provided by the user from AWS on 2026-11-01:

  | Model ID | Input, per 1M tokens | Output, per 1M tokens |
  | --- | --- | --- |
  | `openai.gpt-oss-120b-1:0` (resume assessment, report) | $0.1545 | $0.6180 |
  | `au.anthropic.claude-haiku-4-5-20251001-v1:0` (interviewer) | $1.10 | $5.50 |

  The IDs must match `BEDROCK_MODEL_ID` and `VOICE_BEDROCK_MODEL_ID` exactly, or rows have tokens but no cost.
- **Deepgram:** per minute, set with `usage.deepgram_minute_price`, default $0.065. That is Deepgram's pay-as-you-go Voice Agent rate with your own LLM, read from deepgram.com/pricing on 2026-11-01. Check it against your plan.
- Changing a price affects new rows only.

**Deepgram is an estimate.** Deepgram bills the browser's connection time, which the backend never sees. The row's seconds run from the screening's start to its last request, a lower bound. For exact minutes, use Deepgram's usage page.

**Example queries** (run in the Neon SQL editor):

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

-- Everything one screening used
SELECT screening_ref, category, count(*) AS events, sum(cost_usd) AS cost_usd
FROM talent_insight.usage_events
WHERE screening_ref IS NOT NULL
GROUP BY 1, 2 ORDER BY 1;
```

## Provider settings

- **Deepgram:** the agent settings send `mip_opt_out: true`, which opts out of Deepgram's Model Improvement Program.
- **Amazon Bedrock:** the app requests no tracing or prompt caching. Check one account setting yourself: in the Bedrock console, **Settings → Model invocation logging** must stay off. If it is on, AWS stores every prompt, including resume text and transcripts, in CloudWatch or S3.
- **LangChain and LangSmith:** tracing is forced off in the Bedrock client.
- **Cloudflare Turnstile:** the backend sends only the secret key and the token, not the visitor's IP address.

## Limits

- Session state and limits live in one process's memory. Several processes would each keep their own sessions and limits.
- Render keeps its logs according to its own plan; the app does not control that retention.
- Provider-side retention is governed by each provider's terms, not by this app.
