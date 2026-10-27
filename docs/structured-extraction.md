# Structured resume extraction — module 9

This backend module turns server-read resume text into bounded job-related text mentions with exact source evidence. The upload `/structure` route does not assess whether requirements are met, infer total experience, rank candidates or generate scores/recommendations. The upload `/assess` route and [assessment UI](assessment-ui.md) provide human-reviewable job matching. Synthetic profiles use the manual precompute command and read-only candidate routes.

## API and authoritative context

| Endpoint | Request | Source |
| --- | --- | --- |
| `POST /jobs/{job_id}/resumes/structure` | Raw `application/pdf` bytes | The server reruns module 8 byte/content validation and PDF extraction |

The upload route loads job title, skills and requirements from the shared read-only catalog. Clients cannot provide trusted job criteria, profiles, scores, prompts or provider settings. The read-only transaction is closed before PDF/AI processing. Synthetic demo extraction now runs only through `python -m app.refresh_demo --run` against validated fixture data; the demo POST route was removed. No database writes, schema changes or seeds are involved.

Success contains `job`, `source`, `mode`, `model_id`, `facts`, `unknown_categories`, `offset_unit` and `notice`. `source` contains page text, its kind (`uploaded_pdf` or `synthetic_demo`) and an optional synthetic candidate ID. Synthetic plain-text resumes use one logical source page; this is not a claim about physical PDF pagination. Results and errors use `Cache-Control: no-store`.

Each fact has a `kind` (`skill`, `experience`, `qualification`, `project`), a literal source `value`, and one to three evidence items with `page_number`, `quote`, `start`, `end`. Offsets are page-local Unicode code points with an exclusive end, calculated by the backend; model-supplied offsets are ignored.

Quotes are located by `app/pipeline/evidence.py`. An exact unique match is used directly. Otherwise both the page and the quote are compared after normalizing whitespace runs, compatibility characters (for example the `ﬁ` ligature and non-breaking spaces) and typographic quotes and dashes, because PDF text and model output commonly differ there. The match must still be unique on its page, and **the stored quote is always the original source substring at the computed offsets**, never the model's wording. The value must occur as a complete phrase (with the same normalization) in at least one verified citation.

Each fact is verified independently (`salvage_facts`). A fact is discarded, with a recorded reason, when its kind or shape is invalid, its value exceeds 200 characters, none of its quotes verifies (missing, ambiguous, over 1,200 characters or on a nonexistent page), its value is not in a verified quote, or it repeats an earlier `(kind, value)`. Extra citations beyond three and facts beyond the hard cap of forty are dropped; unknown extra fields are ignored and never used. Nothing is repaired into evidence: a discarded fact simply leaves its category unknown unless another fact verifies. Only an unusable response shape (no `facts` array) fails the whole attempt. The model is asked for at most twelve strong, requirement-focused facts. Omitted evidence remains unknown.

These checks establish where text came from, not its truth, semantic correctness or candidate competence. A skill mention may be negated or qualified in its quote. Review the source wording. `unknown_categories` is derived from categories with no extracted facts; it is not evidence that the candidate lacks them. No per-requirement status or scoring denominator is defined here.

### Candidate name and current title (display only)

Since 2026-10-27 the extraction output also has `identity: {name, current_title}`, each copied exactly from the resume or an empty string. The backend keeps a value only when it occurs in the source (whitespace and typography normalized, first occurrence, stored as the exact source span with page and offsets); anything else becomes `null`. `StructuredResume.identity` is a display aid for uploads: it is never included in the interpretation payload, never used in scoring and never logged (logs record only how many identity fields verified). Mock mode returns no identity. Contact details and personal traits are still never extracted. The extraction prompt also prefers quotes showing a skill applied in a role or project over skills-list lines, and captures evidence a recruiter would consider transferable to a requirement.

## Provider selection and credentials

`AI_MODE` must be explicitly `mock` or the name of a registered LLM provider (currently `bedrock`). If absent, structured extraction returns `ai_not_configured`; health, catalog and plain PDF extraction still work. Presence of a key never silently enables inference. Provider failures never fall back to mock results.

- `mock` returns clearly labeled literal job-skill mentions from the actual source. It invents no experience, qualifications, projects or excerpts, and is not an AI assessment. It needs no AWS credentials/network.
- `bedrock` runs `langchain-aws` `ChatBedrockConverse` in the API process using a configured model/region and the backend AWS credentials or `AWS_BEARER_TOKEN_BEDROCK`. The token is passed as the client's `api_key`, which installs a static bearer-token provider on that client's own botocore session; the process environment is not mutated. One client is built and cached per effective settings value, so connections are reused. No credentials reach responses, URLs, logs or frontend code. The PDF parser child receives a scrubbed environment (`PATH` and Python I/O flags only) so it inherits no credentials.

The user's selected and locally verified configuration is `AWS_REGION=ap-southeast-2`, `BEDROCK_MODEL_ID=openai.gpt-oss-120b-1:0`, `BEDROCK_STRUCTURED_METHOD=json_schema`. These non-secret selections and `AI_MODE=bedrock` are saved in the ignored, mode-0600 `backend/.env`, preserving existing database URLs and the user-provided token. The example file contains placeholders only. An expired or insufficiently permitted key produces a safe service error. No permissions, account resources or regional infrastructure were changed.

`BEDROCK_STRUCTURED_METHOD` is fixed per configuration: `json_schema` requests native Converse output configuration; `function_calling` requests the declared extraction tool and validates exactly one matching call without executing it. There is no runtime switch between methods. Native mode also states the exact schema in the system prompt. Pydantic validation and provenance checks are always authoritative: no claim of provider-enforced schema guarantees is made for this selected model. The selected model's initial native responses failed schema checks; tool-output experiments returned no accepted tool result. Explicit schema instructions plus native output configuration produced a successful, source-verified result. Other models/profiles/methods require their own checks.

## Code layout, prompts and adding a provider

| Path | Responsibility |
| --- | --- |
| `app/prompts/loader.py` | `load_prompt(category, name, **context)`: Jinja `PackageLoader` with `StrictUndefined`, so a missing variable fails |
| `app/prompts/extraction/system.md`, `interpretation/system.md` | Sectioned system instructions (`TASK`, `INPUT`, `SECURITY`, definitions, `RULES`, `OUTPUT FORMAT` with schema and a placeholder-only shape); limits are rendered from the constants in `app/pipeline/contracts.py` |
| `app/prompts/_partials/` | Shared untrusted-input rules, output-format instructions per method, and the retry `repair.md` list |
| `app/llm/base.py` | `LLMProvider` protocol (`check`, `model_id`, `structured_method`, `build`, `error_code`) and the `register_provider` registry |
| `app/llm/providers/` | Provider adapters; `bedrock.py` is the only one. Importing the package registers them |
| `app/llm/factory.py` | `ensure_ai_configured`, cached `get_chat_model(settings)` |
| `app/llm/invoke.py`, `response.py` | One structured call with metrics logging; capture of one complete JSON object from model text |
| `app/pipeline/` | `contracts`, `evidence`, `attempts`, `extraction`, `interpretation`, `scoring`, `assessment` |

Only instructions are templated. The human message is the serialized JSON data payload (`job_context`, `untrusted_resume_pages` and, for interpretation, `verified_text_mentions`), so untrusted resume text never becomes template input or instruction text.

To add a provider: create `app/llm/providers/<name>.py` with a class implementing the protocol (`build` returns a LangChain chat model with SDK retries disabled; `error_code` maps SDK exceptions to the public codes below), call `register_provider(<Class>())` at the bottom of the module and import it in `app/llm/providers/__init__.py`. Add its non-secret settings under `ai.<name>` in `config.yaml` with matching `Settings` fields and `_yaml_fields` entries, and secrets as placeholders in `.env.example`. `AI_MODE=<name>` then validates. The frontend assessment decoder still accepts only `mock` and `bedrock` as `structured.mode`, so extend it before serving another provider's results. Changing a provider, prompt or pipeline file changes the demo snapshot fingerprint.

## Limits, retries and privacy

| Setting | Default | Allowed range |
| --- | --- | --- |
| `AI_MAX_INPUT_CHARACTERS` | 20,000 | 100–50,000 |
| `AI_MAX_OUTPUT_TOKENS` | 8,192 per attempt | 256–8,192 |
| `AI_TEMPERATURE` | 0 | 0–1 |
| `BEDROCK_REASONING_EFFORT` | unset (not sent) | `low`, `medium`, `high` |
| `AI_TIMEOUT_SECONDS` | 130 per extraction or interpretation stage, across its attempts | 5–150 |
| `AI_MAX_ATTEMPTS` | 2 | 1–2 |
| `AI_MAX_CONCURRENT` | 1 | 1–2 per API process |
| `AI_REQUESTS_PER_MINUTE` | 5 | 1–20 per API process |

The text cap includes serialized job context plus resume page text; fixed system/schema instructions are additional. Oversized input returns 413 without truncation or a provider call. PDF byte/page/text/read/parser limits remain independently enforced. Capacity is reserved before upload parsing; busy requests return 503 immediately. A rolling 60-second request counter returns 429 with Retry-After. It stores timestamps only; malformed/admitted requests count, and retries share their logical request's quota entry. Counters reset on process restart; multiple API processes multiply these bounds. These are local safeguards, not distributed quotas, authentication or a monetary budget.

Each model call runs in-process through the cached client. Its SDK has a three-second connect timeout, at most a 60-second read timeout (or the configured stage deadline if shorter), one SDK attempt and a connection pool sized to `AI_MAX_CONCURRENT`. `app/pipeline/attempts.py` enforces one deadline per extraction or interpretation stage across its attempts. On timeout or client disconnect the awaiting request stops immediately, but the SDK call already in a worker thread cannot be killed; it ends when its read timeout expires, after the admission slot has been released. A full upload assessment runs the two stages sequentially; the browser allows 360 seconds for the whole request.

A stage makes at most one retry, after a short delay, when the provider is throttled or times out, when the response is unusable (truncated at the token limit, refused, not a single complete JSON object, or missing the root array), or when more than half of the returned items failed validation. Access, configuration and capability failures are not retried. The retry's system prompt lists up to ten server-written hints that name only locations and failed checks (for example `facts[2].evidence[0]: quote does not appear verbatim on the cited page`); they never contain model output or resume text. The better of the two attempts is kept, and a usable first attempt is returned if the retry fails or the deadline expires.

The JSON reader (`app/llm/response.py`) joins text blocks and ignores reasoning blocks. It accepts strict JSON, the contents of a Markdown code fence, the first complete object surrounded by prose, the previously observed duplicated root brace, and one level of wrapping around the root key. It never completes partial JSON, and a response stopped at the token limit is rejected before parsing. Function-calling mode still requires exactly one call to the declared tool and validates its original arguments.

Uploaded raw text is sent to Bedrock only through the explicit upload structure/assessment routes in Bedrock mode. Module 8's `/resumes/extract` remains local PDF parsing and never calls AI. No uploaded resume/profile/provider output is saved to application files, Neon, browser storage or routine logs. The separate manual demo refresh stores only synthetic source text and validated assessment output in a versioned JSON snapshot. Prompt caches are not requested, LangSmith/LangChain tracing environment flags are forced off when a Bedrock client is built, and the automatically installed LangSmith pytest plugin is disabled in project test options. Model reasoning blocks are discarded rather than returned. SDK/package dependencies include LangSmith transitively; its presence is not authorization to trace data.

Application non-persistence does not establish AWS retention, account invocation-logging settings, proxy behavior or legal compliance. Those settings remain unverified. Use synthetic data for integration checks until real-document privacy/retention review is complete. Prompt boundaries, strict schemas and quote checks limit several injection failures but do not prove model semantic reliability or complete resistance to instructions embedded in a resume. Humans review all results.

## Errors and review

Existing safe PDF/catalog errors are preserved. Structured failures use the standard error envelope with safe codes:

- 413: `ai_input_too_large`.
- 429: `ai_rate_limited`.
- 502: `invalid_model_output`, `invalid_evidence`, `invalid_interpretation`.
- 503: `ai_not_configured`, `provider_configuration_error`, `provider_access_denied`, `unsupported_model_capability`, `ai_unavailable`, `provider_throttled`, `ai_busy`.
- 504: `provider_timeout`, `ai_timeout`.

No message includes credentials, resumes, provider payloads or exception details. An unavailable extraction is not converted into a zero/perfect match or an empty successful profile.

For offline review, start the backend with `AI_MODE=mock` explicitly supplied to its process, then send a synthetic text-based PDF with `Content-Type: application/pdf` to the upload route. The manual `python -m app.refresh_demo` command validates membership counts without provider calls; `--run` performs the Bedrock batch. In the saved Bedrock configuration upload POSTs consume paid inference. Ordinary browser job/profile reads do not. Restart the backend after changing settings.

Default tests remain offline and isolate the real dotenv/AWS credentials. They validate all twelve synthetic mock profiles, Unicode/ambiguous/whitespace/ligature quotes, per-fact and per-judgment salvage, unknown categories, forged output/instructions, retry hints and best-attempt selection, bounded timeout/cancellation, prompt rendering, provider registration, JSON capture, catalog membership, source corruption, raw-PDF contracts, no-store/CORS, admission/rate limits, and the actual LangChain/SDK serializers with Stubber. No test resets or writes Neon. See `PROJECT_CONTEXT.md` for final totals and exact live verification; no automated test invokes paid Bedrock.
