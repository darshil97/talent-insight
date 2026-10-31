# Provider research

The record of what provider documentation says, what was observed, and why the current design was chosen. Each finding carries the date it was read or observed; recheck documentation, account access and SDK versions before relying on it. How the app uses these providers: [screening sessions](voice-sessions.md), [structured extraction](structured-extraction.md), [data retention](data-retention.md).

## Deepgram Voice Agent

Sources (read 2026-10-27 unless noted): [Voice Agent reference](https://developers.deepgram.com/reference/voice-agent/voice-agent), [configure the Voice Agent](https://developers.deepgram.com/docs/configure-voice-agent) (2026-11-01), [LLM models](https://developers.deepgram.com/docs/voice-agent-llm-models), [reusable agent configurations](https://developers.deepgram.com/docs/reusable-agent-configurations), [token authentication](https://developers.deepgram.com/guides/fundamentals/token-based-authentication), [regional endpoints](https://developers.deepgram.com/reference/regional-endpoints).

**Protocol.** `wss://agent.deepgram.com/v1/agent/converse`. Browsers authenticate through the WebSocket subprotocol (`["bearer", token]`). The client sends a `Settings` message after `Welcome`; the server sends `SettingsApplied`, `ConversationText`, `UserStartedSpeaking`, `AgentThinking`, `AgentStartedSpeaking`, `AgentAudioDone`, `FunctionCallRequest` and `Error`. Audio completion is not proof that an interview is complete, so the app has its own explicit, idempotent end operation.

**Temporary tokens.** `POST /v1/auth/grant` with the server key (Member permission) takes `ttl_seconds` (default 30, maximum 3600) and returns a JWT documented as `usage:write` for `/listen`, `/speak`, `/read` and `/agent`, excluding management APIs. A token must be valid only when the connection opens, so it does not limit call length or spend. Observed 2026-10-28: the JWT's scope claim was `asr:write`, and the Voice Agent socket accepts it in live calls.

**Why the interviewer is a custom LLM in FastAPI** (decided 2026-10-27):
- **Native Bedrock** (`think.provider.type: aws_bedrock`) takes IAM or STS keys inside `Settings`. The browser sends `Settings`, so every visitor could read them, and the interviewer instructions would be editable in the browser. Not used.
- **Reusable agent configurations** store the `agent` block by UUID, but template variables are plain text, the docs say not to store secrets, and a temporary token is not tied to a stored config, so a client can still send its own `Settings`. Not used.
- **Custom LLM:** `think.provider.type: open_ai` with `think.endpoint` (`url` and a `headers` object), in OpenAI Chat Completions format. `context_length` is configurable only with a custom endpoint, and `mip_opt_out` (default `false`) opts out of the Model Improvement Program. Used, with a per-session capability in the header. Costs: an extra text hop, a public HTTPS backend, and a capability visible to the browser.
- **Undocumented:** the streaming contract, function forwarding and retry behaviour against a custom endpoint. Observed in live calls on Render (2026-10-29 to 10-31): Deepgram calls the URL exactly as given. It can send a newer request while the previous one is still running; when those were rejected it retried about three times, roughly 240 ms apart, and then ended the call (inferred from log timing).
- **Browser SDK:** `@deepgram/agents` 0.2.0 was not used: custom-endpoint and `mip_opt_out` support were undocumented, and its token caching and reconnect behaviour conflicted with the backend. The app has its own small client.

**Regions.** Agent endpoints exist for the general region (`agent.deepgram.com`), EU, Australia (`api.au.deepgram.com`) and India (`api.in.deepgram.com`). Regional grant hosts are unverified; the app uses the general region.

**Usage reporting** (read 2026-11-01; not used by the app):
- `Settings` accepts a top-level `tags` array of strings, "for filtered searching". Tags are limited to 128 characters and 500 unique values a day. Whether agent sessions show tags in usage reports was not tested.
- The Management API's [usage breakdown](https://developers.deepgram.com/reference/manage/usage/breakdown/get), `GET /v1/projects/{project_id}/usage/breakdown`, filters by `start`, `end`, `endpoint=agent` and `tag`, groups by `tags` and other fields, and returns `agent_hours`, `tokens_in`, `tokens_out` and `requests`. The required key permission is not stated. See also [tagging usage data](https://developers.deepgram.com/guides/fundamentals/tagging-your-usage-data).
- By user decision (2026-11-01) the app records a per-session estimate in Neon instead ([data retention](data-retention.md#usage-table-on-neon)).

## Amazon Bedrock

Sources: [Converse](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html), [structured output](https://docs.aws.amazon.com/bedrock/latest/userguide/structured-output.html), [API keys](https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys.html), [gpt-oss-120b model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-oss-120b.html), [LangChain Bedrock](https://docs.langchain.com/oss/python/integrations/chat/bedrock).

- **Client:** `ChatBedrockConverse` from `langchain-aws` 1.9.0 with `boto3`/`botocore` 1.43.118, which support bearer API keys (`AWS_BEARER_TOKEN_BEDROCK`).
- **Assessment and report model:** `openai.gpt-oss-120b-1:0`, in-region in `ap-southeast-2` (Sydney). It always reasons; reasoning blocks are discarded, and `reasoning_effort` is a gpt-oss-specific request field.
- **Structured output:** schema-constrained Converse output has model and schema-subset restrictions. Early synthetic checks got valid output only with the full schema in the system prompt as well as the request (`json_schema`), and no accepted result through tool output. Local validation and quote checks always apply; there is no automatic fallback between methods. Details: [structured extraction](structured-extraction.md).
- **Interviewer model** (single-sample comparison, 2026-10-28, from India against `ap-southeast-2`, three scripted turns each, model time only):

  | Model | First text, warm client | Behaviour |
  | --- | --- | --- |
  | `au.anthropic.claude-haiku-4-5-20251001-v1:0` (Australia-only profile) | about 1 s | Best: acknowledged a declined topic, switched topic, used a resume mention, ended cleanly. Selected. |
  | `amazon.nova-lite-v1:0` | about 0.7 s | Fastest and cheapest; correct, plainer questions. |
  | `mistral.ministral-3-14b-instruct` | about 0.7–0.8 s | Correct, but each reply arrived in one chunk. |
  | `openai.gpt-oss-20b-1:0` | about 0.8–0.9 s | Repeated a question the candidate had declined. |
  | `openai.gpt-oss-120b-1:0` | about 1.1 s (4.6 s in a single earlier turn) | Packed several questions into one reply and ended early. |
  | `au.anthropic.claude-haiku-5-5` | — | `AccessDeniedException`: listed but not enabled for this account. |

  Render logs on 2026-10-29 showed the Haiku 4.5 interviewer's first text in about 0.8–1.3 s in live calls.
- **Privacy:** LangSmith tracing is forced off and no prompt cache is requested. Bedrock model invocation logging is an account setting that must stay off ([data retention](data-retention.md#provider-settings)).

## Cloudflare Turnstile

Source: [server-side validation](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/) (read 2026-11-01).
- A token is valid for 300 seconds and can be validated only once; a replay fails with `timeout-or-duplicate`.
- Siteverify takes `secret` and `response`; `remoteip` is optional (the app does not send it). It returns `success`, `action`, `hostname`, `challenge_ts`, `error-codes` and `metadata`.
- Observed 2026-10-31: results from Cloudflare's published test keys carry no `action` but set `metadata.result_with_testing_key`; the app accepts that flag, since production secrets reject test tokens.
- The widget script loads from `challenges.cloudflare.com` with explicit rendering; no npm package is needed.

## Prices

Used for `cost_usd` in the usage table; set in `backend/app/config.yaml`.

| Item | Price | Source |
| --- | --- | --- |
| `openai.gpt-oss-120b-1:0` | $0.1545 input / $0.6180 output per million tokens | Provided by the user from AWS, 2026-11-01 |
| `au.anthropic.claude-haiku-4-5-20251001-v1:0` | $1.10 input / $5.50 output per million tokens | Provided by the user from AWS, 2026-11-01 |
| Deepgram Voice Agent, own LLM, pay as you go | $0.065 per connected minute | [deepgram.com/pricing](https://deepgram.com/pricing), read 2026-11-01 |
| Deepgram Voice Agent, managed LLM | $0.075 (standard) or $0.163 (advanced) per minute | deepgram.com/pricing, read 2026-10-27 |

Deepgram bills connection time, so a ten-minute voice screening costs about $0.65 in Deepgram time; new Deepgram accounts got $200 of credit (2026-10-27). Check prices against your own plan and bills.

## Neon Postgres

Neon's [SQLAlchemy guide](https://neon.com/docs/guides/sqlalchemy) and [pooling guide](https://neon.com/docs/connect/connection-pooling): use SQLAlchemy 2 with psycopg and TLS, the pooled URL at runtime and a direct URL for Alembic migrations, because PgBouncer transaction pooling breaks session state. Setup and verification: [database](database.md).
