"""Review initial DDL without connecting to any database."""

import io
from pathlib import Path

from alembic.config import Config

from alembic import command


def test_offline_migration_preview_needs_no_credentials() -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.output_buffer = io.StringIO()
    command.upgrade(config, "head", sql=True)
    output = config.output_buffer.getvalue()
    assert "CREATE SCHEMA talent_insight" in output
    assert "CREATE TABLE talent_insight.demo_candidates" in output
    assert "DROP TABLE" not in output
    assert "ALTER TABLE talent_insight.demo_candidates ADD COLUMN notice_status" in output
    assert "ADD COLUMN last_working_day DATE" in output
    assert "ADD COLUMN notice_days INTEGER" in output
    assert "ck_demo_candidates_notice_fields" in output
    assert "DROP COLUMN" not in output
    assert "CREATE TABLE talent_insight.usage_events" in output
    assert "ck_usage_events_category" in output
    assert "CREATE INDEX ix_usage_events_category_created_at" in output
