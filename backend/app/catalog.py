"""Small read-only queries for the curated catalog."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import DemoCandidate, Job, JobCandidate


def list_jobs(session: Session) -> list[Job]:
    return list(session.scalars(select(Job).order_by(Job.title)))


def list_jobs_with_counts(session: Session) -> list[tuple[Job, int]]:
    count = (
        select(func.count())
        .select_from(JobCandidate)
        .where(JobCandidate.job_id == Job.id)
        .correlate(Job)
        .scalar_subquery()
    )
    return [(job, count) for job, count in session.execute(select(Job, count).order_by(Job.title))]


def get_job(session: Session, job_id: str) -> Job | None:
    return session.scalar(select(Job).where(Job.id == job_id).options(joinedload(Job.requirements)))


def list_candidates_for_job(session: Session, job_id: str) -> list[DemoCandidate]:
    return list(
        session.scalars(
            select(DemoCandidate)
            .join(JobCandidate)
            .where(JobCandidate.job_id == job_id)
            .order_by(DemoCandidate.display_name)
        )
    )


def get_candidate_for_job(session: Session, job_id: str, candidate_id: str) -> DemoCandidate | None:
    return session.scalar(
        select(DemoCandidate)
        .join(JobCandidate)
        .where(JobCandidate.job_id == job_id, DemoCandidate.id == candidate_id)
    )
