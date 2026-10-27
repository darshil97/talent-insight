"""Pipeline contracts; authoritative job context and source verification stay server-side."""

import re
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.resumes import ResumePage

Nonempty = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]
FactKind = Literal["skill", "experience", "qualification", "project"]
FACT_KINDS: tuple[FactKind, ...] = ("skill", "experience", "qualification", "project")
Category = Literal["mandatory", "experience", "preferred", "qualification"]
CATEGORIES: tuple[Category, ...] = ("mandatory", "experience", "preferred", "qualification")
Status = Literal["met", "transferable", "partial", "not_met", "unknown"]
Confidence = Literal["very_high", "high", "medium", "low"]
STATUSES: tuple[Status, ...] = ("met", "transferable", "partial", "not_met", "unknown")

# Hard limits shared by validation and the rendered prompts, so they cannot drift apart.
TARGET_FACTS = 12
MAX_FACTS = 40
MAX_QUOTES_PER_FACT = 3
MAX_VALUE_CHARACTERS = 200
MAX_QUOTE_CHARACTERS = 1200
MAX_CITATIONS = 10
MAX_REASON_CHARACTERS = 300
MAX_NAME_CHARACTERS = 120
MAX_TITLE_CHARACTERS = 160


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class RequirementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    category: Category
    description: str
    minimum_years: float | None
    sort_order: int


class ExtractionJob(StrictModel):
    id: Nonempty = Field(max_length=64)
    title: Nonempty = Field(max_length=300)
    skills: list[Annotated[Nonempty, Field(max_length=200)]] = Field(max_length=100)
    requirements: list[RequirementResponse] = Field(max_length=100)

    @classmethod
    def from_detail(cls, detail) -> Self:
        """Model-visible job context from a validated job detail; nothing else is shared."""
        return cls(
            id=detail.id,
            title=detail.title,
            skills=detail.skills,
            requirements=detail.requirements,
        )


class ExtractionSource(StrictModel):
    kind: Literal["uploaded_pdf", "synthetic_demo"]
    candidate_id: str | None = Field(default=None, max_length=64)
    pages: list[ResumePage] = Field(min_length=1, max_length=50)

    @classmethod
    def synthetic(cls, candidate_id: str, resume_text: str) -> Self:
        return cls(
            kind="synthetic_demo",
            candidate_id=candidate_id,
            pages=[ResumePage(page_number=1, text=resume_text)],
        )

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
        max_length=MAX_QUOTE_CHARACTERS,
        description="Exact unique verbatim excerpt on this page; preserve whitespace.",
    )


class ExtractedFact(StrictModel):
    kind: FactKind
    value: Nonempty = Field(
        max_length=MAX_VALUE_CHARACTERS,
        description="A literal job-related source phrase; no paraphrase or inference.",
    )
    evidence: list[QuotedEvidence] = Field(min_length=1, max_length=MAX_QUOTES_PER_FACT)


class IdentityOutput(StrictModel):
    name: str = Field(
        max_length=MAX_NAME_CHARACTERS,
        description="The candidate's name exactly as written, or an empty string if not stated.",
    )
    current_title: str = Field(
        max_length=MAX_TITLE_CHARACTERS,
        description="Current or most recent job title exactly as written, or an empty string.",
    )


class ResumeFacts(StrictModel):
    """Return job-related literal source mentions and exact page quotes, without assessment."""

    identity: IdentityOutput
    facts: list[ExtractedFact] = Field(
        max_length=MAX_FACTS,
        description="Explicit job-related text only. Empty means unknown; never invent evidence.",
    )


class VerifiedEvidence(QuotedEvidence):
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class VerifiedText(StrictModel):
    """A display value that occurs in the source; offsets address its exact source span."""

    value: Nonempty
    page_number: int = Field(ge=1, le=50)
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class CandidateIdentity(StrictModel):
    """Display aids for uploads; never sent to interpretation or used in scoring."""

    name: VerifiedText | None = None
    current_title: VerifiedText | None = None


class VerifiedFact(StrictModel):
    kind: FactKind
    value: Nonempty
    evidence: list[VerifiedEvidence]


class StructuredResume(StrictModel):
    job: ExtractionJob
    source: ExtractionSource
    mode: str = Field(min_length=1, max_length=32)
    model_id: str | None
    facts: list[VerifiedFact]
    identity: CandidateIdentity | None = None
    unknown_categories: list[FactKind]
    offset_unit: Literal["unicode_code_point"] = "unicode_code_point"
    notice: str

    @field_validator("mode")
    @classmethod
    def known_mode(cls, value: str) -> str:
        from app.llm.factory import ai_modes

        if value not in ai_modes():
            raise ValueError("Unknown AI mode")
        return value


class Judgment(StrictModel):
    requirement_id: str = Field(min_length=1, max_length=64)
    status: Status
    fact_indices: list[int] = Field(max_length=MAX_CITATIONS)
    reason: Annotated[str, StringConstraints(pattern=r"\S")] = Field(
        min_length=1, max_length=MAX_REASON_CHARACTERS
    )

    @model_validator(mode="after")
    def evidence_for_resolved_status(self) -> Self:
        if (self.status == "unknown") != (len(self.fact_indices) == 0):
            raise ValueError("Resolved judgments require cited facts; unknown has none")
        if len(set(self.fact_indices)) != len(self.fact_indices):
            raise ValueError("Duplicate fact references")
        return self


class Interpretation(StrictModel):
    judgments: list[Judgment] = Field(max_length=100)


class JudgmentOutput(StrictModel):
    """Model output: may add resume quotes that no verified mention covers yet."""

    requirement_id: str
    status: Status
    fact_indices: list[int] = Field(
        max_length=MAX_CITATIONS, description="Zero-based indices into verified_text_mentions."
    )
    new_evidence: list[ExtractedFact] = Field(
        max_length=MAX_QUOTES_PER_FACT,
        description="Resume evidence not in verified_text_mentions, copied exactly; verified.",
    )
    reason: str = Field(max_length=MAX_REASON_CHARACTERS)


class InterpretationOutput(StrictModel):
    judgments: list[JudgmentOutput] = Field(max_length=100)


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
    # Midpoint of the range (unknowns at half credit) and how much of the score is unknown.
    estimate: float | None
    confidence: Confidence | None
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


class ExtractionFailure(Exception):
    """A safe public error code; `issues` are server-written retry hints, never model text."""

    def __init__(self, code: str, *, retryable: bool = False, issues: tuple[str, ...] = ()):
        self.code = code
        self.retryable = retryable
        self.issues = issues
        super().__init__(code)


_UNSUPPORTED_SCHEMA_KEYS = {
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


def provider_json_schema(model: type[BaseModel]) -> dict:
    """Provider-compatible schema subset; full Pydantic validation stays authoritative locally."""

    def clean(value):
        if isinstance(value, dict):
            return {
                key: clean(item)
                for key, item in value.items()
                if key not in _UNSUPPORTED_SCHEMA_KEYS
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return clean(model.model_json_schema())


def word_pattern(value: str) -> re.Pattern:
    return re.compile(r"(?<!\w)" + re.escape(value) + r"(?!\w)", re.IGNORECASE)
