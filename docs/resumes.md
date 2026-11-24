# Resume PDF uploads

How the backend receives and parses an uploaded PDF. Uploads are anonymous, temporary and untrusted, including any HTML or embedded instructions. They never create a candidate record.

## Routes

| Route | Purpose | UI |
| --- | --- | --- |
| `GET /resumes/limits` | Effective `max_bytes`, `max_pages`, `max_characters`, and `bot_check_site_key` (public, or `null` when the bot check is off) | Yes |
| `POST /jobs/{job_id}/resumes/assess` | Parse, extract, interpret, score ([scoring](scoring.md)) | Yes |
| `POST /jobs/{job_id}/resumes/structure` | Parse and extract ([extraction](structured-extraction.md)) | No |
| `POST /resumes/extract` | Parse only; needs no job, database or AI; no bot check | No |

- **Request:** raw bytes as `Content-Type: application/pdf`. Multipart and `Content-Encoding` are rejected, and no filename or ID is sent.
- **`/resumes/extract` returns** `{source: "uploaded_pdf", page_count, character_count, pages: [{page_number, text}]}`. Pages start at 1, counts are Unicode code points, whitespace and blank pages are kept, and the response sets `X-Content-Type-Options: nosniff`.
- Responses are `no-store`.

## Errors

These use the [standard envelope](backend-foundation.md). Messages never include the filename, the text or parser details.

| Status | Codes |
| --- | --- |
| 400 | `invalid_content_length` |
| 408 | `upload_timeout`, `extraction_timeout` |
| 413 | `payload_too_large`, `too_many_pages`, `too_much_text` |
| 415 | `unsupported_media_type`, `invalid_pdf_signature` |
| 422 | `empty_upload`, `empty_pdf`, `invalid_pdf`, `encrypted_pdf`, `no_extractable_text`, `pdf_complexity_limit` |
| 503 | `resume_busy` (`Retry-After: 5`) |

- **Order on AI routes:** job lookup (404) → AI configured → bot check → [AI admission](structured-extraction.md#errors) (busy, per minute, per day) → body read and parse → Bedrock. Nothing is read or parsed until the bot check and admission pass.
- **No text:** `no_extractable_text` covers both blank and scanned PDFs. There is no OCR.
- **Mixed documents:** these can extract partially, so compare results with the original.

## Bot check and daily limit

Both AI routes (`/assess` and `/structure`) are guarded against scripted use, because each assessment makes paid Bedrock calls.

- **Bot check:** when both Turnstile keys are set, the request must carry a Cloudflare Turnstile token in the `X-Bot-Check-Token` header (the body is the PDF itself). The token must be minted for the action `resume_assess`; a screening token is refused. A missing, malformed, rejected or expired token gives 403 `bot_check_failed`. If Cloudflare cannot be reached or rejects the backend's secret, the check fails closed with 503 `bot_check_unavailable` (`Retry-After: 30`).
- **Daily limit:** `AI_ASSESSMENTS_PER_DAY` (default 100) uploads are admitted per process per rolling 24 hours. Then 429 `ai_daily_limit` with `Retry-After: 3600`. Failed bot checks and `ai_busy` or `ai_rate_limited` rejections do not count.
- **UI:** the add-candidate panel shows the Turnstile widget when `/resumes/limits` returns a site key, and **Choose PDF** stays disabled until it passes. Tokens work once, so the widget resets after every attempt.
- **Limits:** like the other counters, the daily count is per process and resets on restart.

## Limits and isolation

- **Defaults:** 5 MiB, 20 pages and 100,000 characters; 15 s to receive the body and 10 s to parse; 2 parses at a time per process. See [configuration](configuration.md).
- **Admission:** capacity is reserved before the body is read. Excess requests get `resume_busy` at once, with no queue. The declared and actual sizes are both checked, and nothing is spooled to disk.
- **Child process:** each PDF goes over stdin to a fresh `python -m app.pdf_worker` child running `pypdf==6.19.0` in strict mode. The child:
  - gets only `PATH` and Python I/O flags, so it inherits no credentials;
  - has no logging or core dumps, a 30 s CPU limit and, on Linux, a 512 MiB memory cap;
  - caps decoded streams at 4 MiB, the page tree at 1,000 entries and depth 30, and form invocations at 100.
- **Clean-up:** the parent kills the child on timeout or cancellation and revalidates its output. Complex PDFs can fail even when small.

## Privacy

- Bytes and text are never written to files, Neon, browser storage or routine logs. Results go only to the browser.
- **Usage rows:** each parse adds a counts-only row (outcome, pages, characters, latency) to Neon `talent_insight.usage_events` when usage recording is on. See [data retention](data-retention.md).
- **Cancellation:** the backend may finish a parse the browser has cancelled.
- **Limits of non-persistence:** not storing data is not secure memory erasure. Isolation is not an OS sandbox, and limits are per process.
- **Tests:** `backend/tests/test_resumes.py` generates synthetic PDFs, so no real resumes are committed.
