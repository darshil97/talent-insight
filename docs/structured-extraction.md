# Structured resume extraction — module 9

This backend module turns server-read resume text into bounded job-related text mentions with exact source evidence. It does not assess whether requirements are met, infer total experience, rank candidates or generate scores/recommendations. The existing job page still provides module 8 PDF text review; the assessment UI remains module 11.

## API and authoritative context

| Endpoint | Request | Source |
| --- | --- | --- |
| `POST /jobs/{job_id}/resumes/structure` | Raw `application/pdf` bytes | The server reruns module 8 byte/content validation and PDF extraction |
| `POST /jobs/{job_id}/candidates/{candidate_id}/structure` | Empty body | The server loads the synthetic resume through actual job membership and revalidates module 7 source provenance |

Both routes load job title, skills and requirements from the shared read-only catalog. Clients cannot provide trusted job criteria, profiles, scores, prompts or provider settings. The read-only transaction is closed before PDF/AI processing. Missing/cross-job candidates return 404; malformed IDs return 422. No database writes, schema changes or seeds are involved.

Success contains `job`, `source`, `mode`, `model_id`, `facts`, `unknown_categories`, `offset_unit` and `notice`. `source` contains page text, its kind (`uploaded_pdf` or `synthetic_demo`) and an optional synthetic candidate ID. Synthetic plain-text resumes use one logical source page; this is not a claim about physical PDF pagination. Results and errors use `Cache-Control: no-store`.

Each fact has a `kind` (`skill`, `experience`, `qualification`, `project`), a literal source `value`, and one to three evidence items with `page_number`, `quote`, `start`, `end`. Offsets are page-local Unicode code points with an exclusive end, calculated by the backend. A quote must occur exactly once on its specified page; ambiguous duplicate quotes are rejected. The value must occur as a complete phrase in at least one citation. Duplicate facts, unsupported fields, ungrounded values and invalid page/range evidence fail closed. At most 40 facts are accepted, with values up to 200 and quotes up to 1,200 characters.

These checks establish where text came from, not its truth, semantic correctness or candidate competence. A skill mention may be negated or qualified in its quote. Review the source wording. `unknown_categories` is derived from categories with no extracted facts; it is not evidence that the candidate lacks them. No per-requirement status or scoring denominator is defined here.

## Provider selection and credentials

`AI_MODE` must be explicitly `mock` or `bedrock`. If absent, structured extraction returns `ai_not_configured`; health, catalog and plain PDF extraction still work. Presence of a key never silently enables inference. Provider failures never fall back to mock results.

- `mock` returns clearly labeled literal job-skill mentions from the actual source. It invents no experience, qualifications, projects or excerpts, and is not an AI assessment. It needs no AWS credentials/network.
- `bedrock` runs `langchain-aws` `ChatBedrockConverse` using a configured model/region and the backend AWS credential chain or `AWS_BEARER_TOKEN_BEDROCK`. Backend dotenv values are passed only to the disposable child environment; the API process environment is not mutated and no credentials reach responses, URLs or frontend code.

The user's selected and locally verified configuration is `AWS_REGION=ap-southeast-2`, `BEDROCK_MODEL_ID=openai.gpt-oss-120b-1:0`, `BEDROCK_STRUCTURED_METHOD=json_schema`. These non-secret selections and `AI_MODE=bedrock` are saved in the ignored, mode-0600 `backend/.env`, preserving existing database URLs and the user-provided token. The example file contains placeholders only. An expired or insufficiently permitted key produces a safe service error. No permissions, account resources or regional infrastructure were changed.

`BEDROCK_STRUCTURED_METHOD` is fixed per configuration: `json_schema` requests native Converse output configuration; `function_calling` requests the declared extraction tool and validates exactly one matching call without executing it. There is no runtime switch between methods. Native mode also states the exact schema in the system prompt. Pydantic validation and provenance checks are always authoritative: no claim of provider-enforced schema guarantees is made for this selected model. The selected model's initial native responses failed schema checks; tool-output experiments returned no accepted tool result. Explicit schema instructions plus native output configuration produced a successful, source-verified result. Other models/profiles/methods require their own checks.

## Limits, retries and privacy

| Setting | Default | Allowed range |
| --- | --- | --- |
| `AI_MAX_INPUT_CHARACTERS` | 20,000 | 100–50,000 |
| `AI_MAX_OUTPUT_TOKENS` | 3,000 per attempt | 256–8,192 |
| `AI_TIMEOUT_SECONDS` | 45 across all attempts | 5–120 |
| `AI_MAX_ATTEMPTS` | 2 | 1–2 |
| `AI_MAX_CONCURRENT` | 1 | 1–2 per API process |
| `AI_REQUESTS_PER_MINUTE` | 5 | 1–20 per API process |

The text cap includes serialized job context plus resume page text; fixed system/schema instructions are additional. Oversized input returns 413 without truncation or a provider call. PDF byte/page/text/read/parser limits remain independently enforced. Capacity is reserved before upload parsing; busy requests return 503 immediately. A rolling 60-second request counter returns 429 with Retry-After. It stores timestamps only; malformed/admitted requests count, and retries share their logical request's quota entry. Counters reset on process restart; multiple API processes multiply these bounds. These are local safeguards, not distributed quotas, authentication or a monetary budget.

Each Bedrock attempt uses a disposable child. Its SDK has a three-second connect timeout, at most a 20-second read timeout and one SDK attempt. The parent enforces one overall deadline, killing/reaping a child on timeout/cancellation. At most one service retry follows invalid schema/evidence or a transient throttle/timeout, with a short delay. Access/configuration/capability failures are not retried. Repair instructions contain no rejected provider output. No truncation, refusal, partial JSON recovery, Markdown wrapping, additional tool calls or unverified quote is accepted as a successful extraction. Linux additionally applies a 768 MiB child address-space cap; Linux execution and that cap remain unverified. macOS has no equivalent hard address-space bound.

Raw text is sent to Bedrock only through the explicit structured-extraction route in Bedrock mode. Module 8's `/resumes/extract` remains local PDF parsing and never calls AI. No resume/profile/provider output is saved to application files, Neon, browser storage or routine logs. Worker diagnostics/core dumps are disabled, prompt caches are not requested, LangSmith/LangChain tracing is explicitly disabled, and the automatically installed LangSmith pytest plugin is disabled in project test options. Model reasoning blocks are discarded rather than returned. SDK/package dependencies include LangSmith transitively; its presence is not authorization to trace data.

Application non-persistence does not establish AWS retention, account invocation-logging settings, proxy behavior or legal compliance. Those settings remain unverified. Use synthetic data for integration checks until real-document privacy/retention review is complete. Prompt boundaries, strict schemas and quote checks limit several injection failures but do not prove model semantic reliability or complete resistance to instructions embedded in a resume. Humans review all results.

## Errors and review

Existing safe PDF/catalog errors are preserved. Structured failures use the standard error envelope with safe codes:

- 413: `ai_input_too_large`.
- 429: `ai_rate_limited`.
- 502: `invalid_model_output`, `invalid_evidence`.
- 503: `ai_not_configured`, `provider_configuration_error`, `provider_access_denied`, `unsupported_model_capability`, `ai_unavailable`, `provider_throttled`, `ai_busy`.
- 504: `provider_timeout`, `ai_timeout`.

No message includes credentials, resumes, provider payloads or exception details. An unavailable extraction is not converted into a zero/perfect match or an empty successful profile.

For offline review, start the backend with `AI_MODE=mock` explicitly supplied to its process, then POST the empty-body synthetic route through the API docs or a local HTTP client. To review the PDF route, send an explicitly synthetic text-based PDF with `Content-Type: application/pdf`. In the saved Bedrock configuration these new POSTs consume paid inference; ordinary browser job/profile reads and the existing upload UI do not. Restart the backend after changing settings.

Default tests remain offline and isolate the real dotenv/AWS credentials. They validate all twelve synthetic mock profiles, Unicode/ambiguous quotes, unknown categories, forged output/instructions, bounded repair/timeout/cancellation, catalog membership, source corruption, raw-PDF contracts, no-store/CORS, admission/rate limits, and the actual LangChain/SDK serializers with Stubber. No test resets or writes Neon. See `PROJECT_CONTEXT.md` for final totals and exact live verification; no automated test invokes paid Bedrock.
