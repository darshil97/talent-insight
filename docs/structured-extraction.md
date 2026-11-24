# Structured extraction and the AI layer

Extraction turns resume text into job-related text mentions ("facts") with verified source quotes. This page also covers the AI layer shared with interpretation. For judging and scoring, see [scoring](scoring.md).

## Route and response

`POST /jobs/{job_id}/resumes/structure` takes a raw PDF and runs five steps:

1. Load the job context; the read-only transaction closes before AI work.
2. [Bot check](resumes.md#bot-check-and-daily-limit) when Turnstile is configured.
3. AI admission.
4. [PDF parse](resumes.md).
5. Extraction.

The UI uses `POST /jobs/{job_id}/resumes/assess`, which adds interpretation. Clients cannot supply criteria, prompts or provider settings. Demo resumes are extracted only by the [snapshot refresh](candidates.md#refreshing).

`StructuredResume` (`no-store`):

- `job`: the only context the model sees: `id`, `title`, `skills` and `requirements`.
- `source`: `kind` (`uploaded_pdf` or `synthetic_demo`), `candidate_id` (demo only) and `pages`. A demo resume is one page.
- `mode` (`mock` or `bedrock`) and `model_id` (`null` in mock).
- `facts`: `kind` (`skill`, `experience`, `qualification` or `project`), a literal `value` and 1–3 `evidence` items `{page_number, quote, start, end}`.
- `identity`: `{name, current_title}`, each a verified `{value, page_number, start, end}` or `null`.
- `unknown_categories`: kinds with no facts. This is not evidence of absence.
- `offset_unit: "unicode_code_point"` and `notice`.

## Verification

The backend computes every offset (page-local code points, exclusive end) and ignores model offsets.

- **Quotes** (`app/pipeline/evidence.py`): an exact unique match is tried first. Otherwise the match runs after normalizing whitespace, compatibility characters (`ﬁ`, non-breaking spaces) and typographic quotes and dashes. The match must be unique on its page. The stored quote is always the original source text.
- **Values** must appear as a whole phrase in a verified quote.
- **Dropping facts:** each fact is checked on its own and dropped if:
  - its shape or kind is invalid;
  - its value is over 200 characters;
  - no quote verifies (missing, ambiguous, over 1,200 characters or on a nonexistent page);
  - its value is not in a quote;
  - it duplicates an earlier `(kind, value)`.

  Quotes beyond three and facts beyond 40 are dropped. Nothing is repaired. Only a response with no `facts` array fails.
- **Prompt guidance:** at most 12 facts. Applied-use quotes are preferred over skills-list lines, transferable evidence is included, and "not stated"-style lines are skipped.
- **Identity:** the name and title are kept only when found in the source (at most 120 and 160 characters). They are display-only: never sent to interpretation, scored or logged. Contact details and personal traits are never requested.
- **Limits of verification:** it proves where text came from, not truth or competence. A mention can be negated in its own quote.

## AI modes

`AI_MODE` is `mock` or a registered provider (`bedrock`). Unset, AI routes return `ai_not_configured`; the catalog and `/resumes/extract` still work. Credentials alone never enable inference, and failures never fall back to mock.

- **`mock`:** the first unique source line mentioning each job skill becomes a literal skill fact, and every requirement is judged `unknown`. No network is used. This is not an AI assessment.
- **`bedrock`:** `langchain-aws` `ChatBedrockConverse` running in the API process. The current setup is `openai.gpt-oss-120b-1:0` in `ap-southeast-2`.
  - Credentials come from `AWS_BEARER_TOKEN_BEDROCK` (passed as `api_key`), an AWS profile or access keys. They never reach responses, logs or the frontend.
  - One client is cached per settings value.
- **`BEDROCK_STRUCTURED_METHOD`:**
  - `json_schema` (default) uses native structured output and repeats the schema in the system prompt;
  - `function_calling` requires exactly one call to the declared tool, which is never executed.

  Pydantic and source checks are always authoritative.

Variables are listed in [configuration](configuration.md).

## Code layout

- **`app/prompts/`:** Jinja system prompts (`StrictUndefined`) for extraction and interpretation, plus shared `_partials/`. Limits are rendered from `app/pipeline/contracts.py`.
- **`app/llm/`:**
  - `base.py`: the `LLMProvider` protocol and `register_provider`;
  - `providers/bedrock.py`: the only adapter;
  - `factory.py`: the cached chat model;
  - `invoke.py`: one structured call, logging tokens and timing;
  - `response.py`: JSON capture.
- **`app/pipeline/`:** `contracts`, `evidence`, `attempts`, `extraction`, `interpretation`, `scoring`, `assessment`.
- **Templating:** only instructions are templated. The human message is a JSON payload (`job_context`, `untrusted_resume_pages` and, for interpretation, `verified_text_mentions`), so resume text never becomes template input or instructions.
- **Snapshot:** changing anything here invalidates the [demo snapshot](candidates.md#demo-assessment-snapshot).

**Adding a provider:**

1. Create `app/llm/providers/<name>.py`. `build` must return a LangChain chat model with SDK retries off, and `error_code` must map SDK errors to the [public codes](#errors).
2. Call `register_provider(...)` and import the module in `providers/__init__.py`.
3. Add settings under `ai.<name>` in `config.yaml` with matching `Settings` and `_yaml_fields` entries, plus placeholder secrets in `.env.example`.
4. Extend the frontend decoder, which accepts only `mock` and `bedrock`.

## Attempts, limits and admission

- **Input:** job context plus page text must fit in 20,000 characters, and the interpretation payload (which adds the facts) is checked again. Larger input returns 413 `ai_input_too_large`, with no truncation and no call.
- **Output:** at most 8,192 tokens per attempt, at temperature 0.
- **Attempts per stage:** extraction and interpretation each get up to two attempts within one 130 s deadline. A retry runs when:
  - the provider throttles or times out;
  - the response is unusable (cut off, unfinished, not one JSON object, or no root array);
  - more than half the items failed: unverified facts, or requirements forced to `unknown`.

  Access, configuration, capability and general unavailability errors are not retried.
- **Retry hints:** up to ten server-written hints naming locations and failed checks, never model output or resume text.
- **Result:** the better attempt is kept, and a usable first attempt survives a failed retry or the deadline.
- **SDK settings:** 3 s connect timeout, a read timeout of up to 60 s, and one SDK attempt. A call already in flight runs until its read timeout even after the request gives up.
- **Admission:** checked per process before the upload is read. One request counts once, whatever its attempts. Counters reset on restart and are not a cost budget.
  - 1 concurrent request (`ai_busy`);
  - 5 per rolling minute (`ai_rate_limited`);
  - 100 per rolling 24 hours (`ai_daily_limit`, `AI_ASSESSMENTS_PER_DAY`). Only requests that passed the bot check and were admitted count.
- **Cost:** an upload assessment makes two to four Bedrock calls.
- **JSON capture** (`app/llm/response.py`):
  - Drops reasoning blocks.
  - Accepts strict JSON, a code fence, the first complete object inside prose, a duplicated root brace, or one wrapper level.
  - Never completes partial JSON.

## Errors

| Status | Codes |
| --- | --- |
| 403 | `bot_check_failed` |
| 413 | `ai_input_too_large` |
| 429 | `ai_rate_limited` (`Retry-After: 60`), `ai_daily_limit` (`Retry-After: 3600`) |
| 502 | `invalid_model_output`, `invalid_evidence`, `invalid_interpretation` |
| 503 | `ai_not_configured`, `provider_configuration_error`, `provider_access_denied`, `unsupported_model_capability`, `ai_unavailable`, `provider_throttled`, `ai_busy` (the last two with `Retry-After: 5`), `bot_check_unavailable` (`Retry-After: 30`) |
| 504 | `provider_timeout`, `ai_timeout` |

Messages never include credentials, resume text or provider payloads. A failure never becomes an empty profile or a zero or perfect match. [PDF errors](resumes.md#errors) and 404 can also occur.

## Privacy and limits

- Upload text reaches Bedrock only through `structure` and `assess` in Bedrock mode.
- Nothing from an upload is saved to files, Neon, browser storage or routine logs. Each Bedrock call for an upload adds a counts-only usage row (stage, model, tokens, latency, outcome); see [data retention](data-retention.md).
- LangSmith and LangChain tracing are forced off, LangChain caching is off, and reasoning blocks are discarded.
- Bedrock retention and AWS invocation-logging settings are outside the app; see [provider research](provider-research.md).
- Prompt boundaries, schemas and quote checks reduce prompt-injection risk but do not eliminate it. People review every result.
- Default tests are offline: they use botocore's Stubber, isolate dotenv and AWS credentials, and never call Bedrock or write Neon. For a free manual check, run the backend with `AI_MODE=mock`.
