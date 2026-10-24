"""Synthetic profile evidence must remain traceable before any database write."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.seed import CatalogSeed, load_seed


def test_curated_fixture_covers_domains_and_varied_evidence() -> None:
    data = load_seed()
    assert len(data.jobs) == 4
    assert len(data.candidates) == 12
    assert {row.demo_scenario for row in data.memberships} == {
        "strong",
        "partial",
        "weak",
        "transferable",
        "ambiguous",
        "incomplete",
    }
    for job in data.jobs:
        assert {r.category for r in job.requirements} == {
            "mandatory",
            "experience",
            "preferred",
            "qualification",
        }
        assert len([row for row in data.memberships if row.job_id == job.id]) == 3
    for candidate in data.candidates:
        for claim in candidate.profile()["claims"]:
            assert candidate.resume_text[claim["start"] : claim["end"]] == claim["quote"]


@pytest.mark.parametrize("mutation", ["quote", "duplicate", "question", "membership", "real"])
def test_rejects_unsupported_or_inconsistent_seed_records(mutation: str) -> None:
    data = deepcopy(load_seed().model_dump())
    if mutation == "quote":
        data["candidates"][0]["claims"][0]["quote"] = "Invented Kubernetes qualification"
    elif mutation == "duplicate":
        data["candidates"][1]["id"] = data["candidates"][0]["id"]
    elif mutation == "question":
        data["jobs"][0]["questions"][0]["requirement_ids"] = ["demo_missing"]
    elif mutation == "membership":
        data["memberships"][0]["candidate_id"] = "demo_missing"
    else:
        data["candidates"][0]["is_demo"] = False
    with pytest.raises(ValidationError):
        CatalogSeed.model_validate(data)
