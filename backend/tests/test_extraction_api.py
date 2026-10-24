"""Job-scoped extraction API, privacy and admission tests with offline catalog snapshots."""

import asyncio
from copy import deepcopy

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


def test_demo_result_is_labeled_and_uses_real_membership_context(extraction_app, api_request):
    result = api_request(extraction_app, "POST", "/jobs/demo_ds/candidates/demo_ds_avery/structure")
    assert result.status_code == 200
    body = result.json()
    assert body["job"]["id"] == "demo_ds"
    assert body["source"]["candidate_id"] == "demo_ds_avery"
    assert body["source"]["kind"] == "synthetic_demo"
    assert body["mode"] == "mock" and body["model_id"] is None
    assert "qualification" in body["unknown_categories"]
    assert result.headers["cache-control"] == "no-store"
    assert "score" not in body and "scenario" not in body
    assert extraction_app.state.test_session_closed


@pytest.mark.parametrize(
    "path,status",
    [
        ("/jobs/demo_backend/candidates/demo_ds_avery/structure", 404),
        ("/jobs/demo_missing/candidates/demo_ds_avery/structure", 404),
        ("/jobs/invalid-id/candidates/demo_ds_avery/structure", 422),
        ("/jobs/demo_ds/candidates/invalid-id/structure", 422),
    ],
)
def test_missing_cross_job_or_invalid_context_never_calls_provider(
    extraction_app, api_request, monkeypatch, path, status
):
    calls = []

    async def provider(*args):
        calls.append(1)

    monkeypatch.setattr(extraction, "structure_resume", provider)
    result = api_request(extraction_app, "POST", path)
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


def test_uploaded_client_json_and_demo_profile_overrides_are_rejected(extraction_app, api_request):
    result = api_request(
        extraction_app, "POST", "/jobs/demo_ds/resumes/structure", json={"score": 100, "facts": []}
    )
    assert result.status_code == 415
    result = api_request(
        extraction_app,
        "POST",
        "/jobs/demo_ds/candidates/demo_ds_avery/structure",
        json={"resume_text": "Invented AWS expert"},
    )
    assert result.status_code == 400
    assert "Invented" not in result.text


def test_corrupt_demo_source_fails_before_provider(
    extraction_app, api_request, monkeypatch, caplog
):
    source = load_seed().candidates[0]
    profile = deepcopy(source.profile())
    profile["claims"][0]["quote"] = "fabricated-secret"
    candidate = DemoCandidate(**source.model_dump(exclude={"claims"}), profile=profile)
    monkeypatch.setattr(extraction.catalog, "get_candidate_for_job", lambda *args: candidate)
    response = api_request(
        extraction_app, "POST", "/jobs/demo_ds/candidates/demo_ds_avery/structure"
    )
    assert response.status_code == 500
    assert "fabricated-secret" not in response.text + caplog.text


def test_disabled_and_bad_bedrock_configuration_fail_without_mock_fallback(
    extraction_app, api_request
):
    for settings, code in [
        (Settings(), "ai_not_configured"),
        (Settings(ai_mode="bedrock"), "provider_configuration_error"),
    ]:
        extraction_app.state.settings = settings
        result = api_request(
            extraction_app, "POST", "/jobs/demo_ds/candidates/demo_ds_avery/structure"
        )
        assert result.status_code == 503 and result.json()["error"]["code"] == code
        assert not extraction_app.state.ai_requests


def test_rolling_rate_limit_has_no_resume_data(extraction_app, api_request, monkeypatch):
    extraction_app.state.settings = Settings(ai_mode="mock", ai_requests_per_minute=1)
    path = "/jobs/demo_ds/candidates/demo_ds_avery/structure"
    monkeypatch.setattr(extraction.time, "monotonic", lambda: 1000)
    assert api_request(extraction_app, "POST", path).status_code == 200
    blocked = api_request(extraction_app, "POST", path)
    assert blocked.status_code == 429 and blocked.headers["retry-after"] == "60"
    assert list(extraction_app.state.ai_requests) == [1000]
    monkeypatch.setattr(extraction.time, "monotonic", lambda: 1061)
    assert api_request(extraction_app, "POST", path).status_code == 200


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
            path = "/jobs/demo_ds/candidates/demo_ds_avery/structure"
            first = asyncio.create_task(client.post(path))
            await started.wait()
            blocked = await client.post(path)
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
        "/jobs/demo_ds/candidates/demo_ds_avery/structure",
        headers={"Origin": "http://127.0.0.1:3000"},
    )
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert load_seed().candidates[0].resume_text not in response.text + caplog.text
    assert extraction_app.state.ai_active == 0
