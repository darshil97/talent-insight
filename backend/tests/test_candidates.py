"""Candidate membership and evidence checks never connect to a database."""

import asyncio
from copy import deepcopy
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError

from app.api.jobs import catalog_session
from app.application import create_app
from app.catalog import get_candidate_for_job, list_candidates_for_job
from app.config import Settings
from app.demo_cache import CacheEntry, assessment_digest, load_cache
from app.models import DemoCandidate, Job, JobRequirement
from app.refresh_demo import build_cache
from app.seed import load_seed


@pytest.fixture
def candidates_app(monkeypatch):
    app = create_app(Settings(cors_allowed_origins=("http://127.0.0.1:3000",)))
    app.dependency_overrides[catalog_session] = lambda: object()
    data = load_seed()
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
    monkeypatch.setattr(
        "app.api.candidates.catalog.get_job", lambda session, job_id: jobs.get(job_id)
    )
    monkeypatch.setattr(
        "app.api.candidates.catalog.list_candidates_for_job",
        lambda session, job_id: sorted(
            (row for row in candidates.values() if (job_id, row.id) in pairs),
            key=lambda row: row.display_name,
        ),
    )
    monkeypatch.setattr(
        "app.api.candidates.catalog.get_candidate_for_job",
        lambda session, job_id, candidate_id: (
            candidates.get(candidate_id) if (job_id, candidate_id) in pairs else None
        ),
    )
    monkeypatch.setattr("app.api.candidates.load_cache", lambda: {})
    return app


def test_pool_and_profile_read_current_snapshot_without_provider(
    candidates_app, api_request, monkeypatch
):
    document = asyncio.run(build_cache(load_seed(), Settings(ai_mode="mock")))
    row = next(
        row
        for row in document.entries
        if (row.job_id, row.candidate_id) == ("demo_ds", "demo_ds_avery")
    )
    structured = row.assessment.structured.model_copy(
        update={"mode": "bedrock", "model_id": "test"}
    )
    entry = CacheEntry(
        job_id=row.job_id,
        candidate_id=row.candidate_id,
        fingerprint=row.fingerprint,
        assessment_digest=assessment_digest(
            row.assessment.model_copy(update={"structured": structured})
        ),
        assessment=row.assessment.model_copy(update={"structured": structured}),
    )
    monkeypatch.setattr(
        "app.api.candidates.load_cache", lambda: {(row.job_id, row.candidate_id): entry}
    )

    async def no_provider(*args, **kwargs):
        raise AssertionError("Browsing a demo candidate must not call a provider")

    monkeypatch.setattr("app.extraction.structure_resume", no_provider)
    pool = api_request(candidates_app, "GET", "/jobs/demo_ds/candidates")
    assert pool.status_code == 200
    summary = next(item for item in pool.json()["candidates"] if item["id"] == row.candidate_id)
    assert (summary["match_score"], summary["score_lower"], summary["score_upper"]) == (
        None,
        0,
        100,
    )
    assert summary["snapshot_available"] is True
    profile = api_request(candidates_app, "GET", "/jobs/demo_ds/candidates/demo_ds_avery")
    assert profile.status_code == 200
    assert profile.json()["assessment"]["structured"]["source"]["candidate_id"] == row.candidate_id


def test_versioned_snapshot_is_served_for_every_demo_member(
    candidates_app, api_request, monkeypatch
):
    entries = load_cache()
    assert len(entries) == len(load_seed().memberships) == 13
    monkeypatch.setattr("app.api.candidates.load_cache", lambda: entries)
    pool = api_request(candidates_app, "GET", "/jobs/demo_ds/candidates")
    assert pool.status_code == 200
    theo = next(row for row in pool.json()["candidates"] if row["id"] == "demo_backend_theo")
    assert theo["snapshot_available"] is True
    profile = api_request(candidates_app, "GET", "/jobs/demo_ds/candidates/demo_backend_theo")
    assessment = profile.json()["assessment"]
    assert assessment is not None
    assert assessment["structured"]["source"]["candidate_id"] == "demo_backend_theo"
    assert (theo["match_score"], theo["score_lower"], theo["score_upper"]) == (
        assessment["scoring"]["score"],
        assessment["scoring"]["lower"],
        assessment["scoring"]["upper"],
    )


@pytest.mark.parametrize("job_id", ["demo_ds", "demo_backend", "demo_hr_ops", "demo_marketing_ops"])
def test_list_contains_only_job_members_and_public_summary_fields(
    candidates_app, api_request, job_id
):
    response = api_request(candidates_app, "GET", f"/jobs/{job_id}/candidates")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["job"]["id"] == job_id
    rows = body["candidates"]
    assert len(rows) == (4 if job_id == "demo_ds" else 3)
    assert [row["display_name"] for row in rows] == sorted(row["display_name"] for row in rows)
    expected = {row.candidate_id for row in load_seed().memberships if row.job_id == job_id}
    assert {row["id"] for row in rows} == expected
    for row in rows:
        assert set(row) == {
            "id",
            "display_name",
            "headline",
            "summary",
            "is_demo",
            "stated_experience",
            "snapshot_available",
            "match_score",
            "score_lower",
            "score_upper",
        }
        assert row["is_demo"] is True
        source = next(item for item in load_seed().candidates if item.id == row["id"])
        expected_years = next(
            (claim.label for claim in source.claims if claim.kind == "experience"), None
        )
        assert row["stated_experience"] == expected_years
        assert row["match_score"] is None
        assert row["snapshot_available"] is False


def test_all_profiles_preserve_original_text_and_validated_evidence(candidates_app, api_request):
    data = load_seed()
    sources = {row.id: row for row in data.candidates}
    for member in data.memberships:
        response = api_request(
            candidates_app, "GET", f"/jobs/{member.job_id}/candidates/{member.candidate_id}"
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        body = response.json()
        candidate = body["candidate"]
        source = sources[member.candidate_id]
        assert body["job"]["id"] == member.job_id
        assert candidate["resume_text"] == source.resume_text
        assert candidate["claims"] == source.profile()["claims"]
        assert candidate["offset_unit"] == "unicode_code_point"
        assert set(candidate) == {
            "id",
            "display_name",
            "headline",
            "summary",
            "is_demo",
            "resume_text",
            "claims",
            "offset_unit",
        }
        assert body["assessment"] is None


@pytest.mark.parametrize(
    "path,status",
    [
        ("/jobs/demo_backend/candidates/demo_ds_avery", 404),
        ("/jobs/demo_missing/candidates", 404),
        ("/jobs/demo_missing/candidates/demo_ds_avery", 404),
        ("/jobs/demo_ds/candidates/demo_missing", 404),
        ("/jobs/not-valid/candidates", 422),
        ("/jobs/demo_ds/candidates/not-valid", 422),
    ],
)
def test_missing_and_cross_job_candidates_are_not_exposed(
    candidates_app, api_request, path, status
):
    response = api_request(candidates_app, "GET", path)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert "Avery" not in response.text


def test_empty_pool_is_distinct_from_a_missing_job(candidates_app, api_request, monkeypatch):
    monkeypatch.setattr(
        "app.api.candidates.catalog.list_candidates_for_job", lambda session, job_id: []
    )
    response = api_request(candidates_app, "GET", "/jobs/demo_ds/candidates")
    assert response.status_code == 200
    assert response.json()["candidates"] == []
    assert response.json()["job"]["id"] == "demo_ds"


@pytest.mark.parametrize(
    "mutation", ["quote", "offset", "range", "label", "kind", "summary", "real"]
)
def test_corrupt_profile_fails_closed_without_leaking_resume(
    candidates_app, api_request, monkeypatch, caplog, mutation
):
    source = load_seed().candidates[0]
    candidate = DemoCandidate(
        **source.model_dump(exclude={"claims"}), profile=deepcopy(source.profile())
    )
    if mutation == "quote":
        candidate.profile["claims"][0]["quote"] = "Unverified secret excerpt"
    elif mutation == "offset":
        candidate.profile["claims"][0]["start"] += 1
    elif mutation == "range":
        candidate.profile["claims"][0]["end"] = len(source.resume_text) + 1
    elif mutation == "label":
        candidate.profile["claims"][0]["label"] = "Unverified secret label"
    elif mutation == "kind":
        candidate.profile["claims"][0]["kind"] = "personality"
    elif mutation == "summary":
        candidate.summary = "Unverified secret summary"
    else:
        candidate.is_demo = False
    monkeypatch.setattr("app.api.candidates.catalog.get_candidate_for_job", lambda *args: candidate)
    response = api_request(candidates_app, "GET", "/jobs/demo_ds/candidates/demo_ds_avery")
    assert response.status_code == 500
    assert "Unverified secret" not in response.text + caplog.text
    assert source.resume_text not in response.text + caplog.text


def test_database_failures_keep_safe_error_and_cors(api_request, monkeypatch):
    app = create_app(Settings(cors_allowed_origins=("http://127.0.0.1:3000",)))
    app.state.database_engine = object()
    factory = MagicMock()
    factory.return_value.__enter__.return_value.execute.side_effect = OperationalError(
        "secret SQL", {}, Exception("private")
    )
    monkeypatch.setattr("app.api.jobs.Session", factory)
    response = api_request(
        app, "GET", "/jobs/demo_ds/candidates", headers={"Origin": "http://127.0.0.1:3000"}
    )
    assert response.status_code == 503
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert "private" not in response.text


def test_existing_query_filters_use_membership_not_id_prefixes():
    session = MagicMock()
    list_candidates_for_job(session, "demo_backend")
    statement = session.scalars.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "JOIN talent_insight.job_candidates" in sql
    assert statement.compile().params == {"job_id_1": "demo_backend"}
    get_candidate_for_job(session, "demo_backend", "demo_ds_avery")
    statement = session.scalar.call_args.args[0]
    assert statement.compile().params == {"job_id_1": "demo_backend", "id_1": "demo_ds_avery"}
    assert "JOIN talent_insight.job_candidates" in str(statement)


def test_source_with_unicode_and_no_claims_is_supported():
    from app.api.candidates import CandidateDetail

    text = "DEMO 🧪\nAvery\nEngineer\nSummary\nUses Python."
    start = text.index("Uses Python.")
    candidate = CandidateDetail(
        id="demo_unicode",
        display_name="Avery",
        headline="Engineer",
        summary="Summary",
        is_demo=True,
        resume_text=text,
        claims=[
            {
                "kind": "skill",
                "label": "Python",
                "quote": "Uses Python.",
                "start": start,
                "end": len(text),
            }
        ],
    )
    assert candidate.claims[0].start == start
    assert CandidateDetail(**{**candidate.model_dump(), "claims": []}).claims == []
