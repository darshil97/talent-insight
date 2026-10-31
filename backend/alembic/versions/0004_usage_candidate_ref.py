"""Add candidate_ref to usage events, linking one candidate's resume, screening and report rows.

Revision ID: 0004_usage_candidate_ref
Revises: 0003_usage_events
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_usage_candidate_ref"
down_revision = "0003_usage_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Additive and nullable: existing rows keep no reference.
    op.add_column(
        "usage_events",
        sa.Column("candidate_ref", sa.String(64), nullable=True),
        schema="talent_insight",
    )


def downgrade() -> None:
    op.drop_column("usage_events", "candidate_ref", schema="talent_insight")
