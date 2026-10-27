"""One structured model call: native schema request, raw-response capture and metrics."""

import logging
import time

from app.llm.base import get_provider
from app.llm.factory import get_chat_model
from app.llm.response import extract_text, parse_json_object
from app.pipeline.contracts import ExtractionFailure

logger = logging.getLogger(__name__)
_RETRYABLE = {"provider_throttled", "provider_timeout", "invalid_model_output"}


def _failure(code: str, *issues: str) -> ExtractionFailure:
    return ExtractionFailure(code, retryable=code in _RETRYABLE, issues=issues)


async def invoke_structured(
    settings,
    *,
    stage: str,
    attempt: int,
    system: str,
    payload: str,
    schema: dict,
    output_name: str,
    root_key: str,
) -> object:
    """Return the model's unvalidated JSON value; callers own all schema and source checks."""
    provider = get_provider(settings.ai_mode)
    method = provider.structured_method(settings)
    started = time.perf_counter()
    try:
        runnable = get_chat_model(settings).with_structured_output(
            schema, include_raw=True, method=method
        )
        result = await runnable.ainvoke(
            [("system", system), ("human", payload)], config={"callbacks": []}
        )
    except ExtractionFailure:
        raise
    except Exception as exc:
        code = provider.error_code(exc)
        if code is None:
            if isinstance(exc, NotImplementedError):
                code = "unsupported_model_capability"
            elif isinstance(exc, ValueError | TypeError | KeyError):
                code = "invalid_model_output"
            else:
                code = "ai_unavailable"
        # Exception messages can contain request or credential details; log the class only.
        logger.warning(
            "%s attempt %d: %s call failed with %s (%s) after %.0f ms",
            stage,
            attempt,
            provider.name,
            code,
            type(exc).__name__,
            (time.perf_counter() - started) * 1000,
        )
        raise _failure(code) from None
    raw = result.get("raw") if isinstance(result, dict) else None
    stop = raw.response_metadata.get("stopReason") if raw is not None else None
    usage = getattr(raw, "usage_metadata", None) or {}
    logger.info(
        "%s attempt %d: %s %s stop=%s tokens=%s/%s in %.0f ms",
        stage,
        attempt,
        provider.name,
        provider.model_id(settings),
        stop,
        usage.get("input_tokens"),
        usage.get("output_tokens"),
        (time.perf_counter() - started) * 1000,
    )
    if raw is None:
        raise _failure("invalid_model_output", "response: no model message was returned")
    if stop == "max_tokens":
        raise _failure(
            "invalid_model_output",
            "response: output was cut off at the token limit; return fewer and shorter items",
        )
    if stop not in {"end_turn", "tool_use"}:
        raise _failure("invalid_model_output", "response: the response did not finish normally")
    if method == "json_schema":
        if getattr(raw, "tool_calls", []):
            raise _failure("invalid_model_output", "response: return JSON text, not a tool call")
        try:
            return parse_json_object(extract_text(raw.content), root_key)
        except ValueError:
            raise _failure(
                "invalid_model_output",
                "response: return exactly one complete JSON object and nothing else",
            ) from None
    calls = getattr(raw, "tool_calls", [])
    if len(calls) != 1 or calls[0].get("name") != output_name:
        raise _failure("invalid_model_output", f"response: call {output_name} exactly once")
    # Validate original tool arguments, not a parser's repaired or reshaped value.
    return calls[0]["args"]
