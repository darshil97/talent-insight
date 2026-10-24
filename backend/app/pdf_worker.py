"""Parse one untrusted PDF from stdin; no files, networking, metadata or diagnostics."""

import io
import json
import logging
import resource
import sys

from pypdf import PdfReader, overwrite_configuration
from pypdf.errors import DependencyError, LimitReachedError

from app.resumes import ExtractedResume, ResumeFailure, ResumePage


def parse_pdf(data: bytes, max_pages: int, max_characters: int) -> ExtractedResume:
    try:
        # Strict mode rejects broken cross-reference tables rather than repairing input.
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ResumeFailure("encrypted_pdf")
        count = len(reader.pages)
        if count == 0:
            raise ResumeFailure("empty_pdf")
        if count > max_pages:
            raise ResumeFailure("too_many_pages")
        pages = []
        characters = 0
        for number, page in enumerate(reader.pages, 1):
            text = page.extract_text()
            characters += len(text)
            if characters > max_characters:
                raise ResumeFailure("too_much_text")
            pages.append(ResumePage(page_number=number, text=text))
        if not any(page.text.strip() for page in pages):
            raise ResumeFailure("no_extractable_text")
        return ExtractedResume(page_count=count, character_count=characters, pages=pages)
    except ResumeFailure:
        raise
    except DependencyError:
        # AES password verification can require crypto extras before is_encrypted is available.
        # We reject encryption, so no decryption dependency or password handling is needed.
        raise ResumeFailure("encrypted_pdf") from None
    except (MemoryError, LimitReachedError):
        raise ResumeFailure("pdf_complexity_limit") from None
    except Exception:
        raise ResumeFailure("invalid_pdf") from None


def main() -> None:
    logging.disable(logging.CRITICAL)
    # Limits apply only to this disposable child, never the API process.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    memory_limit = 512 * 1024 * 1024
    # macOS does not enforce a useful address-space limit; Linux hosting must retain this cap.
    if sys.platform.startswith("linux"):
        _, existing_hard = resource.getrlimit(resource.RLIMIT_AS)
        if existing_hard != resource.RLIM_INFINITY:
            memory_limit = min(memory_limit, existing_hard)
        resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
    overwrite_configuration(
        maximum_declared_stream_length=4 * 1024 * 1024,
        array_based_stream_maximum_output_length=4 * 1024 * 1024,
        lzw_maximum_output_length=4 * 1024 * 1024,
        run_length_maximum_output_length=4 * 1024 * 1024,
        zlib_maximum_output_length=4 * 1024 * 1024,
        page_tree_maximum_entries=1000,
        page_tree_maximum_depth=30,
        xform_maximum_invocations_per_extraction=100,
    )
    data = sys.stdin.buffer.read(10 * 1024 * 1024 + 1)
    try:
        if len(data) > 10 * 1024 * 1024 or not data.startswith(b"%PDF-"):
            raise ResumeFailure("invalid_pdf")
        result = parse_pdf(data, int(sys.argv[1]), int(sys.argv[2]))
        output = result.model_dump_json()
    except ResumeFailure as exc:
        output = json.dumps({"error": exc.code})
    sys.stdout.write(output)


if __name__ == "__main__":
    main()
