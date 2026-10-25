"""Offline scoring, interpretation boundaries and synthetic scenario coverage."""

import asyncio

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.extraction_contracts import (
    ExtractionFailure,
    ExtractionJob,
    ExtractionSource,
    StructuredResume,
    verify_facts,
)
from app.matching import (
    assess_resume,
    interpretation_schema,
    mock_interpretation,
    score_interpretation,
)
from app.resumes import ResumePage
from app.seed import load_seed


def sample(requirements=None, text="Python service experience.", fact_value="Python"):
    if requirements is None:
        requirements = [
            {
                "id": "m1",
                "category": "mandatory",
                "description": "Python services.",
                "minimum_years": None,
                "sort_order": 0,
            },
            {
                "id": "m2",
                "category": "mandatory",
                "description": "Production testing.",
                "minimum_years": None,
                "sort_order": 1,
            },
            {
                "id": "e1",
                "category": "experience",
                "description": "3 years experience.",
                "minimum_years": 3,
                "sort_order": 2,
            },
            {
                "id": "p1",
                "category": "preferred",
                "description": "AWS.",
                "minimum_years": None,
                "sort_order": 3,
            },
            {
                "id": "q1",
                "category": "qualification",
                "description": "Degree or study.",
                "minimum_years": None,
                "sort_order": 4,
            },
        ]
    job = ExtractionJob(
        id="demo_test", title="Backend Engineer", skills=["Python"], requirements=requirements
    )
    source = ExtractionSource(kind="uploaded_pdf", pages=[ResumePage(page_number=1, text=text)])
    facts = verify_facts(
        {
            "facts": [
                {
                    "kind": "skill",
                    "value": fact_value,
                    "evidence": [{"page_number": 1, "quote": text}],
                }
            ]
        },
        source,
    )
    return StructuredResume(
        job=job,
        source=source,
        mode="mock",
        model_id=None,
        facts=facts,
        unknown_categories=["experience", "qualification", "project"],
        notice="Synthetic test",
    )


def judgments(structured, statuses):
    return {
        "judgments": [
            {
                "requirement_id": row.id,
                "status": statuses[row.id],
                "fact_indices": [] if statuses[row.id] == "unknown" else [0],
                "reason": "Source needs review",
            }
            for row in structured.job.requirements
        ]
    }


def test_partial_credit_and_unknown_range_are_deterministic():
    structured = sample()
    value = judgments(
        structured, {"m1": "met", "m2": "partial", "e1": "not_met", "p1": "unknown", "q1": "met"}
    )
    first, score = score_interpretation(structured, value, Settings(ai_mode="mock"))
    assert score.score is None
    assert (score.lower, score.upper) == (47.5, 62.5)
    assert (score.mandatory_met, score.mandatory_total) == (1, 2)
    assert (score.resolved_count, score.unknown_count) == (4, 1)
    assert score.categories[0].effective_weight == 50
    assert score_interpretation(structured, value, Settings(ai_mode="mock")) == (first, score)
    value["judgments"][3].update(status="met", fact_indices=[0])
    assert score_interpretation(structured, value, Settings(ai_mode="mock"))[1].score == 62.5


def test_absent_categories_redistribute_and_no_criteria_is_unavailable():
    one = sample(
        requirements=[
            {
                "id": "m1",
                "category": "mandatory",
                "description": "Python services",
                "minimum_years": None,
                "sort_order": 0,
            }
        ]
    )
    score = score_interpretation(one, judgments(one, {"m1": "met"}), Settings())[1]
    assert (score.score, score.lower, score.upper) == (100, 100, 100)
    assert score.categories[0].effective_weight == 100
    empty = one.model_copy(update={"job": one.job.model_copy(update={"requirements": []})})
    score = score_interpretation(empty, {"judgments": []}, Settings())[1]
    assert score.score is score.lower is score.upper is None
    assert score.categories == []


def test_weights_are_configurable_and_reject_bad_totals():
    structured = sample()
    value = judgments(
        structured, {"m1": "met", "m2": "met", "e1": "not_met", "p1": "not_met", "q1": "not_met"}
    )
    default = score_interpretation(structured, value, Settings())[1]
    custom = score_interpretation(
        structured,
        value,
        Settings(
            match_weight_mandatory=40,
            match_weight_experience=30,
            match_weight_preferred=20,
            match_weight_qualification=10,
        ),
    )[1]
    assert default.score == 50 and custom.score == 40
    with pytest.raises(ValidationError):
        Settings(match_weight_mandatory=99)


def test_complete_zero_and_perfect_are_distinct_from_unavailable():
    structured = sample()
    for status, expected in [("not_met", 0), ("met", 100)]:
        value = judgments(structured, {row.id: status for row in structured.job.requirements})
        score = score_interpretation(structured, value, Settings())[1]
        assert (score.score, score.lower, score.upper) == (expected, expected, expected)
        assert score.unknown_count == 0


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "foreign",
        "bad_index",
        "unknown_ref",
        "uncited",
        "duplicate_ref",
        "extra",
        "fake_offset",
    ],
)
def test_invalid_interpretation_or_source_fails_closed(mutation):
    structured = sample()
    value = judgments(structured, {row.id: "unknown" for row in structured.job.requirements})
    row = value["judgments"][0]
    if mutation == "missing":
        value["judgments"].pop()
    elif mutation == "duplicate":
        value["judgments"][1]["requirement_id"] = row["requirement_id"]
    elif mutation == "foreign":
        row["requirement_id"] = "other_job"
    elif mutation == "bad_index":
        row.update(status="met", fact_indices=[1])
    elif mutation == "unknown_ref":
        row["fact_indices"] = [0]
    elif mutation == "uncited":
        row["status"] = "met"
    elif mutation == "duplicate_ref":
        row.update(status="met", fact_indices=[0, 0])
    elif mutation == "extra":
        row["score"] = 100
    else:
        structured.facts[0].evidence[0].start += 1
    with pytest.raises(ExtractionFailure, match="invalid_interpretation"):
        score_interpretation(structured, value, Settings())


def test_mock_never_converts_mentions_to_assured_matches():
    structured = sample()
    result = asyncio.run(assess_resume(structured, Settings(ai_mode="mock")))
    assert all(row.status == "unknown" for row in result.judgments)
    assert result.scoring.score is None
    assert (result.scoring.lower, result.scoring.upper) == (0, 100)
    assert "Mock" in result.notice


def test_bedrock_interpretation_retries_invalid_mapping_and_keeps_score_server_owned(monkeypatch):
    from app import extraction

    structured = sample().model_copy(update={"mode": "bedrock", "model_id": "synthetic-model"})
    settings = Settings(
        ai_mode="bedrock", aws_region="ap-southeast-2", bedrock_model_id="synthetic-model"
    )
    calls = []

    async def provider(job, source, supplied, repair, *, facts):
        calls.append((job, source, supplied, repair, facts))
        if not repair:
            return {
                "judgments": [
                    {
                        "requirement_id": "foreign",
                        "status": "met",
                        "fact_indices": [0],
                        "reason": "Unsupported",
                    }
                ],
                "score": 100,
            }
        return judgments(
            structured,
            {"m1": "met", "m2": "partial", "e1": "unknown", "p1": "unknown", "q1": "unknown"},
        )

    monkeypatch.setattr(extraction, "bedrock_provider", provider)
    result = asyncio.run(assess_resume(structured, settings))
    assert [call[3] for call in calls] == [False, True]
    assert calls[0][0] == structured.job and calls[0][4] == structured.facts
    assert result.scoring.score is None
    assert (result.scoring.lower, result.scoring.upper) == (37.5, 87.5)
    assert "AI interpretation" in result.notice


def test_assessment_rejects_mismatched_provider_identity():
    structured = sample().model_copy(update={"mode": "bedrock", "model_id": "other-model"})
    settings = Settings(
        ai_mode="bedrock", aws_region="ap-southeast-2", bedrock_model_id="synthetic-model"
    )
    with pytest.raises(ExtractionFailure, match="invalid_interpretation"):
        asyncio.run(assess_resume(structured, settings))


def test_all_synthetic_scenarios_preserve_unknowns_and_source_identity():
    data = load_seed()
    scenarios = set()
    for member in data.memberships:
        candidate = next(c for c in data.candidates if c.id == member.candidate_id)
        job = next(j for j in data.jobs if j.id == member.job_id)
        scenarios.add(member.demo_scenario)
        structured = StructuredResume(
            job=ExtractionJob(
                id=job.id,
                title=job.title,
                skills=job.skills,
                requirements=[
                    {**row.model_dump(), "sort_order": i} for i, row in enumerate(job.requirements)
                ],
            ),
            source=ExtractionSource(
                kind="synthetic_demo",
                candidate_id=candidate.id,
                pages=[ResumePage(page_number=1, text=candidate.resume_text)],
            ),
            mode="mock",
            model_id=None,
            facts=[],
            unknown_categories=["skill", "experience", "qualification", "project"],
            notice="Synthetic test",
        )
        interpretation = mock_interpretation(structured)
        score = score_interpretation(structured, interpretation, Settings())[1]
        assert len(interpretation.judgments) == len(job.requirements)
        assert score.score is None and (score.lower, score.upper) == (0, 100)
        assert score.mandatory_met == 0 and score.unknown_count == len(job.requirements)
    assert scenarios == {"strong", "partial", "weak", "transferable", "ambiguous", "incomplete"}


def test_curated_synthetic_experience_scenarios_show_partial_and_unknown():
    data = load_seed()
    cases = [
        ("demo_ds_avery", "4 years of applied product analysis", "met", 100),
        ("demo_ds_mina", "5 years of operations analysis", "partial", 50),
        ("demo_ds_jordan", "Project dates and education are not included", "unknown", None),
    ]
    requirement = next(
        row
        for job in data.jobs
        if job.id == "demo_ds"
        for row in job.requirements
        if row.id == "demo_ds_experience"
    )
    for candidate_id, phrase, status, expected in cases:
        candidate = next(row for row in data.candidates if row.id == candidate_id)
        source = ExtractionSource(
            kind="synthetic_demo",
            candidate_id=candidate_id,
            pages=[ResumePage(page_number=1, text=candidate.resume_text)],
        )
        facts = verify_facts(
            {
                "facts": [
                    {
                        "kind": "experience",
                        "value": phrase,
                        "evidence": [{"page_number": 1, "quote": phrase}],
                    }
                ]
            },
            source,
        )
        structured = StructuredResume(
            job=ExtractionJob(
                id="demo_ds",
                title="Data Scientist",
                skills=[],
                requirements=[{**requirement.model_dump(), "sort_order": 0}],
            ),
            source=source,
            mode="mock",
            model_id=None,
            facts=facts,
            unknown_categories=["skill", "qualification", "project"],
            notice="Synthetic test",
        )
        value = {
            "judgments": [
                {
                    "requirement_id": requirement.id,
                    "status": status,
                    "fact_indices": [] if status == "unknown" else [0],
                    "reason": "Curated test interpretation",
                }
            ]
        }
        score = score_interpretation(structured, value, Settings())[1]
        assert score.score == expected
        assert (score.lower, score.upper) == (
            (0, 100) if expected is None else (expected, expected)
        )


def test_provider_schema_keeps_fields_and_strips_unsupported_limits():
    schema = interpretation_schema()
    assert "judgments" in schema["properties"]
    assert "maxItems" not in str(schema) and "maxLength" not in str(schema)
