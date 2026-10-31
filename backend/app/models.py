"""Curated demo catalog and metered usage. Uploaded candidates have no persistence model."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.database import SCHEMA


class Base(DeclarativeBase):
    metadata = MetaData(
        schema=SCHEMA,
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        },
    )


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="title_nonempty"),
        CheckConstraint("is_demo = true", name="demo_only"),
        CheckConstraint("jsonb_typeof(skills) = 'array'", name="skills_array"),
        CheckConstraint("jsonb_typeof(screening_criteria) = 'array'", name="criteria_array"),
        CheckConstraint("jsonb_typeof(questions) = 'array'", name="questions_array"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    client: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    skills: Mapped[list[str]] = mapped_column(JSONB)
    screening_criteria: Mapped[list[str]] = mapped_column(JSONB)
    questions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    requirements: Mapped[list[JobRequirement]] = relationship(
        order_by="JobRequirement.sort_order", lazy="raise", passive_deletes=True
    )


class JobRequirement(Base):
    __tablename__ = "job_requirements"
    __table_args__ = (
        UniqueConstraint("job_id", "sort_order"),
        CheckConstraint(
            "category IN ('mandatory','experience','preferred','qualification')", name="category"
        ),
        CheckConstraint("minimum_years IS NULL OR minimum_years >= 0", name="years_nonnegative"),
        CheckConstraint("minimum_years IS NULL OR category = 'experience'", name="years_category"),
        CheckConstraint("sort_order >= 0", name="sort_nonnegative"),
        CheckConstraint("length(trim(description)) > 0", name="description_nonempty"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.jobs.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(24))
    description: Mapped[str] = mapped_column(Text)
    minimum_years: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    sort_order: Mapped[int]


class DemoCandidate(Base):
    __tablename__ = "demo_candidates"
    __table_args__ = (
        CheckConstraint("is_demo = true", name="demo_only"),
        CheckConstraint("length(trim(resume_text)) > 0", name="resume_nonempty"),
        CheckConstraint("jsonb_typeof(profile) = 'object'", name="profile_object"),
        CheckConstraint(
            "notice_status IS NULL"
            " OR notice_status IN ('immediate','serving_notice','not_serving')",
            name="notice_status",
        ),
        CheckConstraint(
            "(notice_status IS NULL AND last_working_day IS NULL AND notice_days IS NULL)"
            " OR (notice_status = 'immediate' AND last_working_day IS NULL AND notice_days IS NULL)"
            " OR (notice_status = 'serving_notice' AND last_working_day IS NOT NULL"
            " AND notice_days IS NULL)"
            " OR (notice_status = 'not_serving' AND last_working_day IS NULL"
            " AND notice_days BETWEEN 0 AND 365)",
            name="notice_fields",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))
    headline: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(Text)
    resume_text: Mapped[str] = mapped_column(Text)
    profile: Mapped[dict[str, Any]] = mapped_column(JSONB)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # Optional self-reported availability; null means not provided, never a penalty.
    notice_status: Mapped[str | None] = mapped_column(String(24))
    last_working_day: Mapped[date | None] = mapped_column(Date)
    notice_days: Mapped[int | None]


class JobCandidate(Base):
    __tablename__ = "job_candidates"
    __table_args__ = (
        CheckConstraint(
            "demo_scenario IN ('strong','partial','weak','transferable','ambiguous','incomplete')",
            name="scenario",
        ),
    )

    job_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.jobs.id", ondelete="CASCADE"), primary_key=True
    )
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.demo_candidates.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    demo_scenario: Mapped[str] = mapped_column(String(24))


USAGE_CATEGORIES = ("pdf", "voice_response", "response_analysis", "deepgram")


class UsageEvent(Base):
    """One metered event: counts, timings and prices only, never candidate content."""

    __tablename__ = "usage_events"
    __table_args__ = (
        CheckConstraint(
            "category IN ('pdf','voice_response','response_analysis','deepgram')",
            name="category",
        ),
        Index("ix_usage_events_created_at", "created_at"),
        Index("ix_usage_events_category_created_at", "category", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # render or local: both use the same Neon database.
    origin: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(24))
    operation: Mapped[str] = mapped_column(String(32))
    # ok, or the safe error code the call ended with.
    outcome: Mapped[str] = mapped_column(String(48))
    provider: Mapped[str | None] = mapped_column(String(24))
    model_id: Mapped[str | None] = mapped_column(String(256))
    region: Mapped[str | None] = mapped_column(String(32))
    attempt: Mapped[int | None] = mapped_column(SmallInteger)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    first_output_ms: Mapped[int | None] = mapped_column(Integer)
    stop_reason: Mapped[str | None] = mapped_column(String(32))
    pages: Mapped[int | None] = mapped_column(SmallInteger)
    characters: Mapped[int | None] = mapped_column(Integer)
    seconds: Mapped[Decimal | None] = mapped_column(Numeric(10, 1))
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    screening_mode: Mapped[str | None] = mapped_column(String(8))
    candidate_kind: Mapped[str | None] = mapped_column(String(8))
    job_id: Mapped[str | None] = mapped_column(String(64))
    # A random per-screening value that groups its rows; not the session ID or capability.
    screening_ref: Mapped[str | None] = mapped_column(String(32))
    request_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
