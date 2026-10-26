"""Manually refresh all synthetic assessments without changing Neon."""

import argparse
import asyncio
import hashlib
import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from app.config import Settings, load_settings
from app.demo_cache import (
    CACHE_PATH,
    CacheDocument,
    CacheEntry,
    assessment_digest,
    fingerprint,
    load_cache,
    valid_assessment,
)
from app.extraction import structure_resume
from app.extraction_contracts import (
    ExtractionFailure,
    ExtractionJob,
    ExtractionSource,
    StructuredResume,
    verify_facts,
)
from app.matching import assess_resume
from app.resumes import ResumePage
from app.seed import CatalogSeed, load_seed


class RefreshFailure(Exception):
    def __init__(self, job_id: str, candidate_id: str, stage: str, code: str):
        self.job_id = job_id
        self.candidate_id = candidate_id
        self.stage = stage
        self.code = code
        super().__init__(code)


PROGRESS_PATH = CACHE_PATH.with_name(".assessments-progress.json")
EXTRACTION_PROGRESS_PATH = CACHE_PATH.with_name(".extractions-progress.json")


class ExtractionCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    job_id: str
    candidate_id: str
    fingerprint: str
    digest: str
    structured: StructuredResume


class ExtractionProgress(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: int
    entries: list[ExtractionCheckpoint]


def load_extraction_progress(path: Path) -> dict[tuple[str, str], ExtractionCheckpoint]:
    try:
        document = ExtractionProgress.model_validate_json(path.read_text(encoding="utf-8"))
        rows = {(row.job_id, row.candidate_id): row for row in document.entries}
        return rows if document.version == 1 and len(rows) == len(document.entries) else {}
    except (OSError, ValueError, ValidationError):
        return {}


def valid_extraction(
    entries: dict[tuple[str, str], ExtractionCheckpoint],
    job: ExtractionJob,
    source: ExtractionSource,
    settings: Settings,
) -> StructuredResume | None:
    entry = entries.get((job.id, source.candidate_id or ""))
    if entry is None:
        return None
    structured = entry.structured
    if (
        entry.fingerprint != fingerprint(job, source, settings)
        or entry.digest != hashlib.sha256(structured.model_dump_json().encode()).hexdigest()
        or structured.job != job
        or structured.source != source
        or structured.mode != "bedrock"
        or structured.model_id != settings.bedrock_model_id
    ):
        return None
    try:
        verified = verify_facts(
            {
                "facts": [
                    {
                        "kind": fact.kind,
                        "value": fact.value,
                        "evidence": [
                            {"page_number": item.page_number, "quote": item.quote}
                            for item in fact.evidence
                        ],
                    }
                    for fact in structured.facts
                ]
            },
            source,
        )
    except ExtractionFailure:
        return None
    return structured if verified == structured.facts else None


async def build_cache(
    data: CatalogSeed,
    settings: Settings,
    *,
    progress_path: Path | None = None,
    extraction_progress_path: Path | None = None,
) -> CacheDocument:
    jobs = {row.id: row for row in data.jobs}
    candidates = {row.id: row for row in data.candidates}
    recovered = load_cache(progress_path) if progress_path is not None else {}
    extracted = (
        load_extraction_progress(extraction_progress_path)
        if extraction_progress_path is not None
        else {}
    )
    entries = []
    for member in sorted(data.memberships, key=lambda row: (row.job_id, row.candidate_id)):
        job_row = jobs[member.job_id]
        candidate = candidates[member.candidate_id]
        job = ExtractionJob(
            id=job_row.id,
            title=job_row.title,
            skills=job_row.skills,
            requirements=[
                {**row.model_dump(), "sort_order": index}
                for index, row in enumerate(job_row.requirements)
            ],
        )
        source = ExtractionSource(
            kind="synthetic_demo",
            candidate_id=candidate.id,
            pages=[ResumePage(page_number=1, text=candidate.resume_text)],
        )
        assessment = valid_assessment(recovered, job, source, settings)
        fresh = assessment is None
        if fresh:
            structured = valid_extraction(extracted, job, source, settings)
            if structured is None:
                try:
                    structured = await structure_resume(job, source, settings)
                except ExtractionFailure as exc:
                    raise RefreshFailure(job.id, candidate.id, "extraction", exc.code) from None
                if extraction_progress_path is not None:
                    extracted[(job.id, candidate.id)] = ExtractionCheckpoint(
                        job_id=job.id,
                        candidate_id=candidate.id,
                        fingerprint=fingerprint(job, source, settings),
                        digest=hashlib.sha256(structured.model_dump_json().encode()).hexdigest(),
                        structured=structured,
                    )
                    write_extraction_progress(
                        ExtractionProgress(version=1, entries=list(extracted.values())),
                        extraction_progress_path,
                    )
            try:
                assessment = await assess_resume(structured, settings)
            except ExtractionFailure as exc:
                raise RefreshFailure(job.id, candidate.id, "interpretation", exc.code) from None
        entries.append(
            CacheEntry(
                job_id=job.id,
                candidate_id=candidate.id,
                fingerprint=fingerprint(job, source, settings),
                assessment_digest=assessment_digest(assessment),
                assessment=assessment,
            )
        )
        if progress_path is not None and fresh:
            write_cache(CacheDocument(version=1, entries=entries), progress_path)
    return CacheDocument(version=1, entries=entries)


def _write_document(document: BaseModel, path: Path) -> None:
    """Atomically replace one validated synthetic-data document."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as file:
            temporary = Path(file.name)
            file.write(document.model_dump_json(indent=2))
            file.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_cache(document: CacheDocument, path: Path = CACHE_PATH) -> None:
    """Replace the published cache only after every membership succeeds."""
    _write_document(document, path)


def write_extraction_progress(document: ExtractionProgress, path: Path) -> None:
    _write_document(document, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Call the configured Bedrock provider")
    args = parser.parse_args()
    data = load_seed()
    counts = {job.id: sum(row.job_id == job.id for row in data.memberships) for job in data.jobs}
    if any(count < 3 or count > 5 for count in counts.values()):
        raise SystemExit("Each demo job must have 3–5 candidate memberships.")
    if not args.run:
        print(
            json.dumps(
                {
                    "validated": True,
                    "memberships": len(data.memberships),
                    "per_job": counts,
                    "provider_calls": 0,
                    "snapshot_updated": False,
                }
            )
        )
        return
    settings = load_settings()
    if settings.ai_mode != "bedrock":
        raise SystemExit("Set AI_MODE=bedrock to produce meaningful demo snapshots.")
    try:
        document = asyncio.run(
            build_cache(
                data,
                settings,
                progress_path=PROGRESS_PATH,
                extraction_progress_path=EXTRACTION_PROGRESS_PATH,
            )
        )
    except RefreshFailure as exc:
        raise SystemExit(
            f"Refresh stopped at {exc.job_id}/{exc.candidate_id} during {exc.stage}: "
            f"{exc.code}. The previous snapshot was not changed; completed valid entries "
            "will be reused on retry."
        ) from None
    write_cache(document)
    PROGRESS_PATH.unlink(missing_ok=True)
    EXTRACTION_PROGRESS_PATH.unlink(missing_ok=True)
    print(
        json.dumps(
            {"refreshed": len(document.entries), "per_job": counts, "snapshot_updated": True}
        )
    )


if __name__ == "__main__":
    main()
