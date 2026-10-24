"""Bounded extraction with explicit providers and no durable candidate state."""

import asyncio
import json
import os
import re
import sys
from collections.abc import Awaitable, Callable

from app.config import Settings
from app.extraction_contracts import (
    FACT_KINDS,
    ExtractionFailure,
    ExtractionJob,
    ExtractionSource,
    StructuredResume,
    verify_facts,
)

Provider = Callable[[ExtractionJob, ExtractionSource, Settings, bool], Awaitable[object]]


async def mock_provider(
    job: ExtractionJob, source: ExtractionSource, _settings: Settings, _repair: bool
) -> object:
    """Literal skill mentions only, clearly labeled; never simulates experience or assessment."""
    facts = []
    for skill in job.skills:
        found = False
        for page in source.pages:
            for line in page.text.splitlines():
                match = re.search(r"(?<!\w)" + re.escape(skill) + r"(?!\w)", line, re.IGNORECASE)
                if match and len(line) <= 1200 and page.text.count(line) == 1:
                    facts.append(
                        {
                            "kind": "skill",
                            "value": match.group(),
                            "evidence": [{"page_number": page.page_number, "quote": line}],
                        }
                    )
                    found = True
                    break
            if found:
                break
        if len(facts) == 40:
            break
    return {"facts": facts}


def worker_environment(settings: Settings) -> dict[str, str]:
    env = dict(os.environ)
    # Tracing can send full prompts to another service. Disable it in every disposable child.
    env.update(
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
        LANGCHAIN_TRACING="false",
        LANGCHAIN_DEBUG="false",
        PYTHONDONTWRITEBYTECODE="1",
    )
    for name in (
        "aws_region",
        "bedrock_model_id",
        "bedrock_structured_method",
        "ai_max_output_tokens",
        "ai_timeout_seconds",
        "aws_profile",
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_session_token",
        "aws_bearer_token_bedrock",
    ):
        value = getattr(settings, name)
        if value is not None:
            env[name.upper()] = str(
                value.get_secret_value() if hasattr(value, "get_secret_value") else value
            )
    return env


async def bedrock_provider(
    job: ExtractionJob, source: ExtractionSource, settings: Settings, repair: bool
) -> object:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.bedrock_worker",
        env=worker_environment(settings),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        payload = json.dumps(
            {"job": job.model_dump(), "source": source.model_dump(), "repair": repair},
            ensure_ascii=False,
        ).encode()
        output, _ = await process.communicate(payload)
    finally:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        await process.wait()
    if process.returncode != 0 or len(output) > 512_000:
        raise ExtractionFailure("ai_unavailable")
    try:
        result = json.loads(output)
    except (ValueError, UnicodeError):
        raise ExtractionFailure("invalid_model_output", retryable=True) from None
    if isinstance(result, dict) and "error" in result:
        allowed = {
            "provider_access_denied",
            "provider_configuration_error",
            "provider_throttled",
            "provider_timeout",
            "unsupported_model_capability",
            "invalid_model_output",
            "ai_unavailable",
        }
        code = result["error"]
        if not isinstance(code, str) or code not in allowed:
            code = "ai_unavailable"
        raise ExtractionFailure(
            code,
            retryable=code in {"provider_throttled", "provider_timeout", "invalid_model_output"},
        )
    return result


def configured_provider(settings: Settings) -> Provider:
    if settings.ai_mode is None:
        raise ExtractionFailure("ai_not_configured")
    if settings.ai_mode == "mock":
        return mock_provider
    if not settings.aws_region or not settings.bedrock_model_id:
        raise ExtractionFailure("provider_configuration_error")
    return bedrock_provider


async def structure_resume(
    job: ExtractionJob,
    source: ExtractionSource,
    settings: Settings,
    provider: Provider | None = None,
) -> StructuredResume:
    provider = provider or configured_provider(settings)
    # Count all model-visible source and job text; never silently truncate a resume.
    if (
        len(job.model_dump_json()) + sum(len(page.text) for page in source.pages)
        > settings.ai_max_input_characters
    ):
        raise ExtractionFailure("ai_input_too_large")
    try:
        async with asyncio.timeout(settings.ai_timeout_seconds):
            for attempt in range(settings.ai_max_attempts):
                try:
                    value = await provider(job, source, settings, attempt > 0)
                    facts = verify_facts(value, source)
                    return StructuredResume(
                        job=job,
                        source=source,
                        mode=settings.ai_mode,
                        model_id=settings.bedrock_model_id
                        if settings.ai_mode == "bedrock"
                        else None,
                        facts=facts,
                        unknown_categories=[
                            kind for kind in FACT_KINDS if not any(f.kind == kind for f in facts)
                        ],
                        notice=(
                            "Mock extraction: literal skill mentions only; no AI assessment. "
                            "Other categories remain unknown."
                            if settings.ai_mode == "mock"
                            else "AI-extracted text mentions with verified source quotes. "
                            "Review their meaning and completeness; missing evidence is unknown. "
                            "No score or hiring decision."
                        ),
                    )
                except ExtractionFailure as exc:
                    if not exc.retryable or attempt + 1 == settings.ai_max_attempts:
                        raise
                    await asyncio.sleep(0.2)
    except TimeoutError:
        raise ExtractionFailure("ai_timeout") from None
    raise ExtractionFailure("ai_unavailable")
