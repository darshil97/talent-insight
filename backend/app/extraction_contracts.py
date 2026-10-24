"""Job-related facts only; authoritative context and source verification stay server-side."""

import re
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.api.jobs import RequirementResponse
from app.resumes import ResumePage

Nonempty = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]
FactKind = Literal["skill", "experience", "qualification", "project"]
FACT_KINDS: tuple[FactKind, ...] = ("skill", "experience", "qualification", "project")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class ExtractionJob(StrictModel):
    id: Nonempty = Field(max_length=64)
    title: Nonempty = Field(max_length=300)
    skills: list[Annotated[Nonempty, Field(max_length=200)]] = Field(max_length=100)
    requirements: list[RequirementResponse] = Field(max_length=100)


class ExtractionSource(StrictModel):
    kind: Literal["uploaded_pdf", "synthetic_demo"]
    candidate_id: str | None = Field(default=None, max_length=64)
    pages: list[ResumePage] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def valid_source(self) -> Self:
        if (
            [page.page_number for page in self.pages] != list(range(1, len(self.pages) + 1))
            or not any(page.text.strip() for page in self.pages)
            or sum(len(page.text) for page in self.pages) > 200_000
            or (self.kind == "synthetic_demo") != (self.candidate_id is not None)
        ):
            raise ValueError("Invalid extraction source")
        return self


class QuotedEvidence(StrictModel):
    page_number: int = Field(ge=1, le=50, description="One-based source page number.")
    quote: Nonempty = Field(
        max_length=1200,
        description="Exact unique verbatim excerpt on this page; preserve whitespace.",
    )


class ExtractedFact(StrictModel):
    kind: FactKind
    value: Nonempty = Field(
        max_length=200,
        description="A literal job-related source phrase; no paraphrase or inference.",
    )
    evidence: list[QuotedEvidence] = Field(min_length=1, max_length=3)


class ResumeFacts(StrictModel):
    """Return job-related literal source mentions and exact page quotes, without assessment."""

    facts: list[ExtractedFact] = Field(
        max_length=40,
        description="Explicit job-related text only. Empty means unknown; never invent evidence.",
    )


class VerifiedEvidence(QuotedEvidence):
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class VerifiedFact(StrictModel):
    kind: FactKind
    value: Nonempty
    evidence: list[VerifiedEvidence]


class StructuredResume(StrictModel):
    job: ExtractionJob
    source: ExtractionSource
    mode: Literal["mock", "bedrock"]
    model_id: str | None
    facts: list[VerifiedFact]
    unknown_categories: list[FactKind]
    offset_unit: Literal["unicode_code_point"] = "unicode_code_point"
    notice: str


class ExtractionFailure(Exception):
    def __init__(self, code: str, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


def verify_facts(value: object, source: ExtractionSource) -> list[VerifiedFact]:
    """Offsets are calculated from exact, unambiguous quotes, never trusted from a model."""
    from pydantic import ValidationError

    try:
        result = ResumeFacts.model_validate(value)
    except ValidationError:
        raise ExtractionFailure("invalid_model_output", retryable=True) from None
    verified = []
    seen = set()
    for fact in result.facts:
        key = (fact.kind, fact.value.casefold())
        if key in seen:
            raise ExtractionFailure("invalid_model_output", retryable=True)
        seen.add(key)
        evidence = []
        for citation in fact.evidence:
            if citation.page_number > len(source.pages):
                raise ExtractionFailure("invalid_evidence", retryable=True)
            text = source.pages[citation.page_number - 1].text
            start = text.find(citation.quote)
            if start < 0 or text.find(citation.quote, start + 1) >= 0:
                raise ExtractionFailure("invalid_evidence", retryable=True)
            evidence.append(
                VerifiedEvidence(
                    **citation.model_dump(), start=start, end=start + len(citation.quote)
                )
            )
        if not any(
            re.search(
                r"(?<!\w)" + re.escape(fact.value) + r"(?!\w)", item.quote, flags=re.IGNORECASE
            )
            for item in evidence
        ):
            raise ExtractionFailure("invalid_evidence", retryable=True)
        verified.append(VerifiedFact(kind=fact.kind, value=fact.value, evidence=evidence))
    return verified


def provider_schema() -> dict:
    """AWS's native JSON subset omits constraints still enforced by Pydantic locally."""
    excluded = {
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "pattern",
        "minItems",
        "maxItems",
    }

    def clean(value):
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items() if key not in excluded}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return clean(ResumeFacts.model_json_schema())
