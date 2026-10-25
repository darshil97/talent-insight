"""Canonical catalog context, bounded temporary extraction, no scoring or persistence."""

import time
from contextlib import asynccontextmanager, contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.responses import JSONResponse

from app import catalog
from app.api.candidates import CandidateDetail, CandidateId, StoredProfile
from app.api.jobs import JobDetail, JobId, catalog_session
from app.api.resumes import extract_upload
from app.errors import ErrorResponse, error_response
from app.extraction import configured_provider, structure_resume
from app.extraction_contracts import (
    ExtractionFailure,
    ExtractionJob,
    ExtractionSource,
    StructuredResume,
)
from app.matching import Assessment, assess_resume
from app.resumes import ResumePage

router = APIRouter(tags=["structured extraction"])
ERRORS = {
    "ai_not_configured": (
        503,
        "Structured extraction is disabled. Select AI_MODE explicitly on the backend.",
    ),
    "provider_configuration_error": (
        503,
        "Bedrock extraction is not configured correctly. "
        "Check backend region, model and credentials.",
    ),
    "provider_access_denied": (
        503,
        "Bedrock access was denied. "
        "Check model access and the backend credential's permissions or expiry.",
    ),
    "unsupported_model_capability": (
        503,
        "The configured Bedrock model or profile does not support this extraction request. "
        "Check the backend model and structured-output method.",
    ),
    "ai_unavailable": (503, "Structured extraction is unavailable. Try again later."),
    "provider_throttled": (503, "Bedrock is busy. Try again later."),
    "provider_timeout": (504, "Bedrock did not respond in time. Try again later."),
    "ai_timeout": (504, "Structured extraction took too long. Try again with a shorter resume."),
    "ai_busy": (503, "Structured extraction is busy. Try again shortly."),
    "ai_rate_limited": (
        429,
        "The extraction request limit was reached. Wait a minute and try again.",
    ),
    "ai_input_too_large": (
        413,
        "The resume and job exceed the AI text limit. Use a shorter resume; no text was truncated.",
    ),
    "invalid_model_output": (
        502,
        "The model did not return a valid extraction. No assessment was produced.",
    ),
    "invalid_evidence": (
        502,
        "The model returned evidence that could not be verified against the source. "
        "No assessment was produced.",
    ),
    "invalid_interpretation": (
        502,
        "The requirement interpretation could not be verified. No assessment was produced.",
    ),
}


async def extraction_error_handler(_request: Request, exc: ExtractionFailure) -> JSONResponse:
    code = exc.code if exc.code in ERRORS else "ai_unavailable"
    status, message = ERRORS[code]
    result = error_response(status, code, message)
    if code in {"ai_busy", "provider_throttled", "ai_rate_limited"}:
        result.headers["Retry-After"] = "60" if code == "ai_rate_limited" else "5"
    return result


def load_context(request: Request, job_id: str, candidate_id: str | None = None):
    # Snapshot in a sync dependency and close the read-only transaction BEFORE PDF/AI work.
    with contextmanager(catalog_session)(request) as session:
        row = catalog.get_job(session, job_id)
        if row is None:
            raise HTTPException(404)
        detail = JobDetail.model_validate(row)
        job = ExtractionJob(
            id=detail.id, title=detail.title, skills=detail.skills, requirements=detail.requirements
        )
        if candidate_id is None:
            return job, None
        candidate = catalog.get_candidate_for_job(session, job_id, candidate_id)
        if candidate is None:
            raise HTTPException(404)
        stored = StoredProfile.model_validate(candidate.profile)
        # Reuse module 7's corruption/provenance guard before using a demo source.
        profile = CandidateDetail.model_validate(
            {
                "id": candidate.id,
                "display_name": candidate.display_name,
                "headline": candidate.headline,
                "summary": candidate.summary,
                "is_demo": candidate.is_demo,
                "resume_text": candidate.resume_text,
                "claims": stored.claims,
            }
        )
        source = ExtractionSource(
            kind="synthetic_demo",
            candidate_id=profile.id,
            pages=[ResumePage(page_number=1, text=profile.resume_text)],
        )
        return job, source


def job_context(request: Request, job_id: JobId) -> ExtractionJob:
    return load_context(request, job_id)[0]


def demo_context(request: Request, job_id: JobId, candidate_id: CandidateId):
    return load_context(request, job_id, candidate_id)


@asynccontextmanager
async def extraction_slot(request: Request):
    settings = request.app.state.settings
    configured_provider(settings)  # No call, fallback or quota charge when unconfigured.
    if request.app.state.ai_active >= settings.ai_max_concurrent:
        raise ExtractionFailure("ai_busy")
    now = time.monotonic()
    recent = request.app.state.ai_requests
    while recent and recent[0] <= now - 60:
        recent.popleft()
    if len(recent) >= settings.ai_requests_per_minute:
        raise ExtractionFailure("ai_rate_limited")
    recent.append(now)
    request.app.state.ai_active += 1
    try:
        yield
    finally:
        request.app.state.ai_active -= 1


responses = {
    status: {"model": ErrorResponse} for status in (404, 408, 413, 415, 422, 429, 502, 503, 504)
}


@router.post(
    "/jobs/{job_id}/resumes/structure",
    response_model=StructuredResume,
    responses=responses,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def structure_upload(
    request: Request, response: Response, job: Annotated[ExtractionJob, Depends(job_context)]
) -> StructuredResume | JSONResponse:
    async with extraction_slot(request):
        extracted = await extract_upload(request, response)
        if isinstance(extracted, JSONResponse):
            return extracted
        source = ExtractionSource(kind="uploaded_pdf", pages=extracted.pages)
        result = await structure_resume(job, source, request.app.state.settings)
        response.headers["Cache-Control"] = "no-store"
        return result


@router.post(
    "/jobs/{job_id}/candidates/{candidate_id}/structure",
    response_model=StructuredResume,
    responses=responses,
)
async def structure_demo(
    request: Request,
    response: Response,
    context: Annotated[tuple[ExtractionJob, ExtractionSource], Depends(demo_context)],
) -> StructuredResume:
    # This route accepts no client profile, scores, prompts or job requirements.
    if request.headers.get("content-length", "0") != "0" or request.headers.get(
        "transfer-encoding"
    ):
        raise HTTPException(400)
    async with extraction_slot(request):
        result = await structure_resume(*context, request.app.state.settings)
        response.headers["Cache-Control"] = "no-store"
        return result


@router.post(
    "/jobs/{job_id}/resumes/assess",
    response_model=Assessment,
    responses=responses,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def assess_upload(
    request: Request, response: Response, job: Annotated[ExtractionJob, Depends(job_context)]
) -> Assessment | JSONResponse:
    async with extraction_slot(request):
        extracted = await extract_upload(request, response)
        if isinstance(extracted, JSONResponse):
            return extracted
        source = ExtractionSource(kind="uploaded_pdf", pages=extracted.pages)
        structured = await structure_resume(job, source, request.app.state.settings)
        result = await assess_resume(structured, request.app.state.settings)
        response.headers["Cache-Control"] = "no-store"
        return result


@router.post(
    "/jobs/{job_id}/candidates/{candidate_id}/assess",
    response_model=Assessment,
    responses=responses,
)
async def assess_demo(
    request: Request,
    response: Response,
    context: Annotated[tuple[ExtractionJob, ExtractionSource], Depends(demo_context)],
) -> Assessment:
    if request.headers.get("content-length", "0") != "0" or request.headers.get(
        "transfer-encoding"
    ):
        raise HTTPException(400)
    async with extraction_slot(request):
        structured = await structure_resume(*context, request.app.state.settings)
        result = await assess_resume(structured, request.app.state.settings)
        response.headers["Cache-Control"] = "no-store"
        return result
