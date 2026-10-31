"""Anonymous, stateless PDF extraction; never invokes a database or AI provider."""

import asyncio
import logging

from fastapi import APIRouter, Request, Response
from starlette.responses import JSONResponse

from app.errors import ErrorResponse, error_response
from app.resumes import FAILURES, ExtractedResume, ResumeFailure, ResumeLimits, extract_pdf

router = APIRouter(prefix="/resumes", tags=["resumes"])
logger = logging.getLogger(__name__)


@router.get("/limits", response_model=ResumeLimits)
async def limits(request: Request, response: Response) -> ResumeLimits:
    response.headers["Cache-Control"] = "no-store"
    settings = request.app.state.settings
    return ResumeLimits(
        max_bytes=settings.resume_max_bytes,
        max_pages=settings.resume_max_pages,
        max_characters=settings.resume_max_characters,
    )


@router.post(
    "/extract",
    response_model=ExtractedResume,
    responses={status: {"model": ErrorResponse} for status in (400, 408, 413, 415, 422, 503)},
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def extract(request: Request, response: Response) -> ExtractedResume | JSONResponse:
    return await extract_upload(request, response)


async def extract_upload(request: Request, response: Response) -> ExtractedResume | JSONResponse:
    """Shared byte validation/parser path for plain extraction and structured extraction."""
    settings = request.app.state.settings
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if (
        media_type != "application/pdf"
        or request.headers.get("content-encoding", "identity") != "identity"
    ):
        return error_response(
            415,
            "unsupported_media_type",
            "Upload a PDF using application/pdf without content encoding.",
        )
    declared_size = request.headers.get("content-length")
    if declared_size is not None:
        if not declared_size.isascii() or not declared_size.isdecimal():
            return error_response(400, "invalid_content_length", "Invalid upload length.")
        if len(declared_size) > 10 or int(declared_size) > settings.resume_max_bytes:
            return error_response(
                413, "payload_too_large", "This PDF exceeds the upload size limit."
            )
    # Reserve capacity before reading so slow uploads cannot form an unbounded queue.
    if request.app.state.resume_active >= settings.resume_max_concurrent:
        logger.warning("PDF upload rejected: %d parsers active", request.app.state.resume_active)
        result = error_response(503, "resume_busy", "PDF processing is busy. Try again shortly.")
        result.headers["Retry-After"] = "5"
        return result
    request.app.state.resume_active += 1
    try:
        data = bytearray()
        try:
            async with asyncio.timeout(settings.resume_upload_timeout_seconds):
                async for chunk in request.stream():
                    if len(data) + len(chunk) > settings.resume_max_bytes:
                        return error_response(
                            413, "payload_too_large", "This PDF exceeds the upload size limit."
                        )
                    data.extend(chunk)
        except TimeoutError:
            return error_response(408, "upload_timeout", "The upload took too long. Try again.")
        if not data:
            return error_response(
                422, "empty_upload", "The selected file is empty. Upload a text-based PDF."
            )
        if not data.startswith(b"%PDF-"):
            return error_response(
                415,
                "invalid_pdf_signature",
                "The file content is not a PDF. Export a PDF and try again.",
            )
        try:
            result = await extract_pdf(bytes(data), settings)
        except ResumeFailure as exc:
            status, message = FAILURES[exc.code]
            return error_response(status, exc.code, message)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return result
    finally:
        request.app.state.resume_active -= 1
