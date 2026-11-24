"""Per-process AI admission: bounded concurrency and rolling one-minute and one-day counts."""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import Request

from app.llm.factory import ensure_ai_configured
from app.pipeline.contracts import ExtractionFailure

logger = logging.getLogger(__name__)
DAY_SECONDS = 86_400


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
    daily = request.app.state.ai_days
    while daily and daily[0] <= now - DAY_SECONDS:
        daily.popleft()
    if len(daily) >= settings.ai_assessments_per_day:
        logger.warning("AI request rejected: daily limit of %d reached", len(daily))
        raise ExtractionFailure("ai_daily_limit")
    recent.append(now)
    daily.append(now)
    request.app.state.ai_active += 1
    try:
        yield
    finally:
        request.app.state.ai_active -= 1
