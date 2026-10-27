"""Read-only HTTP contracts for the synthetic job catalog."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict

from app import catalog
from app.api.deps import CatalogSession, JobId
from app.errors import ErrorResponse
from app.pipeline.contracts import RequirementResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    client: str
    description: str
    skills: list[str]
    is_demo: Literal[True]


class QuestionResponse(BaseModel):
    id: str
    text: str
    requirement_ids: list[str]


class JobDetail(JobSummary):
    requirements: list[RequirementResponse]
    screening_criteria: list[str]
    questions: list[QuestionResponse]


class JobListResponse(BaseModel):
    jobs: list[JobSummary]


@router.get("", response_model=JobListResponse, responses={503: {"model": ErrorResponse}})
def jobs(response: Response, session: CatalogSession) -> JobListResponse:
    response.headers["Cache-Control"] = "no-store"
    return JobListResponse(
        jobs=[JobSummary.model_validate(job) for job in catalog.list_jobs(session)]
    )


@router.get(
    "/{job_id}",
    response_model=JobDetail,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def job_detail(job_id: JobId, response: Response, session: CatalogSession) -> JobDetail:
    job = catalog.get_job(session, job_id)
    if job is None:
        raise HTTPException(404)
    response.headers["Cache-Control"] = "no-store"
    return JobDetail.model_validate(job)
