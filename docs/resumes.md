# Temporary resume PDF extraction

Module 8 added anonymous text-based PDF extraction. Its standalone `/resumes/extract` API remains available without a provider. Module 11 changes the job-page action to the separate [assessment API and UI](assessment-ui.md), which interprets requirements when configured. Neither action creates a candidate. All uploaded content, including embedded instructions and HTML, remains untrusted text.

## HTTP contract

- `GET /resumes/limits` returns the backend's effective `max_bytes`, `max_pages` and `max_characters` for the upload form.
- `POST /resumes/extract` accepts PDF bytes directly as `Content-Type: application/pdf`. Multipart forms and compressed HTTP bodies are rejected. No filename, job ID or candidate ID is required or retained. The endpoint works without database or provider configuration.
- Success returns `source: "uploaded_pdf"`, `page_count`, `character_count`, and `pages: [{page_number, text}]`. Page numbering starts at one; character counts use Unicode code points. Extracted strings retain their whitespace. Blank pages within an otherwise readable document remain present.
- Responses use `Cache-Control: no-store`. Successful extraction also sets `X-Content-Type-Options: nosniff`. CORS explicitly allows GET/POST and Content-Type for configured origins, without browser credentials.

Errors use the existing `{"error":{"code":"…","message":"…"}}` envelope. Messages never contain the filename, submitted text, parser diagnostics or exception details.

| Status | Codes | Recovery |
| --- | --- | --- |
| 400 | `invalid_content_length` | Send a valid body length or a streaming body |
| 408 | `upload_timeout`, `extraction_timeout` | Retry or export a simpler PDF |
| 413 | `payload_too_large`, `too_many_pages`, `too_much_text` | Select a smaller/shorter PDF |
| 415 | `unsupported_media_type`, `invalid_pdf_signature` | Export a PDF and send it with the PDF content type |
| 422 | `empty_upload`, `empty_pdf`, `invalid_pdf`, `encrypted_pdf`, `no_extractable_text`, `pdf_complexity_limit` | Select a valid unencrypted text-based PDF |
| 503 | `resume_busy` | Retry later; `Retry-After: 5` is provided |

The no-text error explicitly covers blank or scanned PDFs without claiming to distinguish them reliably. No OCR is attempted. Mixed text/image documents can return partial extraction; the UI warns about image-only pages and asks the recruiter to verify the original document. A nonempty text layer is not proof of complete or accurate extraction.

## Limits and parser lifecycle

Optional settings are validated at startup; process values override `backend/.env`. The frontend loads effective display limits, while the server enforces them independently.

| Setting | Default | Allowed range |
| --- | --- | --- |
| `RESUME_MAX_BYTES` | 5,242,880 (5 MiB) | 1,024–10,485,760 |
| `RESUME_MAX_PAGES` | 20 | 1–50 |
| `RESUME_MAX_CHARACTERS` | 100,000 | 100–200,000 |
| `RESUME_UPLOAD_TIMEOUT_SECONDS` | 15 | 0.1–60 |
| `RESUME_TIMEOUT_SECONDS` | 10 | 0.1–30 |
| `RESUME_MAX_CONCURRENT` | 2 | 1–4 per API process |

Capacity is reserved before body reads; excess requests are rejected immediately rather than queued. Both declared and actual streaming body sizes are checked. No multipart parser or disk spool is used. A deadline bounds the entire body read.

Each accepted body goes through a disposable Python child using pinned `pypdf==6.19.0`, strict parsing, bounded page/text output and reduced complexity/decompression limits. Individual decoded streams are capped at 4 MiB; page-tree entries/depth and form invocations are bounded. Complex PDFs may be rejected even when file/page/text counts are small. The parent kills and reaps a worker on timeout or task cancellation. Each child disables diagnostic logging/core dumps and has a 30-second CPU ceiling. Linux additionally applies a 512 MiB address-space cap; that Linux behavior has not been executed on this macOS machine. macOS does not provide the same hard address-space bound. Process isolation is not an OS security sandbox or a public-service abuse-control system. Concurrency is per process; multiple API processes multiply capacity. The child is started with a scrubbed environment (`PATH` and Python I/O flags only), so it inherits no AWS, database or other credentials from the API process.

The parser uses the official [pypdf extraction API](https://pypdf.readthedocs.io/en/latest/user/extract-text.html). Its documentation describes extraction memory costs and the limits of extracting text from scans. See the pinned [6.19.0 package release](https://pypi.org/project/pypdf/6.19.0/) for the dependency source.

## Temporary state and privacy

The application does not write uploaded bytes/text into files, Neon, browser storage or routine logs. Filenames and PDF metadata are omitted from the request/result contract. The chosen file is released from frontend state after success; results exist in React memory only. Clear removes the selected file/result/error and focuses the input. Selecting a replacement removes old output. Leaving the job unmounts/aborts the upload view. Refresh and browser pagehide/history restoration clear temporary data. No resume data enters URLs or server-rendered props.

Browser cancellation discards frontend results immediately. If the backend has already received the body, it may finish within its server deadline before observing a disconnected client. The module 8 route does not call AI; the module 11 job-page assessment action uses the backend's configured provider. Module 9's separate [structured-extraction API](structured-extraction.md) also sends text to Bedrock only when that route and provider mode are explicitly used. Application non-persistence is not a secure-memory-erasure guarantee or a statement about OS swap, browser internals, proxy logs or third-party retention. Hosted request logging/body capture must be reviewed before deployment. Plain PDF extraction needs no database, provider, migration, seed or deployment.

## Verification

With `talent-insight` Conda active, run backend `python -m pytest -W error`, Ruff lint/format and `python -m pip check`; run frontend `npm test`, lint, typecheck and Webpack build. Tests are offline; shared Neon checks remain opt-in/read-only.

`backend/tests/test_resumes.py` builds explicitly synthetic PDFs with actual PDF objects, fonts, cross-reference tables, compressed streams and image-only pages. It checks text/page preservation, literal HTML/instructions, blank/mixed/scanned/encrypted/malformed/truncated/zero-page documents, MIME/signature validation, exact byte and page/text limits, chunked bodies with absent/false lengths, slow reads, concurrent admission/recovery, parser timeout/cancellation cleanup and compressed-stream expansion. Frontend tests check typed contracts, Unicode counts, file validation, transport privacy, cancellation and safe errors. Fixtures are generated at test time; no real resumes are committed.

Manual browser checks and final test totals are in `PROJECT_CONTEXT.md`. These are not an automated E2E suite, full accessibility audit, real-resume accuracy evaluation or Linux deployment test.
