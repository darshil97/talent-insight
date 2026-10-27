"""Add optional self-reported availability to synthetic demo candidates.

Revision ID: 0002_candidate_availability
Revises: 0001_demo_catalog
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_candidate_availability"
down_revision = "0001_demo_catalog"
branch_labels = None
depends_on = None

FIELDS = (
    "(notice_status IS NULL AND last_working_day IS NULL AND notice_days IS NULL)"
    " OR (notice_status = 'immediate' AND last_working_day IS NULL AND notice_days IS NULL)"
    " OR (notice_status = 'serving_notice' AND last_working_day IS NOT NULL"
    " AND notice_days IS NULL)"
    " OR (notice_status = 'not_serving' AND last_working_day IS NULL"
    " AND notice_days BETWEEN 0 AND 365)"
)


def upgrade() -> None:
    # Additive and nullable: existing rows stay valid as "not provided" until reseeded.
    op.add_column(
        "demo_candidates",
        sa.Column("notice_status", sa.String(24), nullable=True),
        schema="talent_insight",
    )
    op.add_column(
        "demo_candidates",
        sa.Column("last_working_day", sa.Date(), nullable=True),
        schema="talent_insight",
    )
    op.add_column(
        "demo_candidates",
        sa.Column("notice_days", sa.Integer(), nullable=True),
        schema="talent_insight",
    )
    op.create_check_constraint(
        op.f("ck_demo_candidates_notice_status"),
        "demo_candidates",
        "notice_status IS NULL OR notice_status IN ('immediate','serving_notice','not_serving')",
        schema="talent_insight",
    )
    op.create_check_constraint(
        op.f("ck_demo_candidates_notice_fields"),
        "demo_candidates",
        FIELDS,
        schema="talent_insight",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_demo_candidates_notice_fields"), "demo_candidates", schema="talent_insight"
    )
    op.drop_constraint(
        op.f("ck_demo_candidates_notice_status"), "demo_candidates", schema="talent_insight"
    )
    op.drop_column("demo_candidates", "notice_days", schema="talent_insight")
    op.drop_column("demo_candidates", "last_working_day", schema="talent_insight")
    op.drop_column("demo_candidates", "notice_status", schema="talent_insight")
