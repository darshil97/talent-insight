"""The manual demo refresh is offline in tests and never writes Neon."""

import asyncio

import pytest

from app.config import Settings
from app.demo_cache import CacheEntry, assessment_digest, load_cache, valid_assessment
from app.extraction import structure_resume as real_structure_resume
from app.extraction_contracts import ExtractionFailure
from app.matching import assess_resume as real_assess_resume
from app.refresh_demo import (
    RefreshFailure,
    build_cache,
    load_extraction_progress,
    valid_extraction,
    write_cache,
)
from app.seed import load_seed


def test_refresh_covers_every_membership_and_replaces_one_complete_file(tmp_path):
    data = load_seed()
    settings = Settings(ai_mode="mock")
    document = asyncio.run(build_cache(data, settings))
    assert len(document.entries) == len(data.memberships) == 13
    assert {(row.job_id, row.candidate_id) for row in document.entries} == {
        (row.job_id, row.candidate_id) for row in data.memberships
    }
    assert all(
        row.assessment.structured.source.kind == "synthetic_demo" for row in document.entries
    )
    path = tmp_path / "assessments.json"
    write_cache(document, path)
    loaded = load_cache(path)
    assert len(loaded) == 13
    path.write_text("broken", encoding="utf-8")
    assert load_cache(path) == {}


def test_snapshot_is_bound_to_job_source_weights_and_provider():
    settings = Settings(ai_mode="mock")
    row = asyncio.run(build_cache(load_seed(), settings)).entries[0]
    structured = row.assessment.structured.model_copy(
        update={"mode": "bedrock", "model_id": "test-model"}
    )
    assessment = row.assessment.model_copy(update={"structured": structured})
    entry = CacheEntry(
        job_id=row.job_id,
        candidate_id=row.candidate_id,
        fingerprint=row.fingerprint,
        assessment_digest=assessment_digest(assessment),
        assessment=assessment,
    )
    entries = {(row.job_id, row.candidate_id): entry}
    job, source = structured.job, structured.source
    assert valid_assessment(entries, job, source, settings) == assessment
    assert (
        valid_assessment(entries, job.model_copy(update={"title": "Changed"}), source, settings)
        is None
    )
    assert (
        valid_assessment(
            entries, job, source.model_copy(update={"candidate_id": "demo_other"}), settings
        )
        is None
    )
    different_weights = Settings(
        ai_mode="mock",
        match_weight_mandatory=40,
        match_weight_experience=30,
        match_weight_preferred=20,
        match_weight_qualification=10,
    )
    assert valid_assessment(entries, job, source, different_weights) is None
    assert valid_assessment({(row.job_id, row.candidate_id): row}, job, source, settings) is None
    changed_score = assessment.model_copy(
        update={"scoring": assessment.scoring.model_copy(update={"score": 100})}
    )
    edited = entry.model_copy(update={"assessment": changed_score})
    assert valid_assessment({(row.job_id, row.candidate_id): edited}, job, source, settings) is None


@pytest.mark.parametrize("stage", ["extraction", "interpretation"])
def test_refresh_failure_identifies_member_and_stage_without_writing_snapshot(monkeypatch, stage):
    async def fail(*_args, **_kwargs):
        raise ExtractionFailure("invalid_model_output")

    if stage == "extraction":
        monkeypatch.setattr("app.refresh_demo.structure_resume", fail)
    else:
        monkeypatch.setattr("app.refresh_demo.assess_resume", fail)
    with pytest.raises(RefreshFailure) as caught:
        asyncio.run(build_cache(load_seed(), Settings(ai_mode="mock")))
    assert (caught.value.job_id, caught.value.candidate_id) == (
        "demo_backend",
        "demo_backend_mara",
    )
    assert (caught.value.stage, caught.value.code) == (stage, "invalid_model_output")


def test_refresh_reuses_only_completed_valid_progress_after_failure(monkeypatch, tmp_path):
    settings = Settings(ai_mode="bedrock", bedrock_model_id="synthetic-test")
    progress = tmp_path / ".assessments-progress.json"
    extraction_progress = tmp_path / ".extractions-progress.json"
    snapshot = tmp_path / "assessments.json"
    snapshot.write_text("previous snapshot", encoding="utf-8")
    calls = []
    assess_calls = []
    fail_fourth = True

    async def fake_structure(job, source, _settings):
        calls.append((job.id, source.candidate_id))
        result = await real_structure_resume(job, source, Settings(ai_mode="mock"))
        return result.model_copy(update={"mode": "bedrock", "model_id": "synthetic-test"})

    async def fake_assess(structured, _settings):
        assess_calls.append(structured.source.candidate_id)
        if fail_fourth and len(assess_calls) == 4:
            raise ExtractionFailure("invalid_model_output")
        mock_structured = structured.model_copy(update={"mode": "mock", "model_id": None})
        result = await real_assess_resume(mock_structured, Settings(ai_mode="mock"))
        return result.model_copy(update={"structured": structured})

    monkeypatch.setattr("app.refresh_demo.structure_resume", fake_structure)
    monkeypatch.setattr("app.refresh_demo.assess_resume", fake_assess)
    data = load_seed()

    with pytest.raises(RefreshFailure):
        asyncio.run(
            build_cache(
                data,
                settings,
                progress_path=progress,
                extraction_progress_path=extraction_progress,
            )
        )
    assert snapshot.read_text(encoding="utf-8") == "previous snapshot"
    assert len(load_cache(progress)) == 3
    extracted = load_extraction_progress(extraction_progress)
    assert len(extracted) == 4
    last = next(reversed(extracted.values()))
    job = last.structured.job
    source = last.structured.source
    assert valid_extraction(extracted, job, source, settings) == last.structured
    corrupted = last.model_copy(update={"digest": "wrong"})
    assert (
        valid_extraction({(job.id, source.candidate_id): corrupted}, job, source, settings) is None
    )
    changed = source.model_copy(
        update={"pages": [source.pages[0].model_copy(update={"text": "changed"})]}
    )
    assert valid_extraction(extracted, job, changed, settings) is None

    fail_fourth = False
    document = asyncio.run(
        build_cache(
            data,
            settings,
            progress_path=progress,
            extraction_progress_path=extraction_progress,
        )
    )
    assert len(document.entries) == 13
    assert len(calls) == 13  # Interpretation retries reuse the fourth extraction.
    assert len(assess_calls) == 14
    write_cache(document, snapshot)
    progress.unlink()
    extraction_progress.unlink()
    assert len(load_cache(snapshot)) == 13
    assert not progress.exists()
    assert not extraction_progress.exists()
