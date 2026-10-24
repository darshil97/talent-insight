"""Job-scoped synthetic candidate views with validated resume provenance."""

from typing import Annotated, Literal, Self

from fastapi import APIRouter, HTTPException, Path, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app import catalog
from app.api.jobs import CatalogSession, JobId, JobSummary
from app.errors import ErrorResponse

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
    job: JobSummary
    candidates: list[CandidateSummary]


class CandidateProfileResponse(BaseModel):
    job: JobSummary
    candidate: CandidateDetail


responses = {status: {"model": ErrorResponse} for status in (404, 422, 503)}


@router.get("", response_model=CandidateListResponse, responses=responses)
def candidates(job_id: JobId, response: Response, session: CatalogSession) -> CandidateListResponse:
    job = catalog.get_job(session, job_id)
    if job is None:
        raise HTTPException(404)
    rows = catalog.list_candidates_for_job(session, job_id)
    response.headers["Cache-Control"] = "no-store"
    return CandidateListResponse(
        job=JobSummary.model_validate(job),
        candidates=[CandidateSummary.model_validate(row) for row in rows],
    )


@router.get("/{candidate_id}", response_model=CandidateProfileResponse, responses=responses)
def candidate_profile(
    job_id: JobId, candidate_id: CandidateId, response: Response, session: CatalogSession
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
    return CandidateProfileResponse(job=JobSummary.model_validate(job), candidate=detail)
