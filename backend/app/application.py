"""Application composition without import-time environment loading."""

import asyncio
import logging
from collections import deque
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.availability import router as availability_router
from app.api.candidates import router as candidates_router
from app.api.extraction import extraction_error_handler
from app.api.extraction import router as extraction_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.resumes import router as resumes_router
from app.api.screenings import router as screenings_router
from app.api.screenings import voice_error_handler
from app.config import Settings, load_settings
from app.core.logging import configure_logging
from app.core.request_context import HEADER, RequestIdMiddleware
from app.database import create_database_engine
from app.errors import SafeErrorsMiddleware, register_error_handlers
from app.pipeline.contracts import ExtractionFailure
from app.usage import UsageRecorder, capture_model_calls, flush_periodically
from app.voice import sessions
from app.voice.contracts import VoiceFailure
from app.voice.sessions import SessionStore

logger = logging.getLogger(__name__)


async def purge_sessions(app: FastAPI) -> None:
    """Delete expired screenings on a timer, so transcripts never wait for the next request."""
    while True:
        await asyncio.sleep(sessions.PURGE_INTERVAL_SECONDS)
        try:
            app.state.voice_sessions.purge()
        except Exception as exc:
            logger.error("Session purge failed (%s)", type(exc).__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else load_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.database_url is not None:
            app.state.database_engine = create_database_engine(settings.database_url)
        purger = asyncio.create_task(purge_sessions(app))
        flusher = asyncio.create_task(flush_periodically(app))
        try:
            yield
        finally:
            for task in (purger, flusher):
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            # Queued rows are written once more; sessions still in memory are not recorded.
            await app.state.usage.flush(app.state.database_engine)
            if app.state.database_engine is not None:
                app.state.database_engine.dispose()
                app.state.database_engine = None

    app = FastAPI(
        title="Talent Insight API",
        version="0.1.0",
        debug=False,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        redirect_slashes=False,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.database_engine = None
    app.state.resume_active = 0
    app.state.ai_active = 0
    app.state.ai_requests = deque()
    app.state.usage = UsageRecorder(settings)
    capture_model_calls()
    app.state.voice_sessions = SessionStore(settings, recorder=app.state.usage)
    # Tests replace these with httpx mock transports; None uses the network.
    app.state.deepgram_transport = None
    app.state.turnstile_transport = None
    register_error_handlers(app)
    app.add_exception_handler(ExtractionFailure, extraction_error_handler)
    app.add_exception_handler(VoiceFailure, voice_error_handler)
    app.include_router(health_router)
    app.include_router(jobs_router)
    app.include_router(candidates_router)
    app.include_router(resumes_router)
    app.include_router(extraction_router)
    app.include_router(availability_router)
    app.include_router(screenings_router)
    app.add_middleware(SafeErrorsMiddleware)
    # Wraps the error boundary so sanitized HTTP 500s also carry the request ID.
    app.add_middleware(RequestIdMiddleware)
    # Added last to wrap the error boundary, including sanitized HTTP 500s.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=[HEADER],
    )
    return app
