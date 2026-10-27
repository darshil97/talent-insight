"""Per-process AI admission: bounded concurrency and a rolling one-minute request count."""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import Request

from app.llm.factory import ensure_ai_configured
from app.pipeline.contracts import ExtractionFailure

logger = logging.getLogger(__name__)


@asynccontextmanager
async def ai_slot(request: Request):
    settings = request.app.state.settings
    ensure_ai_configured(settings)  # No call, fallback or quota charge when unconfigured.
    if request.app.state.ai_active >= settings.ai_max_concurrent:
        logger.warning(
            "AI request rejected: %d active of %d",
            request.app.state.ai_active,
            settings.ai_max_concurrent,
        )
        raise ExtractionFailure("ai_busy")
    now = time.monotonic()
    recent = request.app.state.ai_requests
    while recent and recent[0] <= now - 60:
        recent.popleft()
    if len(recent) >= settings.ai_requests_per_minute:
        logger.warning("AI request rejected: %d requests in the last minute", len(recent))
        raise ExtractionFailure("ai_rate_limited")
    recent.append(now)
    request.app.state.ai_active += 1
    try:
        yield
    finally:
        request.app.state.ai_active -= 1
