"""Synthetic profile evidence must remain traceable before any database write."""

import asyncio
import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.refresh_demo import build_cache
from app.seed import CatalogSeed, load_seed


def test_curated_fixture_covers_domains_and_varied_evidence() -> None:
    fixture = json.loads(
        (Path(__file__).resolve().parents[1] / "app" / "fixtures" / "candidates.json").read_text()
    )
    assert set(fixture) == {"candidates"}
    assert all(len(row["memberships"]) >= 1 for row in fixture["candidates"])
    data = load_seed()
    assert len(data.jobs) == 4
    assert len(data.candidates) == 12
    assert len(data.memberships) == 13
    assert {job.id for job in data.jobs} == {
        "demo_ds",
        "demo_backend",
        "demo_hr_ops",
        "demo_marketing_ops",
    }
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
        assert len([row for row in data.memberships if row.job_id == job.id]) == (
            4 if job.id == "demo_ds" else 3
        )
    assert any(
        row.job_id == "demo_ds"
        and row.candidate_id == "demo_backend_theo"
        and row.demo_scenario == "weak"
        for row in data.memberships
    )
    for candidate in data.candidates:
        for claim in candidate.profile()["claims"]:
            assert candidate.resume_text[claim["start"] : claim["end"]] == claim["quote"]


def test_candidate_owned_links_support_more_than_one_job(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "app" / "fixtures"
    root = tmp_path / "fixtures"
    shutil.copytree(source, root)
    path = root / "candidates.json"
    fixture = json.loads(path.read_text())
    fixture["candidates"][0]["memberships"].append(
        {"job_id": "demo_hr_ops", "demo_scenario": "transferable"}
    )
    path.write_text(json.dumps(fixture))
    data = load_seed(root)
    assert len(data.memberships) == 14
    assert {
        (row.job_id, row.demo_scenario)
        for row in data.memberships
        if row.candidate_id == "demo_ds_avery"
    } == {("demo_ds", "strong"), ("demo_hr_ops", "transferable")}
    snapshots = asyncio.run(build_cache(data, Settings(ai_mode="mock")))
    assert len(snapshots.entries) == 14
    assert {(row.job_id, row.candidate_id) for row in snapshots.entries} == {
        (row.job_id, row.candidate_id) for row in data.memberships
    }
    fixture["candidates"][0]["memberships"].append(
        {"job_id": "demo_hr_ops", "demo_scenario": "strong"}
    )
    path.write_text(json.dumps(fixture))
    with pytest.raises(ValidationError, match="Duplicate job-candidate membership"):
        load_seed(root)


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


def test_populated_job_requires_three_to_five_memberships() -> None:
    data = load_seed().model_dump()
    data["memberships"] = [
        row
        for row in data["memberships"]
        if row["job_id"] != "demo_backend" or row["candidate_id"] == "demo_backend_priya"
    ]
    data["candidates"] = [row for row in data["candidates"] if row["id"] != "demo_backend_mara"]
    with pytest.raises(ValidationError, match="three to five"):
        CatalogSeed.model_validate(data)


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
