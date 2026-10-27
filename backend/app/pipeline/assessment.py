"""Interpret one validated extraction, then score it without provider-controlled arithmetic."""

import logging

from app.config import Settings
from app.llm.factory import MOCK_MODE, ensure_ai_configured, model_id
from app.pipeline.contracts import FACT_KINDS, Assessment, ExtractionFailure, StructuredResume
from app.pipeline.interpretation import interpret_resume
from app.pipeline.scoring import score_interpretation

logger = logging.getLogger(__name__)


async def assess_resume(structured: StructuredResume, settings: Settings) -> Assessment:
    ensure_ai_configured(settings)
    if settings.ai_mode != structured.mode or structured.model_id != model_id(settings):
        raise ExtractionFailure("invalid_interpretation")
    interpretation, facts = await interpret_resume(structured, settings)
    if facts != structured.facts:
        # Quotes the judging step added are verified source spans, like extracted facts.
        structured = structured.model_copy(
            update={
                "facts": facts,
                "unknown_categories": [
                    kind for kind in FACT_KINDS if not any(fact.kind == kind for fact in facts)
                ],
            }
        )
    judgments, scoring = score_interpretation(structured, interpretation, settings)
    logger.info(
        "assessment: %d resolved, %d unknown, estimate %s, confidence %s",
        scoring.resolved_count,
        scoring.unknown_count,
        scoring.estimate,
        scoring.confidence,
    )
    return Assessment(
        structured=structured,
        judgments=judgments.judgments,
        scoring=scoring,
        notice=(
            "Mock interpretation leaves every criterion unknown. "
            if settings.ai_mode == MOCK_MODE
            else "AI interpretation requires human review. "
        )
        + "Evidence citations prove text location, not competence. "
        "The unvalidated rubric is not a hiring decision or performance probability.",
    )
