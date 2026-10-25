"""Evidence-linked interpretation and deterministic, non-decisional scoring."""

import asyncio
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.config import Settings
from app.extraction_contracts import ExtractionFailure, StructuredResume, verify_facts

Category = Literal["mandatory", "experience", "preferred", "qualification"]
Status = Literal["met", "partial", "not_met", "unknown"]
CATEGORIES: tuple[Category, ...] = ("mandatory", "experience", "preferred", "qualification")
CREDIT = {"met": Decimal(1), "partial": Decimal("0.5"), "not_met": Decimal(0)}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class Judgment(StrictModel):
    requirement_id: str = Field(min_length=1, max_length=64)
    status: Status
    fact_indices: list[int] = Field(max_length=10)
    reason: Annotated[str, StringConstraints(pattern=r"\S")] = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def evidence_for_resolved_status(self) -> Self:
        if (self.status == "unknown") != (len(self.fact_indices) == 0):
            raise ValueError("Resolved judgments require cited facts; unknown has none")
        if len(set(self.fact_indices)) != len(self.fact_indices):
            raise ValueError("Duplicate fact references")
        return self


class Interpretation(StrictModel):
    judgments: list[Judgment] = Field(max_length=100)


class CategoryScore(StrictModel):
    category: Category
    requirement_count: int
    resolved_count: int
    unknown_count: int
    effective_weight: float
    lower: float
    upper: float


class MatchScore(StrictModel):
    score: float | None
    lower: float | None
    upper: float | None
    resolved_count: int
    unknown_count: int
    mandatory_met: int
    mandatory_total: int
    categories: list[CategoryScore]


class Assessment(StrictModel):
    structured: StructuredResume
    judgments: list[Judgment]
    scoring: MatchScore
    notice: str


def interpretation_schema() -> dict:
    """Provider-compatible subset; full local validation remains authoritative."""
    # Match the native-output schema subset; full constraints are enforced locally.
    excluded = {"minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems", "pattern"}

    def clean(value):
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items() if key not in excluded}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return clean(Interpretation.model_json_schema())


def validate_interpretation(structured: StructuredResume, value: object) -> Interpretation:
    """Recheck provenance and require an exact, job-owned requirement mapping."""
    from pydantic import ValidationError

    try:
        validated = Interpretation.model_validate(value)
        verified = verify_facts(
            {
                "facts": [
                    {
                        "kind": fact.kind,
                        "value": fact.value,
                        "evidence": [
                            {"page_number": e.page_number, "quote": e.quote} for e in fact.evidence
                        ],
                    }
                    for fact in structured.facts
                ]
            },
            structured.source,
        )
        if verified != structured.facts:
            raise ValueError("Source offsets changed")
        requirement_ids = [row.id for row in structured.job.requirements]
        if len(set(requirement_ids)) != len(requirement_ids):
            raise ValueError("Duplicate canonical requirements")
        if len(validated.judgments) != len(requirement_ids) or (
            {row.requirement_id for row in validated.judgments} != set(requirement_ids)
        ):
            raise ValueError("Judgments must cover each canonical requirement exactly once")
        for row in validated.judgments:
            if any(index < 0 or index >= len(verified) for index in row.fact_indices):
                raise ValueError("Invalid fact reference")
        return validated
    except (ValidationError, ValueError, ExtractionFailure):
        raise ExtractionFailure("invalid_interpretation", retryable=True) from None


def score_interpretation(
    structured: StructuredResume, value: object, settings: Settings
) -> tuple[Interpretation, MatchScore]:
    interpretation = validate_interpretation(structured, value)
    weights = {
        "mandatory": settings.match_weight_mandatory,
        "experience": settings.match_weight_experience,
        "preferred": settings.match_weight_preferred,
        "qualification": settings.match_weight_qualification,
    }
    lookup = {row.requirement_id: row for row in interpretation.judgments}
    present = {row.category for row in structured.job.requirements}
    active_weight = sum(weights[category] for category in present)
    groups = []
    lower = upper = Decimal(0)
    resolved = unknown = mandatory_met = mandatory_total = 0
    for category in CATEGORIES:
        requirements = [row for row in structured.job.requirements if row.category == category]
        if not requirements:
            continue
        judgments = [lookup[row.id] for row in requirements]
        known = sum(
            (CREDIT[row.status] for row in judgments if row.status != "unknown"), Decimal(0)
        )
        missing = sum(row.status == "unknown" for row in judgments)
        resolved += len(judgments) - missing
        unknown += missing
        if category == "mandatory":
            mandatory_total = len(judgments)
            mandatory_met = sum(row.status == "met" for row in judgments)
        effective = (
            Decimal(weights[category]) / Decimal(active_weight) if active_weight else Decimal(0)
        )
        category_lower = effective * known / len(judgments) * 100
        category_upper = effective * (known + missing) / len(judgments) * 100
        lower += category_lower
        upper += category_upper
        groups.append(
            CategoryScore(
                category=category,
                requirement_count=len(judgments),
                resolved_count=len(judgments) - missing,
                unknown_count=missing,
                effective_weight=_display(effective * 100),
                lower=_display(category_lower),
                upper=_display(category_upper),
            )
        )
    available = bool(structured.job.requirements and active_weight)
    score = MatchScore(
        score=_display(lower) if available and unknown == 0 else None,
        lower=_display(lower) if available else None,
        upper=_display(upper) if available else None,
        resolved_count=resolved,
        unknown_count=unknown,
        mandatory_met=mandatory_met,
        mandatory_total=mandatory_total,
        categories=groups,
    )
    return interpretation, score


def _display(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def mock_interpretation(structured: StructuredResume) -> Interpretation:
    """Mock extraction cannot establish criterion satisfaction from word mentions."""
    return Interpretation(
        judgments=[
            Judgment(
                requirement_id=row.id,
                status="unknown",
                fact_indices=[],
                reason="Requires review of source meaning and requirement fit.",
            )
            for row in structured.job.requirements
        ]
    )


async def assess_resume(structured: StructuredResume, settings: Settings) -> Assessment:
    """Interpret one validated extraction, then score without provider-controlled arithmetic."""
    from app.extraction import bedrock_provider, configured_provider

    configured_provider(settings)
    if settings.ai_mode != structured.mode or (
        structured.mode == "bedrock" and structured.model_id != settings.bedrock_model_id
    ):
        raise ExtractionFailure("invalid_interpretation")
    if settings.ai_mode == "mock":
        value = mock_interpretation(structured)
    else:
        if (
            len(structured.job.model_dump_json())
            + len(structured.source.model_dump_json())
            + sum(len(fact.model_dump_json()) for fact in structured.facts)
            > settings.ai_max_input_characters
        ):
            raise ExtractionFailure("ai_input_too_large")
        try:
            async with asyncio.timeout(settings.ai_timeout_seconds):
                for attempt in range(settings.ai_max_attempts):
                    try:
                        value = await bedrock_provider(
                            structured.job,
                            structured.source,
                            settings,
                            attempt > 0,
                            facts=structured.facts,
                        )
                        validate_interpretation(structured, value)
                        break
                    except ExtractionFailure as exc:
                        if not exc.retryable or attempt + 1 == settings.ai_max_attempts:
                            raise
                        await asyncio.sleep(0.2)
        except TimeoutError:
            raise ExtractionFailure("ai_timeout") from None
    judgments, scoring = score_interpretation(structured, value, settings)
    return Assessment(
        structured=structured,
        judgments=judgments.judgments,
        scoring=scoring,
        notice=(
            "Mock interpretation leaves every criterion unknown. "
            if settings.ai_mode == "mock"
            else "AI interpretation requires human review. "
        )
        + "Evidence citations prove text location, not competence. "
        "The unvalidated rubric is not a hiring decision or performance probability.",
    )
