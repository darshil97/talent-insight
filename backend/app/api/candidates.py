"""Job-scoped synthetic candidate views with validated resume provenance."""

from typing import Annotated, Literal, Self

from fastapi import APIRouter, HTTPException, Path, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app import catalog
from app.api.deps import CatalogSession, JobId
from app.api.jobs import JobDetail
from app.demo_cache import load_cache, valid_assessment
from app.errors import ErrorResponse
from app.pipeline.contracts import Assessment, Confidence, ExtractionJob, ExtractionSource
from app.ranking import Availability, AvailabilityInput, describe, ranking_score

router = APIRouter(prefix="/jobs/{job_id}/candidates", tags=["candidates"])
CandidateId = Annotated[str, Path(pattern=r"^demo_[a-z0-9_]+$", max_length=64)]
Nonempty = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]


class CandidateSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: Nonempty
    headline: Nonempty
    summary: Nonempty
    is_demo: Literal[True]


class CandidateTableSummary(CandidateSummary):
    stated_experience: str | None
    snapshot_available: bool
    match_score: float | None
    score_lower: float | None
    score_upper: float | None
    match_estimate: float | None
    confidence: Confidence | None
    availability: Availability
    ranking_score: float | None


class EvidenceClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["skill", "experience", "qualification"]
    label: Nonempty
    quote: Nonempty
    start: int = Field(strict=True, ge=0)
    end: int = Field(strict=True, gt=0)


class StoredProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claims: list[EvidenceClaim]


class CandidateDetail(CandidateSummary):
    resume_text: Nonempty
    claims: list[EvidenceClaim]
    offset_unit: Literal["unicode_code_point"] = "unicode_code_point"

    @model_validator(mode="after")
    def validate_provenance(self) -> Self:
        if any(
            value not in self.resume_text
            for value in (self.display_name, self.headline, self.summary)
        ):
            raise ValueError("Display context must appear in the synthetic source resume")
        for claim in self.claims:
            if (
                claim.start >= claim.end
                or claim.end > len(self.resume_text)
                or self.resume_text[claim.start : claim.end] != claim.quote
                or claim.label.casefold() not in claim.quote.casefold()
            ):
                raise ValueError("Evidence must match its original resume range and label")
        return self


class CandidateListResponse(BaseModel):
    job: JobDetail
    candidates: list[CandidateTableSummary]


class CandidateProfileResponse(BaseModel):
    job: JobDetail
    candidate: CandidateDetail
    availability: Availability
    assessment: Assessment | None


def candidate_availability(candidate, settings) -> Availability:
    """Stored self-reported notice details; a ranking aid, never part of the match score."""
    return describe(
        AvailabilityInput(
            status=candidate.notice_status,
            last_working_day=candidate.last_working_day,
            notice_days=candidate.notice_days,
        ),
        settings,
    )


def cached_for_candidate(entries, job, candidate, settings):
    context = ExtractionJob.from_detail(JobDetail.model_validate(job))
    source = ExtractionSource.synthetic(candidate.id, candidate.resume_text)
    return valid_assessment(entries, context, source, settings)


responses = {status: {"model": ErrorResponse} for status in (404, 422, 503)}


@router.get("", response_model=CandidateListResponse, responses=responses)
def candidates(
    job_id: JobId, response: Response, request: Request, session: CatalogSession
) -> CandidateListResponse:
    job = catalog.get_job(session, job_id)
    if job is None:
        raise HTTPException(404)
    rows = catalog.list_candidates_for_job(session, job_id)
    response.headers["Cache-Control"] = "no-store"
    summaries = []
    entries = load_cache()
    for row in rows:
        summary = CandidateSummary.model_validate(row)
        claims = StoredProfile.model_validate(row.profile).claims
        # Validate the quoted source before displaying a stated duration in the table.
        CandidateDetail(**summary.model_dump(), resume_text=row.resume_text, claims=claims)
        experience = next((claim.label for claim in claims if claim.kind == "experience"), None)
        settings = request.app.state.settings
        assessment = cached_for_candidate(entries, job, row, settings)
        scoring = assessment.scoring if assessment else None
        availability = candidate_availability(row, settings)
        summaries.append(
            CandidateTableSummary(
                **summary.model_dump(),
                stated_experience=experience,
                snapshot_available=assessment is not None,
                match_score=scoring.score if scoring else None,
                score_lower=scoring.lower if scoring else None,
                score_upper=scoring.upper if scoring else None,
                match_estimate=scoring.estimate if scoring else None,
                confidence=scoring.confidence if scoring else None,
                availability=availability,
                ranking_score=ranking_score(scoring.estimate if scoring else None, availability),
            )
        )
    return CandidateListResponse(job=JobDetail.model_validate(job), candidates=summaries)


@router.get("/{candidate_id}", response_model=CandidateProfileResponse, responses=responses)
def candidate_profile(
    job_id: JobId,
    candidate_id: CandidateId,
    response: Response,
    request: Request,
    session: CatalogSession,
) -> CandidateProfileResponse:
    job = catalog.get_job(session, job_id)
    if job is None:
        raise HTTPException(404)
    candidate = catalog.get_candidate_for_job(session, job_id, candidate_id)
    if candidate is None:
        raise HTTPException(404)
    summary = CandidateSummary.model_validate(candidate)
    profile = StoredProfile.model_validate(candidate.profile)
    detail = CandidateDetail(
        **summary.model_dump(), resume_text=candidate.resume_text, claims=profile.claims
    )
    response.headers["Cache-Control"] = "no-store"
    settings = request.app.state.settings
    return CandidateProfileResponse(
        job=JobDetail.model_validate(job),
        candidate=detail,
        availability=candidate_availability(candidate, settings),
        assessment=cached_for_candidate(load_cache(), job, candidate, settings),
    )
