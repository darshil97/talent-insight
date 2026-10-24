"""Create the curated demo catalog in its own schema.

Revision ID: 0001_demo_catalog
Revises: none
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_demo_catalog"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fail rather than adopt an existing unversioned schema with unknown contents.
    op.execute("CREATE SCHEMA talent_insight")
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("client", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("skills", postgresql.JSONB(), nullable=False),
        sa.Column("screening_criteria", postgresql.JSONB(), nullable=False),
        sa.Column("questions", postgresql.JSONB(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint("length(trim(title)) > 0", name=op.f("ck_jobs_title_nonempty")),
        sa.CheckConstraint("is_demo = true", name=op.f("ck_jobs_demo_only")),
        sa.CheckConstraint("jsonb_typeof(skills) = 'array'", name=op.f("ck_jobs_skills_array")),
        sa.CheckConstraint(
            "jsonb_typeof(screening_criteria) = 'array'", name=op.f("ck_jobs_criteria_array")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(questions) = 'array'", name=op.f("ck_jobs_questions_array")
        ),
        schema="talent_insight",
    )
    op.create_table(
        "job_requirements",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(64),
            sa.ForeignKey("talent_insight.jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("minimum_years", sa.Numeric(4, 1), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.UniqueConstraint("job_id", "sort_order", name=op.f("uq_job_requirements_job_id")),
        sa.CheckConstraint(
            "category IN ('mandatory','experience','preferred','qualification')",
            name=op.f("ck_job_requirements_category"),
        ),
        sa.CheckConstraint(
            "minimum_years IS NULL OR minimum_years >= 0",
            name=op.f("ck_job_requirements_years_nonnegative"),
        ),
        sa.CheckConstraint(
            "minimum_years IS NULL OR category = 'experience'",
            name=op.f("ck_job_requirements_years_category"),
        ),
        sa.CheckConstraint("sort_order >= 0", name=op.f("ck_job_requirements_sort_nonnegative")),
        sa.CheckConstraint(
            "length(trim(description)) > 0", name=op.f("ck_job_requirements_description_nonempty")
        ),
        schema="talent_insight",
    )
    op.create_index(
        "ix_job_requirements_job_id", "job_requirements", ["job_id"], schema="talent_insight"
    )
    op.create_table(
        "demo_candidates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("headline", sa.String(160), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("resume_text", sa.Text(), nullable=False),
        sa.Column("profile", postgresql.JSONB(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint("is_demo = true", name=op.f("ck_demo_candidates_demo_only")),
        sa.CheckConstraint(
            "length(trim(resume_text)) > 0", name=op.f("ck_demo_candidates_resume_nonempty")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(profile) = 'object'", name=op.f("ck_demo_candidates_profile_object")
        ),
        schema="talent_insight",
    )
    op.create_table(
        "job_candidates",
        sa.Column(
            "job_id",
            sa.String(64),
            sa.ForeignKey("talent_insight.jobs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "candidate_id",
            sa.String(64),
            sa.ForeignKey("talent_insight.demo_candidates.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("demo_scenario", sa.String(24), nullable=False),
        sa.CheckConstraint(
            "demo_scenario IN ('strong','partial','weak','transferable','ambiguous','incomplete')",
            name=op.f("ck_job_candidates_scenario"),
        ),
        schema="talent_insight",
    )
    op.create_index(
        "ix_job_candidates_candidate_id",
        "job_candidates",
        ["candidate_id"],
        schema="talent_insight",
    )


def downgrade() -> None:
    op.drop_table("job_candidates", schema="talent_insight")
    op.drop_table("job_requirements", schema="talent_insight")
    op.drop_table("demo_candidates", schema="talent_insight")
    op.drop_table("jobs", schema="talent_insight")
    op.execute("DROP SCHEMA talent_insight RESTRICT")
