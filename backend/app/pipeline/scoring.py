"""Deterministic, non-decisional scoring from validated judgments; no provider arithmetic."""

from decimal import ROUND_HALF_UP, Decimal

from app.config import Settings
from app.pipeline.contracts import (
    CATEGORIES,
    CategoryScore,
    Confidence,
    ExtractionFailure,
    Interpretation,
    MatchScore,
    StructuredResume,
)
from app.pipeline.evidence import reverify


def credits(settings: Settings) -> dict[str, Decimal]:
    """Credit per resolved status; unknown stays unresolved and only widens the range."""
    return {
        "met": Decimal(1),
        "transferable": Decimal(str(settings.match_credit_transferable)),
        "partial": Decimal(str(settings.match_credit_partial)),
        "not_met": Decimal(0),
    }


# Upper bounds, in score points, on how much of the score unknown requirements leave open.
CONFIDENCE_BANDS: tuple[tuple[Decimal, Confidence], ...] = (
    (Decimal(0), "very_high"),
    (Decimal(15), "high"),
    (Decimal(35), "medium"),
)


def confidence(unknown_points: Decimal) -> Confidence:
    return next((label for limit, label in CONFIDENCE_BANDS if unknown_points <= limit), "low")


def validate_interpretation(structured: StructuredResume, value: object) -> Interpretation:
    """Recheck provenance and require an exact, job-owned requirement mapping."""
    from pydantic import ValidationError

    try:
        validated = Interpretation.model_validate(value)
        if not reverify(structured):
            raise ValueError("Source offsets changed")
        requirement_ids = [row.id for row in structured.job.requirements]
        if len(set(requirement_ids)) != len(requirement_ids):
            raise ValueError("Duplicate canonical requirements")
        if len(validated.judgments) != len(requirement_ids) or (
            {row.requirement_id for row in validated.judgments} != set(requirement_ids)
        ):
            raise ValueError("Judgments must cover each canonical requirement exactly once")
        for row in validated.judgments:
            if any(index < 0 or index >= len(structured.facts) for index in row.fact_indices):
                raise ValueError("Invalid fact reference")
        return validated
    except (ValidationError, ValueError):
        raise ExtractionFailure("invalid_interpretation") from None


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
    credit = credits(settings)
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
            (credit[row.status] for row in judgments if row.status != "unknown"), Decimal(0)
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
        estimate=_display((lower + upper) / 2) if available else None,
        confidence=confidence((upper - lower).quantize(Decimal("0.1"))) if available else None,
        resolved_count=resolved,
        unknown_count=unknown,
        mandatory_met=mandatory_met,
        mandatory_total=mandatory_total,
        categories=groups,
    )
    return interpretation, score


def _display(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
