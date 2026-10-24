"""Synthetic profile evidence must remain traceable before any database write."""

import json
import shutil
from copy import deepcopy
from pathlib import Path

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


def test_job_files_can_be_edited_or_added_without_python_changes(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "app" / "fixtures"
    shutil.copytree(source, tmp_path / "fixtures")
    root = tmp_path / "fixtures"
    job_file = root / "jobs" / "demo_ds.json"
    job = json.loads(job_file.read_text())
    job["title"] = "Edited Data Scientist"
    job_file.write_text(json.dumps(job))
    assert next(job for job in load_seed(root).jobs if job.id == "demo_ds").title == job["title"]
    job["id"] = "demo_new"
    for row in job["requirements"]:
        row["id"] = row["id"].replace("demo_ds", "demo_new")
    for row in job["questions"]:
        row["id"] = row["id"].replace("demo_ds", "demo_new")
        row["requirement_ids"] = [
            value.replace("demo_ds", "demo_new") for value in row["requirement_ids"]
        ]
    (root / "jobs" / "demo_new.json").write_text(json.dumps(job))
    assert len(load_seed(root).jobs) == 5  # Jobs need no candidates until module 7.


@pytest.mark.parametrize("mutation", ["filename", "duplicate", "missing", "malformed"])
def test_split_job_files_fail_validation_before_database_access(
    tmp_path: Path, mutation: str
) -> None:
    source = Path(__file__).resolve().parents[1] / "app" / "fixtures"
    root = tmp_path / "fixtures"
    shutil.copytree(source, root)
    job_file = root / "jobs" / "demo_ds.json"
    if mutation == "filename":
        job_file.rename(root / "jobs" / "wrong.json")
    elif mutation == "missing":
        for path in (root / "jobs").iterdir():
            path.unlink()
    elif mutation == "malformed":
        job_file.write_text("{")
    else:
        job = json.loads(job_file.read_text())
        job["requirements"][1]["id"] = job["requirements"][0]["id"]
        job_file.write_text(json.dumps(job))
    with pytest.raises(ValueError):
        load_seed(root)
