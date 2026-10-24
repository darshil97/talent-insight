"""Validated, atomic, repeatable seeding of synthetic catalog records only."""

import json
from importlib.resources import files
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import load_settings
from app.database import create_database_engine
from app.models import DemoCandidate, Job, JobCandidate, JobRequirement

DemoId = Annotated[str, StringConstraints(pattern=r"^demo_[a-z0-9_]+$", max_length=64)]
Nonempty = Annotated[str, StringConstraints(min_length=1)]


class SeedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequirementSeed(SeedModel):
    id: DemoId
    category: Literal["mandatory", "experience", "preferred", "qualification"]
    description: Nonempty
    minimum_years: float | None = Field(default=None, ge=0, le=99)

    @model_validator(mode="after")
    def years_are_experience(self) -> Self:
        if self.minimum_years is not None and self.category != "experience":
            raise ValueError("Year thresholds belong only to experience requirements")
        return self


class QuestionSeed(SeedModel):
    id: DemoId
    text: Nonempty
    requirement_ids: list[DemoId] = Field(min_length=1)


class JobSeed(SeedModel):
    id: DemoId
    title: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    client: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    description: Nonempty
    skills: list[Nonempty] = Field(min_length=1)
    screening_criteria: list[Nonempty] = Field(min_length=1)
    questions: list[QuestionSeed] = Field(min_length=1)
    requirements: list[RequirementSeed] = Field(min_length=1)
    is_demo: Literal[True] = True

    @model_validator(mode="after")
    def question_references(self) -> Self:
        ids = {row.id for row in self.requirements}
        if any(not set(question.requirement_ids) <= ids for question in self.questions):
            raise ValueError("Screening questions must reference this job's requirements")
        return self


class EvidenceSeed(SeedModel):
    kind: Literal["skill", "experience", "qualification"]
    label: Nonempty
    quote: Nonempty


class CandidateSeed(SeedModel):
    id: DemoId
    display_name: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    headline: Annotated[str, StringConstraints(min_length=1, max_length=160)]
    summary: Nonempty
    resume_text: Nonempty
    claims: list[EvidenceSeed]
    is_demo: Literal[True] = True

    @model_validator(mode="after")
    def evidence_is_in_resume(self) -> Self:
        for value in (self.display_name, self.headline, self.summary):
            if value not in self.resume_text:
                raise ValueError("Candidate display context must appear in the synthetic resume")
        for claim in self.claims:
            if (
                claim.quote not in self.resume_text
                or claim.label.casefold() not in claim.quote.casefold()
            ):
                raise ValueError("Structured claims need a supporting original resume excerpt")
        return self

    def profile(self) -> dict:
        return {
            "claims": [
                {
                    **claim.model_dump(),
                    "start": self.resume_text.index(claim.quote),
                    "end": self.resume_text.index(claim.quote) + len(claim.quote),
                }
                for claim in self.claims
            ]
        }


class MembershipSeed(SeedModel):
    job_id: DemoId
    candidate_id: DemoId
    demo_scenario: Literal["strong", "partial", "weak", "transferable", "ambiguous", "incomplete"]


class CatalogSeed(SeedModel):
    jobs: list[JobSeed] = Field(min_length=1)
    candidates: list[CandidateSeed] = Field(min_length=1)
    memberships: list[MembershipSeed] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids_and_references(self) -> Self:
        groups = [
            self.jobs,
            self.candidates,
            [r for job in self.jobs for r in job.requirements],
            [q for job in self.jobs for q in job.questions],
        ]
        for rows in groups:
            if len({row.id for row in rows}) != len(rows):
                raise ValueError("Seed identifiers must be unique")
        jobs = {row.id for row in self.jobs}
        candidates = {row.id for row in self.candidates}
        pairs = {(row.job_id, row.candidate_id) for row in self.memberships}
        if len(pairs) != len(self.memberships):
            raise ValueError("Duplicate job-candidate membership")
        if any(j not in jobs or c not in candidates for j, c in pairs):
            raise ValueError("Membership references an unknown job or candidate")
        if {j for j, _ in pairs} != jobs or {c for _, c in pairs} != candidates:
            raise ValueError("Every job and candidate must belong to a demo pool")
        return self


def load_seed() -> CatalogSeed:
    data = files("app").joinpath("fixtures/catalog.json").read_text(encoding="utf-8")
    return CatalogSeed.model_validate_json(data)


def seed_catalog(engine: Engine, data: CatalogSeed | None = None) -> dict[str, int]:
    data = data if data is not None else load_seed()
    # Revalidate supplied models as well; model_copy/model_construct can bypass validation.
    data = CatalogSeed.model_validate(data.model_dump())
    job_rows, requirement_rows = [], []
    for job in data.jobs:
        job_rows.append(job.model_dump(exclude={"requirements"}))
        requirement_rows.extend(
            {**row.model_dump(), "job_id": job.id, "sort_order": i}
            for i, row in enumerate(job.requirements)
        )
    candidate_rows = [
        {**row.model_dump(exclude={"claims"}), "profile": row.profile()} for row in data.candidates
    ]
    membership_rows = [row.model_dump() for row in data.memberships]
    batches = [
        (Job, job_rows, ["id"]),
        (JobRequirement, requirement_rows, ["id"]),
        (DemoCandidate, candidate_rows, ["id"]),
        (JobCandidate, membership_rows, ["job_id", "candidate_id"]),
    ]
    with Session(engine) as session, session.begin():
        for model, rows, key in batches:
            statement = insert(model).values(rows)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=key,
                    set_={
                        name: getattr(statement.excluded, name)
                        for name in rows[0]
                        if name not in key
                    },
                )
            )
    return {
        "jobs": len(job_rows),
        "requirements": len(requirement_rows),
        "candidates": len(candidate_rows),
        "memberships": len(membership_rows),
    }


def main() -> None:
    settings = load_settings()
    if settings.database_url is None:
        raise SystemExit("Configure DATABASE_URL for the existing talent-insight Neon project.")
    engine = create_database_engine(settings.database_url)
    try:
        counts = seed_catalog(engine)
    except (SQLAlchemyError, ValueError):
        raise SystemExit(
            "Seeding failed. Check migrations, database access and fixture validity."
        ) from None
    finally:
        engine.dispose()
    print(json.dumps({"seeded_demo_records": counts}))


if __name__ == "__main__":
    main()
