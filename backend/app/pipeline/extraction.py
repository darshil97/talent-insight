"""Resume fact extraction with explicit providers and no durable candidate state."""

import json
import logging

from app.config import Settings
from app.llm.base import get_provider
from app.llm.factory import MOCK_MODE, ensure_ai_configured, model_id
from app.llm.invoke import invoke_structured
from app.pipeline.attempts import Outcome, run_attempts
from app.pipeline.contracts import (
    FACT_KINDS,
    MAX_FACTS,
    MAX_QUOTE_CHARACTERS,
    MAX_QUOTES_PER_FACT,
    MAX_VALUE_CHARACTERS,
    TARGET_FACTS,
    CandidateIdentity,
    ExtractionFailure,
    ExtractionJob,
    ExtractionSource,
    ResumeFacts,
    StructuredResume,
    VerifiedFact,
    provider_json_schema,
    word_pattern,
)
from app.pipeline.evidence import salvage_facts, verify_facts, verify_identity
from app.prompts.loader import load_prompt

logger = logging.getLogger(__name__)
MOCK_NOTICE = (
    "Mock extraction: literal skill mentions only; no AI assessment. "
    "Other categories remain unknown."
)
AI_NOTICE = (
    "AI-extracted text mentions with verified source quotes. "
    "Review their meaning and completeness; missing evidence is unknown. "
    "No score or hiring decision."
)


def mock_facts(job: ExtractionJob, source: ExtractionSource) -> dict:
    """Literal skill mentions only, clearly labeled; never simulates experience or assessment."""
    facts = []
    for skill in job.skills:
        found = False
        for page in source.pages:
            for line in page.text.splitlines():
                match = word_pattern(skill).search(line)
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
        if len(facts) == MAX_FACTS:
            break
    return {"facts": facts}


def extraction_prompt(settings: Settings, issues: tuple[str, ...] = ()) -> str:
    return load_prompt(
        "extraction",
        "system",
        with_mentions=False,
        target_facts=TARGET_FACTS,
        max_facts=MAX_FACTS,
        max_quotes=MAX_QUOTES_PER_FACT,
        max_value=MAX_VALUE_CHARACTERS,
        max_quote=MAX_QUOTE_CHARACTERS,
        method=get_provider(settings.ai_mode).structured_method(settings),
        output_name="ResumeFacts",
        schema_json=json.dumps(provider_json_schema(ResumeFacts), ensure_ascii=False),
        issues=list(issues),
    )


def extraction_payload(job: ExtractionJob, source: ExtractionSource) -> str:
    """Server-owned job context plus untrusted page text, serialized as data, not instructions."""
    return json.dumps(
        {
            "job_context": job.model_dump(),
            "untrusted_resume_pages": [page.model_dump() for page in source.pages],
        },
        ensure_ascii=False,
    )


async def _extract_once(
    job: ExtractionJob,
    source: ExtractionSource,
    settings: Settings,
    attempt: int,
    issues: tuple[str, ...],
) -> Outcome[tuple[list[VerifiedFact], CandidateIdentity | None]]:
    value = await invoke_structured(
        settings,
        stage="extraction",
        attempt=attempt,
        system=extraction_prompt(settings, issues),
        payload=extraction_payload(job, source),
        schema=provider_json_schema(ResumeFacts),
        output_name="ResumeFacts",
        root_key="facts",
    )
    result = salvage_facts(value, source)
    if result.issues:
        logger.info(
            "extraction attempt %d: kept %d of %d facts; discarded %s",
            attempt,
            len(result.facts),
            result.returned,
            result.counts(),
        )
    # Retry only when most returned facts were unverifiable; otherwise keep what verified.
    retry = tuple(result.issues) if result.failed * 2 > result.returned else ()
    identity = verify_identity(value, source)
    return Outcome((result.facts, identity), quality=len(result.facts), retry_issues=retry)


async def structure_resume(
    job: ExtractionJob, source: ExtractionSource, settings: Settings
) -> StructuredResume:
    ensure_ai_configured(settings)
    # Count all model-visible source and job text; never silently truncate a resume.
    if (
        len(job.model_dump_json()) + sum(len(page.text) for page in source.pages)
        > settings.ai_max_input_characters
    ):
        raise ExtractionFailure("ai_input_too_large")
    identity = None
    if settings.ai_mode == MOCK_MODE:
        facts = verify_facts(mock_facts(job, source), source)
    else:
        facts, identity = await run_attempts(
            "extraction",
            settings,
            lambda attempt, issues: _extract_once(job, source, settings, attempt, issues),
        )
    unknown = [kind for kind in FACT_KINDS if not any(fact.kind == kind for fact in facts)]
    logger.info(
        "extraction: %d verified facts; unknown categories: %s; identity fields verified: %d",
        len(facts),
        ",".join(unknown) or "none",
        sum(bool(field) for field in (identity.name, identity.current_title)) if identity else 0,
    )
    return StructuredResume(
        job=job,
        source=source,
        mode=settings.ai_mode,
        model_id=model_id(settings),
        facts=facts,
        identity=identity,
        unknown_categories=unknown,
        notice=MOCK_NOTICE if settings.ai_mode == MOCK_MODE else AI_NOTICE,
    )
