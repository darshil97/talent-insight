"""Read-only HTTP contracts for the synthetic job catalog."""

from collections.abc import Iterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import catalog
from app.errors import ErrorResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])
JobId = Annotated[str, Path(pattern=r"^demo_[a-z0-9_]+$", max_length=64)]


class JobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    client: str
    description: str
    skills: list[str]
    is_demo: Literal[True]


class RequirementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    category: Literal["mandatory", "experience", "preferred", "qualification"]
    description: str
    minimum_years: float | None
    sort_order: int


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


def catalog_session(request: Request) -> Iterator[Session]:
    """Each request uses a bounded, read-only transaction; never seed on demand."""
    engine = request.app.state.database_engine
    if engine is None:
        raise HTTPException(503)
    try:
        with Session(engine, autoflush=False) as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            session.execute(text("SET LOCAL statement_timeout = '5000ms'"))
            yield session
    except SQLAlchemyError:
        raise HTTPException(503) from None


CatalogSession = Annotated[Session, Depends(catalog_session)]


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
