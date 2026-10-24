# Provider research and architecture constraints

Reviewed official documentation on 2026-10-24 (Asia/Kolkata). Neon is verified. Module 9 subsequently verified one source-validated Bedrock extraction using synthetic text, as recorded below; other AI/voice findings remain research rather than verified integrations. Recheck documentation, account access and selected SDK versions for each integration.

## Deepgram authentication

The [temporary-token guide](https://developers.deepgram.com/guides/fundamentals/token-based-authentication) documents `POST https://api.deepgram.com/v1/auth/grant`, authenticated with the server's API key. The default token lifetime is 30 seconds; the key must have sufficient permissions. Voice Agent accepts these tokens. Token expiry restricts connection establishment, not the duration of an already open connection. Therefore a short token lifetime alone does not cap interview duration or spend.

The [Voice Agent reference](https://developers.deepgram.com/reference/voice-agent/voice-agent) documents `wss://agent.deepgram.com/v1/agent/converse`, settings messages, bearer authentication and browser authentication through WebSocket subprotocols. It exposes `ConversationText`, `SettingsApplied`, `UserStartedSpeaking`, `AgentAudioDone`, errors and function-call messages. Audio completion is not proof that an entire interview is complete. Design an explicit, idempotent application completion operation and distinguish normal completion, early termination and transport failure. Client-submitted transcripts are unverified candidate statements, not authenticated provider evidence.

## Browser SDK and dynamic configuration

The [browser JavaScript SDK](https://developers.deepgram.com/docs/browser-agent-javascript) provides `@deepgram/agents`, with session, microphone and playback primitives. Its documented `tokenFactory` obtains credentials at connect/reconnect time. It supports inline settings, so no separate dashboard agent per job is necessary. Documented transcript, speech-start, connection and error events support the proposed UI. Microphone permission and playback behavior still need real-browser verification.

The [React integration](https://developers.deepgram.com/docs/browser-agent-react) provides `@deepgram/react`, context and hooks for connection, transcript and audio controls. Evaluate it when module 13 begins; pin and verify the selected package then. Do not install it during initial setup solely for future voice work.

## Bedrock within Deepgram: decision required before module 12

Deepgram's [LLM configuration guide](https://developers.deepgram.com/docs/voice-agent-llm-models) documents `aws_bedrock` as a bring-your-own provider, with a regional endpoint, model ID and IAM or STS credentials in settings. Passing these settings through a browser would expose AWS credentials, contrary to this project's requirements. Do not implement that pattern, even with STS.

The same guide documents custom LLM endpoints using an OpenAI-compatible protocol. A proposed fallback is a narrowly scoped FastAPI reasoning endpoint that calls Bedrock server-side while audio stays browser-to-Deepgram. This is an architectural inference, not a verified integration. It adds a text request hop, protocol translation, hosting latency and an endpoint that needs session authorization and usage limits. It does not require changing the underlying model provider to OpenAI.

Before voice implementation, investigate whether a supported server-managed configuration can hide credentials and securely bind dynamic context. Otherwise present the reasoning-endpoint design for approval. Verify streaming/cancellation, endpoint authentication and whether a client-held session capability permits arbitrary requests; enforce authoritative context, bounded inputs and usage server-side. Do not silently switch to a managed LLM or proxy audio.

## Backend Bedrock integration

[AWS Converse documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html) describes a common model interface and the required inference permissions. [LangChain's Bedrock integration](https://docs.langchain.com/oss/python/integrations/chat/bedrock) recommends `ChatBedrockConverse` for supported use cases; use `langchain-aws` with the normal AWS credential chain behind a small backend adapter.

[AWS structured-output documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/structured-output.html) describes schema-constrained Converse output and strict tool use, with model/profile and schema-subset restrictions. Confirm compatibility of the account, region, selected model or inference profile and pinned SDK. Always apply Pydantic validation and evidence checks, even when native schema enforcement is available. If unsupported, use a documented validated tool-output path or return a clear capability error; never accept arbitrary JSON unchecked.

Module 9 user selection: `openai.gpt-oss-120b-1:0` in `ap-southeast-2` (Sydney), using the user-provided `AWS_BEARER_TOKEN_BEDROCK` from the ignored backend dotenv. The [AWS model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-oss-120b.html) documents this model's Converse endpoint and in-region Sydney availability. Documentation alone did not establish account access; bounded synthetic calls then confirmed the key could invoke the model. No IAM permissions or infrastructure were changed. [AWS's API-key guide](https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys.html) documents bearer-key authentication; the pinned `boto3==1.43.118`, `botocore==1.43.118` and `langchain-aws==1.9.0` support it.

Actual module 9 checks: six small synthetic-only Converse calls, each capped at 2,048 output tokens with one SDK attempt and no service retry. Three explored native JSON requests: the first two outputs failed local validation; the final request included the exact schema in the system prompt as well as `outputConfig`, and returned two facts that passed Pydantic and exact source-quote verification. Three tool-output checks returned no accepted structured tool result. This does not establish a success rate, an accuracy score or provider-enforced schema guarantees. No real resume or transcript was sent. Raw responses/reasoning, source content and credentials were not written into application files or routine logs.

The saved method is explicitly `BEDROCK_STRUCTURED_METHOD=json_schema`, with the full schema also stated in the server prompt. Do not automatically fall back between JSON, tool or mock paths. Native output configuration is not a reason to skip local validation. The parser independently rejects incomplete/fenced JSON that a generic JSON parser might repair; schema, quotes, phrase provenance and page ranges are checked again before returning facts. The selected model's reasoning blocks are discarded. [AWS tool-use documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use-client-side.html) distinguishes automatic tool selection from model-specific forced choices; a tool method must be verified for the actual selected model/profile before use.

LangSmith is a transitive dependency of the chosen adapter, but tracing is explicitly disabled in every disposable Bedrock worker and its pytest plugin is disabled in project test options. No prompt cache is requested. AWS invocation-logging/retention settings and real-document privacy remain unverified; application non-persistence does not establish those policies. See [structured extraction](structured-extraction.md) for the exact API, bounds, provenance semantics and limitations.

## Neon Postgres

Neon's [SQLAlchemy guide](https://neon.com/docs/guides/sqlalchemy) documents standard PostgreSQL connectivity. Its [pooling guide](https://neon.com/docs/connect/connection-pooling) describes PgBouncer transaction pooling and related session-state constraints. Recommend SQLAlchemy 2 with psycopg, a bounded application pool and TLS. Use a direct connection for Alembic migrations to avoid session-state surprises; configure runtime and migration URLs separately.

The existing `talent-insight` project, its single `production` branch and `neondb` database were inspected and initialized with the approved catalog migration and synthetic seed. Pooled runtime and direct migration connectivity, schema parity, evidence and repeatable seeding are verified on Neon PostgreSQL 18.6. Local and hosted backend runs share this Neon database; no local PostgreSQL server is used. Default checks need no database; opt-in integration tests use read-only transactions. See [database setup](database.md) for the exact target and commands. Object storage remains optional and unused.

## Public-demo boundary

CORS controls cooperating browsers; it does not authenticate API callers or enforce provider cost limits. Before public voice access, verify token scope, server-enforceable session duration, concurrency and project spend limits. A browser can change settings and ignore a client-side stop timer. A single-process in-memory limiter is only a development safeguard, not a distributed budget control.

Signed temporary candidate context can detect modification but is readable by its holder. Keep it short-lived, size-limited and out of URLs/logs; do not put resumes in an opaque-looking token and assume confidentiality. Session design remains pending, including replay/duplicate protection, expiry and cleanup. Backend transcript validation can check structure and consistency but cannot prove a browser transcript authentic.
