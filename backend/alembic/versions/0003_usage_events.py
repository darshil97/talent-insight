"""Add metered usage events: counts, timings and prices only, never candidate content.

Revision ID: 0003_usage_events
Revises: 0002_candidate_availability
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_usage_events"
down_revision = "0002_candidate_availability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A new table only; no existing table or row changes.
    op.create_table(
        "usage_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("outcome", sa.String(48), nullable=False),
        sa.Column("provider", sa.String(24), nullable=True),
        sa.Column("model_id", sa.String(256), nullable=True),
        sa.Column("region", sa.String(32), nullable=True),
        sa.Column("attempt", sa.SmallInteger(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("first_output_ms", sa.Integer(), nullable=True),
        sa.Column("stop_reason", sa.String(32), nullable=True),
        sa.Column("pages", sa.SmallInteger(), nullable=True),
        sa.Column("characters", sa.Integer(), nullable=True),
        sa.Column("seconds", sa.Numeric(10, 1), nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("screening_mode", sa.String(8), nullable=True),
        sa.Column("candidate_kind", sa.String(8), nullable=True),
        sa.Column("job_id", sa.String(64), nullable=True),
        sa.Column("screening_ref", sa.String(32), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "category IN ('pdf','voice_response','response_analysis','deepgram')",
            name=op.f("ck_usage_events_category"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_events")),
        schema="talent_insight",
    )
    op.create_index(
        "ix_usage_events_created_at", "usage_events", ["created_at"], schema="talent_insight"
    )
    op.create_index(
        "ix_usage_events_category_created_at",
        "usage_events",
        ["category", "created_at"],
        schema="talent_insight",
    )


def downgrade() -> None:
    op.drop_index("ix_usage_events_category_created_at", "usage_events", schema="talent_insight")
    op.drop_index("ix_usage_events_created_at", "usage_events", schema="talent_insight")
    op.drop_table("usage_events", schema="talent_insight")
