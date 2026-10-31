# Data retention and logs

Module 15b reviewed where candidate data lives, when it is deleted and what the logs contain. Uploaded resumes, screening transcripts and reports are temporary: nothing about a real candidate is written to Neon, files or browser storage.

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

## Provider settings

- **Deepgram:** the agent settings send `mip_opt_out: true`, which opts out of Deepgram's Model Improvement Program.
- **Amazon Bedrock:** the app requests no tracing or prompt caching. Check one account setting yourself: in the Bedrock console, **Settings → Model invocation logging** must stay off. If it is on, AWS stores every prompt, including resume text and transcripts, in CloudWatch or S3.
- **LangChain and LangSmith:** tracing is forced off in the Bedrock client.
- **Cloudflare Turnstile:** the backend sends only the secret key and the token, not the visitor's IP address.

## Limits

- Session state and limits live in one process's memory. Several processes would each keep their own sessions and limits.
- Render keeps its logs according to its own plan; the app does not control that retention.
- Provider-side retention is governed by each provider's terms, not by this app.
