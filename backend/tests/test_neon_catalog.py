"""Opt-in checks on the shared catalog. Every connection is transaction-read-only."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from app.catalog import get_candidate_for_job, get_job, list_candidates_for_job, list_jobs
from app.config import load_settings
from app.database import SCHEMA, create_database_engine
from app.models import Base
from app.seed import load_seed

pytestmark = pytest.mark.neon


@pytest.fixture
def neon_connection() -> Iterator[Connection]:
    settings = load_settings()
    if settings.database_url is None:
        pytest.fail("Configure the shared Neon DATABASE_URL before using --neon.")
    engine = create_database_engine(settings.database_url)
    try:
        if not (engine.url.host or "").endswith(".neon.tech"):
            pytest.fail("The configured integration target must be Neon.")
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            assert connection.scalar(text("SHOW transaction_read_only")) == "on"
            yield connection
    finally:
        engine.dispose()


def test_neon_revision_and_model_parity(neon_connection: Connection) -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    assert (
        neon_connection.scalar(
            text("SELECT version_num FROM public.talent_insight_alembic_version")
        )
        == head
    )
    context = MigrationContext.configure(
        neon_connection,
        opts={
            "include_schemas": True,
            "include_name": lambda name, kind, parents: kind != "schema" or name == SCHEMA,
            "compare_type": True,
        },
    )
    assert compare_metadata(context, Base.metadata) == []


def test_neon_catalog_and_membership(neon_connection: Connection) -> None:
    data = load_seed()
    with Session(bind=neon_connection) as session:
        assert {job.id for job in data.jobs} <= {job.id for job in list_jobs(session)}
        for source in data.jobs:
            job = get_job(session, source.id)
            assert job is not None
            assert [r.id for r in job.requirements] == [r.id for r in source.requirements]
            expected = {m.candidate_id for m in data.memberships if m.job_id == source.id}
            actual = {c.id for c in list_candidates_for_job(session, source.id)}
            assert expected <= actual
        assert get_candidate_for_job(session, "demo_ds", "demo_ds_avery") is not None
        assert get_candidate_for_job(session, "demo_backend", "demo_ds_avery") is None
        assert get_job(session, "missing") is None


def test_neon_evidence_matches_original_resumes(neon_connection: Connection) -> None:
    sources = {candidate.id: candidate for candidate in load_seed().candidates}
    with Session(bind=neon_connection) as session:
        for member in load_seed().memberships:
            candidate = get_candidate_for_job(session, member.job_id, member.candidate_id)
            assert candidate is not None
            assert candidate.is_demo is True
            assert candidate.resume_text == sources[candidate.id].resume_text
            assert candidate.profile == sources[candidate.id].profile()
