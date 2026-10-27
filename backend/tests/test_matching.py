"""Offline scoring, interpretation boundaries and synthetic scenario coverage."""

import asyncio
import json

import pytest
from pydantic import ValidationError
from test_extraction import bedrock_settings, scripted

from app.config import Settings
from app.pipeline import interpretation
from app.pipeline.assessment import assess_resume
from app.pipeline.contracts import (
    ExtractionFailure,
    ExtractionJob,
    ExtractionSource,
    Interpretation,
    StructuredResume,
    provider_json_schema,
)
from app.pipeline.evidence import verify_facts
from app.pipeline.interpretation import UNVERIFIED_REASON, mock_interpretation, salvage_judgments
from app.pipeline.scoring import score_interpretation
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


def test_bedrock_interpretation_retries_unusable_mapping_and_keeps_score_server_owned(
    monkeypatch,
):
    structured = sample().model_copy(update={"mode": "bedrock", "model_id": "synthetic-model"})
    settings = bedrock_settings(bedrock_model_id="synthetic-model")
    calls = scripted(
        monkeypatch,
        interpretation,
        {
            "judgments": [
                {
                    "requirement_id": "foreign",
                    "status": "met",
                    "fact_indices": [0],
                    "reason": "Unsupported private reason",
                }
            ],
            "score": 100,
        },
        judgments(
            structured,
            {"m1": "met", "m2": "partial", "e1": "unknown", "p1": "unknown", "q1": "unknown"},
        ),
    )
    result = asyncio.run(assess_resume(structured, settings))
    assert [call["attempt"] for call in calls] == [1, 2]
    payload = json.loads(calls[0]["payload"])
    assert payload["job_context"] == structured.job.model_dump()
    assert payload["verified_text_mentions"] == [fact.model_dump() for fact in structured.facts]
    retry = calls[1]["system"]
    assert "requirement m1: has no judgment" in retry
    assert "judgments[0]: uses a requirement_id that is not in the job" in retry
    assert "Unsupported private reason" not in retry
    assert result.scoring.score is None
    assert (result.scoring.lower, result.scoring.upper) == (37.5, 87.5)
    assert "AI interpretation" in result.notice


@pytest.mark.parametrize(
    "mutation,status,indices",
    [
        ("missing", "unknown", []),
        ("conflicting", "unknown", []),
        ("identical_duplicate", "met", [0]),
        ("bad_index", "unknown", []),
        ("partly_bad_index", "met", [0]),
        ("unknown_ref", "unknown", []),
        ("uncited", "unknown", []),
        ("duplicate_ref", "met", [0]),
        ("extra", "met", [0]),
        ("long_reason", "met", [0]),
        ("invalid_status", "unknown", []),
    ],
)
def test_judgment_salvage_only_widens_uncertainty(mutation, status, indices):
    structured = sample()
    value = judgments(structured, {row.id: "met" for row in structured.job.requirements})
    row = value["judgments"][0]
    if mutation == "missing":
        value["judgments"].pop(0)
    elif mutation == "conflicting":
        value["judgments"].append({**row, "status": "not_met"})
    elif mutation == "identical_duplicate":
        value["judgments"].append(dict(row))
    elif mutation == "bad_index":
        row["fact_indices"] = [7]
    elif mutation == "partly_bad_index":
        row["fact_indices"] = [0, 7, True]
    elif mutation == "unknown_ref":
        row["status"] = "unknown"
    elif mutation == "uncited":
        row["fact_indices"] = []
    elif mutation == "duplicate_ref":
        row["fact_indices"] = [0, 0]
    elif mutation == "extra":
        row["score"] = 100
    elif mutation == "long_reason":
        row["reason"] = "x" * 500
    else:
        row["status"] = "excellent"
    result = salvage_judgments(value, structured)
    first = result.interpretation.judgments[0]
    assert [row.requirement_id for row in result.interpretation.judgments] == [
        row.id for row in structured.job.requirements
    ]
    assert (first.requirement_id, first.status, first.fact_indices) == ("m1", status, indices)
    assert len(first.reason) <= 300
    if status == "unknown" and mutation != "unknown_ref":
        assert first.reason == UNVERIFIED_REASON
    # Salvaged output always passes strict scoring validation.
    score_interpretation(structured, result.interpretation, Settings())


def test_unusable_interpretation_shape_fails_without_a_score():
    with pytest.raises(ExtractionFailure, match="invalid_model_output"):
        salvage_judgments({"score": 100}, sample())


def test_assessment_rejects_mismatched_provider_identity():
    structured = sample().model_copy(update={"mode": "bedrock", "model_id": "other-model"})
    settings = bedrock_settings(bedrock_model_id="synthetic-model")
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
        ("demo_ds_avery", "6 years of applied product data science", "met", 100),
        ("demo_ds_mina", "5 years of operations analysis", "partial", 50),
        ("demo_ds_jordan", "the specific query ownership is not stated", "unknown", None),
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
    schema = provider_json_schema(Interpretation)
    assert "judgments" in schema["properties"]
    assert "maxItems" not in str(schema) and "maxLength" not in str(schema)


def test_transferable_sits_between_met_and_partial_and_credits_are_configurable():
    structured = sample()
    statuses = {"m1": "met", "m2": "transferable", "e1": "partial", "p1": "met", "q1": "met"}
    value = judgments(structured, statuses)
    score = score_interpretation(structured, value, Settings())[1]
    # Mandatory (1 + 0.75) / 2 * 50 + experience 0.5 * 25 + 15 + 10.
    assert score.score == 81.3
    assert score.mandatory_met == 1
    custom = Settings(match_credit_transferable=0.9, match_credit_partial=0.4)
    assert score_interpretation(structured, value, custom)[1].score == 82.5
    for status, expected in [("met", 100), ("transferable", 75), ("partial", 50)]:
        uniform = judgments(structured, {row.id: status for row in structured.job.requirements})
        assert score_interpretation(structured, uniform, Settings())[1].score == expected


def test_salvage_keeps_transferable_judgments_with_citations():
    structured = sample()
    value = judgments(structured, {row.id: "transferable" for row in structured.job.requirements})
    result = salvage_judgments(value, structured)
    assert {row.status for row in result.interpretation.judgments} == {"transferable"}
    assert result.issues == []
    uncited = judgments(structured, {row.id: "unknown" for row in structured.job.requirements})
    uncited["judgments"][0].update(status="transferable")
    assert salvage_judgments(uncited, structured).interpretation.judgments[0].status == "unknown"


@pytest.mark.parametrize(
    "unknown,estimate,confidence",
    [
        (set(), 100.0, "very_high"),
        ({"p1"}, 92.5, "high"),
        ({"e1"}, 87.5, "medium"),
        ({"m1", "e1"}, 75.0, "low"),
        ({"m1", "m2", "e1", "p1", "q1"}, 50.0, "low"),
    ],
)
def test_estimate_is_the_range_midpoint_and_confidence_follows_unknown_weight(
    unknown, estimate, confidence
):
    structured = sample()
    statuses = {
        row.id: ("unknown" if row.id in unknown else "met") for row in structured.job.requirements
    }
    score = score_interpretation(structured, judgments(structured, statuses), Settings())[1]
    assert score.estimate == estimate and score.confidence == confidence
    assert score.estimate == round((score.lower + score.upper) / 2, 1)
    assert (score.score is None) == bool(unknown)


def new_evidence_row(structured, quote, value="Python", status="met"):
    return {
        "requirement_id": "m1",
        "status": status,
        "fact_indices": [],
        "new_evidence": [
            {"kind": "experience", "value": value, "evidence": [{"page_number": 1, "quote": quote}]}
        ],
        "reason": "Quoted directly from the resume.",
    }


def test_judging_can_add_verified_resume_quotes_as_new_cited_facts():
    structured = sample(text="Python service experience.\nRan pytest suites for every release.")
    value = judgments(structured, {row.id: "unknown" for row in structured.job.requirements})
    value["judgments"][1] = {
        **new_evidence_row(structured, "Ran pytest suites for every release.", value="pytest"),
        "requirement_id": "m2",
    }
    result = salvage_judgments(value, structured)
    assert result.added == 1 and result.facts[-1].value == "pytest"
    m2 = result.interpretation.judgments[1]
    assert (m2.status, m2.fact_indices) == ("met", [len(structured.facts)])
    evidence = result.facts[-1].evidence[0]
    assert structured.source.pages[0].text[evidence.start : evidence.end] == evidence.quote


def test_unverifiable_or_duplicate_new_evidence_never_creates_a_match():
    structured = sample(text="Python service experience.")
    value = judgments(structured, {row.id: "unknown" for row in structured.job.requirements})
    value["judgments"][0] = new_evidence_row(structured, "Ten years of Rust in production.")
    result = salvage_judgments(value, structured)
    assert result.added == 0 and result.interpretation.judgments[0].status == "unknown"
    assert any("new_evidence[0]" in issue for issue in result.issues)
    duplicate = judgments(structured, {row.id: "unknown" for row in structured.job.requirements})
    duplicate["judgments"][0] = new_evidence_row(
        structured, "Python service experience.", value="Python"
    )
    duplicate["judgments"][0]["new_evidence"][0]["kind"] = "skill"
    reused = salvage_judgments(duplicate, structured)
    assert reused.added == 0 and reused.interpretation.judgments[0].fact_indices == [0]


def test_assessment_publishes_added_quotes_with_the_structured_facts(monkeypatch):
    structured = sample(text="Python service experience.\nRan pytest suites for every release.")
    structured = structured.model_copy(update={"mode": "bedrock", "model_id": "synthetic-model"})
    value = judgments(structured, {row.id: "unknown" for row in structured.job.requirements})
    value["judgments"][1] = {
        **new_evidence_row(structured, "Ran pytest suites for every release.", value="pytest"),
        "requirement_id": "m2",
    }
    scripted(monkeypatch, interpretation, value)
    result = asyncio.run(
        assess_resume(structured, bedrock_settings(bedrock_model_id="synthetic-model"))
    )
    assert [fact.value for fact in result.structured.facts] == ["Python", "pytest"]
    assert "experience" not in result.structured.unknown_categories
    assert result.judgments[1].fact_indices == [1]
    assert result.scoring.confidence == "low" and result.scoring.estimate is not None


@pytest.mark.parametrize(
    "quote,status",
    [
        ("Payroll coordination is not documented.", "unknown"),
        ("CRM lead routing is not described.", "unknown"),
        ("Holds a BCom; no quantitative degree.", "not_met"),
    ],
)
def test_not_met_cannot_rest_only_on_missing_information(quote, status):
    structured = sample(text=f"Python service experience.\n{quote}")
    value = judgments(structured, {row.id: "unknown" for row in structured.job.requirements})
    value["judgments"][0] = new_evidence_row(
        structured, quote, value=quote.split()[0], status="not_met"
    )
    result = salvage_judgments(value, structured)
    assert result.interpretation.judgments[0].status == status
    if status == "unknown":
        assert "judgments[0]: missing_information_not_contrary" in result.issues
