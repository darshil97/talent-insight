"""Application composition without import-time environment loading."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.candidates import router as candidates_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.config import Settings, load_settings
from app.database import create_database_engine
from app.errors import SafeErrorsMiddleware, register_error_handlers


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.database_url is not None:
            app.state.database_engine = create_database_engine(settings.database_url)
        try:
            yield
        finally:
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
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(jobs_router)
    app.include_router(candidates_router)
    app.add_middleware(SafeErrorsMiddleware)
    # Added last to wrap the error boundary, including sanitized HTTP 500s.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Content-Type"],
    )
    return app
