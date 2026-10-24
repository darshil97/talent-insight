"""Temporary PDF contracts and a disposable, deadline-bound parser process."""

import asyncio
import json
import sys
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings


class ResumeLimits(BaseModel):
    max_bytes: int
    max_pages: int
    max_characters: int


class ResumePage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    page_number: int = Field(ge=1, le=50)
    text: str = Field(max_length=200_000)


class ExtractedResume(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source: Literal["uploaded_pdf"] = "uploaded_pdf"
    page_count: int = Field(ge=1, le=50)
    character_count: int = Field(ge=1, le=200_000)
    pages: list[ResumePage] = Field(min_length=1, max_length=50)


# Only these messages may cross the parser boundary. Never echo parser exceptions.
FAILURES = {
    "invalid_pdf": (422, "This PDF is malformed or unsupported. Export a new PDF and try again."),
    "encrypted_pdf": (422, "Password-protected PDFs are not supported. Upload an unencrypted PDF."),
    "empty_pdf": (422, "This PDF has no pages. Upload a PDF containing resume text."),
    "no_extractable_text": (
        422,
        "This PDF is blank or scanned and has no extractable text. "
        "Upload a text-based PDF; OCR is not available.",
    ),
    "too_many_pages": (413, "This PDF exceeds the page limit. Upload a shorter resume."),
    "too_much_text": (413, "This PDF exceeds the extracted-text limit. Upload a shorter resume."),
    "pdf_complexity_limit": (
        422,
        "This PDF is too complex to process. Export a simpler text-based PDF.",
    ),
    "extraction_timeout": (
        408,
        "PDF processing took too long. Export a simpler PDF and try again.",
    ),
}


class ResumeFailure(Exception):
    def __init__(self, code: str) -> None:
        self.code = code if code in FAILURES else "invalid_pdf"
        super().__init__(self.code)


async def extract_pdf(data: bytes, settings: Settings) -> ExtractedResume:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.pdf_worker",
        str(settings.resume_max_pages),
        str(settings.resume_max_characters),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with asyncio.timeout(settings.resume_timeout_seconds):
            output, _ = await process.communicate(data)
    except TimeoutError:
        raise ResumeFailure("extraction_timeout") from None
    finally:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        await process.wait()
    if process.returncode != 0:
        raise ResumeFailure("pdf_complexity_limit")
    # The worker writes bounded JSON only. Validate again before exposing it.
    if output.startswith(b'{"error":'):
        raise ResumeFailure(json.loads(output)["error"])
    result = ExtractedResume.model_validate_json(output)
    if (
        result.page_count != len(result.pages)
        or result.page_count > settings.resume_max_pages
        or result.character_count != sum(len(page.text) for page in result.pages)
        or result.character_count > settings.resume_max_characters
        or [page.page_number for page in result.pages] != list(range(1, result.page_count + 1))
    ):
        raise ResumeFailure("invalid_pdf")
    return result
