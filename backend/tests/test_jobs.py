"""Jobs HTTP contracts and read-only sessions, without any database connection."""

import asyncio
from collections.abc import Callable
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy.exc import OperationalError

from app.api.jobs import catalog_session
from app.application import create_app
from app.config import Settings
from app.models import Job, JobRequirement
from app.seed import load_seed


def sample_jobs() -> list[Job]:
    result = []
    for source in sorted(load_seed().jobs, key=lambda job: job.title):
        job = Job(**source.model_dump(exclude={"requirements"}))
        job.requirements = [
            JobRequirement(**row.model_dump(), job_id=job.id, sort_order=i)
            for i, row in enumerate(source.requirements)
        ]
        result.append(job)
    return result


@pytest.fixture
def jobs_app(monkeypatch: pytest.MonkeyPatch):
    app = create_app(Settings(cors_allowed_origins=("http://127.0.0.1:3000",)))
    app.dependency_overrides[catalog_session] = lambda: object()
    rows = sample_jobs()
    monkeypatch.setattr("app.api.jobs.catalog.list_jobs", lambda session: rows)
    monkeypatch.setattr(
        "app.api.jobs.catalog.get_job",
        lambda session, job_id: next((job for job in rows if job.id == job_id), None),
    )
    return app


def test_list_is_typed_demo_only_and_excludes_detail_and_candidates(
    jobs_app, api_request: Callable[..., httpx.Response]
) -> None:
    response = api_request(jobs_app, "GET", "/jobs")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    rows = response.json()["jobs"]
    assert len(rows) == 4
    assert [row["title"] for row in rows] == sorted(row["title"] for row in rows)
    for row in rows:
        assert set(row) == {"id", "title", "client", "description", "skills", "is_demo"}
        assert row["is_demo"] is True


def test_job_detail_contains_ordered_requirements_and_question_references(
    jobs_app, api_request: Callable[..., httpx.Response]
) -> None:
    response = api_request(jobs_app, "GET", "/jobs/demo_ds")
    assert response.status_code == 200
    body = response.json()
    source = next(job for job in load_seed().jobs if job.id == "demo_ds")
    assert [row["id"] for row in body["requirements"]] == [row.id for row in source.requirements]
    assert [row["sort_order"] for row in body["requirements"]] == list(range(6))
    assert body["questions"] == [row.model_dump() for row in source.questions]
    assert body["requirements"][3]["minimum_years"] == 3
    assert "candidates" not in body
    assert response.headers["cache-control"] == "no-store"


def test_empty_catalog_is_not_an_error(
    jobs_app, api_request: Callable[..., httpx.Response], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.jobs.catalog.list_jobs", lambda session: [])
    response = api_request(jobs_app, "GET", "/jobs")
    assert response.status_code == 200
    assert response.json() == {"jobs": []}


@pytest.mark.parametrize("path,status", [("/jobs/demo_missing", 404), ("/jobs/invalid-id", 422)])
def test_missing_and_invalid_ids(jobs_app, api_request, path, status) -> None:
    response = api_request(jobs_app, "GET", path)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"


def test_no_database_is_a_safe_503_but_health_still_works(api_request) -> None:
    app = create_app(Settings())
    assert api_request(app, "GET", "/health").status_code == 200
    response = api_request(app, "GET", "/jobs")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"


def test_transaction_is_read_only_bounded_closed_and_database_errors_are_safe(
    monkeypatch: pytest.MonkeyPatch, api_request, caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(Settings(cors_allowed_origins=("http://127.0.0.1:3000",)))
    app.state.database_engine = object()
    session = MagicMock()
    session.scalars.side_effect = OperationalError("SQL secret", {}, Exception("credential"))
    factory = MagicMock()
    factory.return_value.__enter__.return_value = session
    monkeypatch.setattr("app.api.jobs.Session", factory)
    response = api_request(app, "GET", "/jobs", headers={"Origin": "http://127.0.0.1:3000"})
    assert response.status_code == 503
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert [str(call.args[0]) for call in session.execute.call_args_list] == [
        "SET TRANSACTION READ ONLY",
        "SET LOCAL statement_timeout = '5000ms'",
    ]
    factory.return_value.__exit__.assert_called_once()
    assert "credential" not in response.text + caplog.text
    assert "SQL secret" not in response.text + caplog.text


def test_engine_is_lazy_per_app_and_disposed_at_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = MagicMock()
    monkeypatch.setattr("app.application.create_database_engine", factory)
    app = create_app(Settings(database_url="postgresql://demo:placeholder@localhost/demo"))
    factory.assert_not_called()

    async def exercise():
        async with app.router.lifespan_context(app):
            assert app.state.database_engine is factory.return_value
            factory.return_value.connect.assert_not_called()
        factory.return_value.dispose.assert_called_once()
        assert app.state.database_engine is None

    asyncio.run(exercise())


def test_invalid_catalog_data_fails_closed(jobs_app, api_request, monkeypatch) -> None:
    rows = sample_jobs()
    rows[0].is_demo = False
    monkeypatch.setattr("app.api.jobs.catalog.list_jobs", lambda session: rows)
    response = api_request(jobs_app, "GET", "/jobs")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
