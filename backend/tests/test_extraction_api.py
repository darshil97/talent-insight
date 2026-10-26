"""Job-scoped extraction API, privacy and admission tests with offline catalog snapshots."""

import asyncio

import httpx
import pytest
from test_resumes import pdf

from app.api import extraction
from app.application import create_app
from app.config import Settings
from app.extraction_contracts import ExtractionFailure
from app.models import DemoCandidate, Job, JobRequirement
from app.seed import load_seed


@pytest.fixture
def extraction_app(monkeypatch):
    data = load_seed()
    app = create_app(Settings(ai_mode="mock", cors_allowed_origins=("http://127.0.0.1:3000",)))
    jobs = {}
    for row in data.jobs:
        job = Job(**row.model_dump(exclude={"requirements"}))
        job.requirements = [
            JobRequirement(**requirement.model_dump(), job_id=row.id, sort_order=i)
            for i, requirement in enumerate(row.requirements)
        ]
        jobs[row.id] = job
    candidates = {
        row.id: DemoCandidate(**row.model_dump(exclude={"claims"}), profile=row.profile())
        for row in data.candidates
    }
    pairs = {(row.job_id, row.candidate_id) for row in data.memberships}
    app.state.test_session_closed = False

    def session(request):
        request.app.state.test_session_closed = False
        try:
            yield object()
        finally:
            request.app.state.test_session_closed = True

    monkeypatch.setattr(extraction, "catalog_session", session)
    monkeypatch.setattr(extraction.catalog, "get_job", lambda session, job_id: jobs.get(job_id))
    monkeypatch.setattr(
        extraction.catalog,
        "get_candidate_for_job",
        lambda session, job_id, candidate_id: (
            candidates.get(candidate_id) if (job_id, candidate_id) in pairs else None
        ),
    )
    return app


def test_demo_provider_routes_are_removed(extraction_app, api_request):
    for suffix in ("structure", "assess"):
        response = api_request(
            extraction_app, "POST", f"/jobs/demo_ds/candidates/demo_ds_avery/{suffix}"
        )
        assert response.status_code == 404
    assert not extraction_app.state.ai_requests


def test_assessment_routes_are_temporary_and_mock_scores_stay_unavailable(
    extraction_app, api_request
):
    demo = api_request(extraction_app, "POST", "/jobs/demo_ds/candidates/demo_ds_avery/assess")
    assert demo.status_code == 404
    uploaded = api_request(
        extraction_app,
        "POST",
        "/jobs/demo_ds/resumes/assess",
        content=pdf(("SYNTHETIC RESUME\nUsed Python and SQL.",)),
        headers={"Content-Type": "application/pdf"},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["structured"]["source"]["candidate_id"] is None
    assert uploaded.json()["scoring"]["score"] is None
    assert uploaded.headers["cache-control"] == "no-store"


def test_assessment_rejects_cross_job_and_client_supplied_results(extraction_app, api_request):
    assert (
        api_request(
            extraction_app,
            "POST",
            "/jobs/demo_ds/candidates/demo_ds_avery/assess",
            json={"score": 100},
        ).status_code
        == 404
    )
    assert (
        api_request(
            extraction_app,
            "POST",
            "/jobs/demo_ds/resumes/assess",
            json={"score": 100},
        ).status_code
        == 415
    )


@pytest.mark.parametrize(
    "path,status",
    [
        ("/jobs/demo_missing/resumes/structure", 404),
        ("/jobs/invalid-id/resumes/structure", 422),
    ],
)
def test_missing_cross_job_or_invalid_context_never_calls_provider(
    extraction_app, api_request, monkeypatch, path, status
):
    calls = []

    async def provider(*args):
        calls.append(1)

    monkeypatch.setattr(extraction, "structure_resume", provider)
    result = api_request(
        extraction_app,
        "POST",
        path,
        content=pdf(("SYNTHETIC RESUME\nUsed Python.",)),
        headers={"Content-Type": "application/pdf"},
    )
    assert result.status_code == status and calls == []
    assert "Avery" not in result.text


def test_upload_uses_server_parsed_pdf_and_releases_database_before_ai(
    extraction_app, api_request, monkeypatch
):
    original = extraction.structure_resume

    async def wrapped(*args):
        assert extraction_app.state.test_session_closed
        return await original(*args)

    monkeypatch.setattr(extraction, "structure_resume", wrapped)
    result = api_request(
        extraction_app,
        "POST",
        "/jobs/demo_ds/resumes/structure",
        content=pdf(("SYNTHETIC RESUME\nUsed Python and SQL.",)),
        headers={"Content-Type": "application/pdf"},
    )
    assert result.status_code == 200
    body = result.json()
    assert body["source"]["kind"] == "uploaded_pdf"
    assert body["source"]["candidate_id"] is None
    assert {fact["value"] for fact in body["facts"]} == {"Python", "SQL"}
    assert result.headers["cache-control"] == "no-store"
    assert extraction_app.state.ai_active == extraction_app.state.resume_active == 0


def test_uploaded_client_json_is_rejected(extraction_app, api_request):
    result = api_request(
        extraction_app, "POST", "/jobs/demo_ds/resumes/structure", json={"score": 100, "facts": []}
    )
    assert result.status_code == 415


def test_disabled_and_bad_bedrock_configuration_fail_without_mock_fallback(
    extraction_app, api_request
):
    for settings, code in [
        (Settings(), "ai_not_configured"),
        (Settings(ai_mode="bedrock"), "provider_configuration_error"),
    ]:
        extraction_app.state.settings = settings
        result = api_request(
            extraction_app,
            "POST",
            "/jobs/demo_ds/resumes/structure",
            content=pdf(("SYNTHETIC RESUME\nUsed Python.",)),
            headers={"Content-Type": "application/pdf"},
        )
        assert result.status_code == 503 and result.json()["error"]["code"] == code
        assert not extraction_app.state.ai_requests


def test_rolling_rate_limit_has_no_resume_data(extraction_app, api_request, monkeypatch):
    extraction_app.state.settings = Settings(ai_mode="mock", ai_requests_per_minute=1)
    path = "/jobs/demo_ds/resumes/structure"
    monkeypatch.setattr(extraction.time, "monotonic", lambda: 1000)
    payload = pdf(("SYNTHETIC RESUME\nUsed Python.",))
    headers = {"Content-Type": "application/pdf"}
    assert (
        api_request(extraction_app, "POST", path, content=payload, headers=headers).status_code
        == 200
    )
    blocked = api_request(extraction_app, "POST", path, content=payload, headers=headers)
    assert blocked.status_code == 429 and blocked.headers["retry-after"] == "60"
    assert list(extraction_app.state.ai_requests) == [1000]
    monkeypatch.setattr(extraction.time, "monotonic", lambda: 1061)
    assert (
        api_request(extraction_app, "POST", path, content=payload, headers=headers).status_code
        == 200
    )


def test_concurrent_admission_and_cancellation_free_capacity(extraction_app, monkeypatch):
    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def pending(*args):
            started.set()
            await release.wait()

        monkeypatch.setattr(extraction, "structure_resume", pending)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(extraction_app), base_url="http://test"
        ) as client:
            path = "/jobs/demo_ds/resumes/structure"
            payload = pdf(("SYNTHETIC RESUME\nUsed Python.",))
            first = asyncio.create_task(
                client.post(path, content=payload, headers={"Content-Type": "application/pdf"})
            )
            await started.wait()
            blocked = await client.post(
                path, content=payload, headers={"Content-Type": "application/pdf"}
            )
            assert blocked.status_code == 503 and blocked.json()["error"]["code"] == "ai_busy"
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            assert extraction_app.state.ai_active == 0

    asyncio.run(run())


@pytest.mark.parametrize(
    "code,status",
    [
        ("invalid_evidence", 502),
        ("provider_access_denied", 503),
        ("ai_timeout", 504),
        ("provider_throttled", 503),
    ],
)
def test_errors_are_safe_no_store_and_cors_wrapped(
    extraction_app, api_request, monkeypatch, caplog, code, status
):
    async def failed(*args):
        raise ExtractionFailure(code)

    monkeypatch.setattr(extraction, "structure_resume", failed)
    response = api_request(
        extraction_app,
        "POST",
        "/jobs/demo_ds/resumes/structure",
        content=pdf(("SYNTHETIC RESUME\nUsed Python.",)),
        headers={"Origin": "http://127.0.0.1:3000", "Content-Type": "application/pdf"},
    )
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert load_seed().candidates[0].resume_text not in response.text + caplog.text
    assert extraction_app.state.ai_active == 0
