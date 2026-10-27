"""Validated, versioned assessment snapshots for synthetic job memberships."""

import hashlib
import json
from functools import cache
from importlib.resources import files
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from app.config import Settings
from app.pipeline.contracts import Assessment, ExtractionJob, ExtractionSource

CACHE_PATH = Path(__file__).with_name("fixtures") / "assessments.json"
# Any change to pipeline code, provider adapters or prompt text invalidates every snapshot.
LOGIC_DIRECTORIES = ("pipeline", "llm", "prompts")
LOGIC_FILES = ("refresh_demo.py",)


@cache
def _code_hashes() -> tuple[tuple[str, str], ...]:
    """Hash packaged logic once per process; every candidate read reuses the result."""
    app_files = files("app")
    found = {name: app_files.joinpath(name).read_bytes() for name in LOGIC_FILES}
    pending = [(directory, app_files.joinpath(directory)) for directory in LOGIC_DIRECTORIES]
    while pending:
        prefix, folder = pending.pop()
        for item in folder.iterdir():
            name = f"{prefix}/{item.name}"
            if item.is_dir():
                if item.name != "__pycache__":
                    pending.append((name, item))
            elif item.name.endswith((".py", ".md")):
                found[name] = item.read_bytes()
    return tuple(
        sorted((name, hashlib.sha256(content).hexdigest()) for name, content in found.items())
    )


class CacheEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    job_id: str
    candidate_id: str
    fingerprint: str
    assessment_digest: str
    assessment: Assessment


class CacheDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: int
    entries: list[CacheEntry]


def fingerprint(job: ExtractionJob, source: ExtractionSource, settings: Settings) -> str:
    """Invalidate snapshots when source, criteria, weights, credits or pipeline code changes."""
    code_hashes = dict(_code_hashes())
    payload = {
        "job": job.model_dump(mode="json"),
        "source": source.model_dump(mode="json"),
        "weights": [
            settings.match_weight_mandatory,
            settings.match_weight_experience,
            settings.match_weight_preferred,
            settings.match_weight_qualification,
        ],
        "credits": [settings.match_credit_transferable, settings.match_credit_partial],
        "code": code_hashes,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def assessment_digest(assessment: Assessment) -> str:
    return hashlib.sha256(assessment.model_dump_json().encode()).hexdigest()


def load_cache(path: Path = CACHE_PATH) -> dict[tuple[str, str], CacheEntry]:
    try:
        document = CacheDocument.model_validate_json(path.read_text(encoding="utf-8"))
        if document.version != 1:
            return {}
        rows = {(row.job_id, row.candidate_id): row for row in document.entries}
        return rows if len(rows) == len(document.entries) else {}
    except (OSError, ValueError, ValidationError):
        return {}


def valid_assessment(
    entries: dict[tuple[str, str], CacheEntry],
    job: ExtractionJob,
    source: ExtractionSource,
    settings: Settings,
) -> Assessment | None:
    entry = entries.get((job.id, source.candidate_id or ""))
    if (
        entry is None
        or entry.fingerprint != fingerprint(job, source, settings)
        or entry.assessment_digest != assessment_digest(entry.assessment)
    ):
        return None
    assessment = entry.assessment
    if (
        assessment.structured.job != job
        or assessment.structured.source != source
        or assessment.structured.mode != "bedrock"
        or assessment.structured.model_id is None
    ):
        return None
    return assessment
