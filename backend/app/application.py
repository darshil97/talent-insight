"""Application composition without import-time environment loading."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.config import Settings, load_settings
from app.errors import SafeErrorsMiddleware, register_error_handlers


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else load_settings()
    app = FastAPI(
        title="Talent Insight API",
        version="0.1.0",
        debug=False,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        redirect_slashes=False,
    )
    app.state.settings = settings
    register_error_handlers(app)
    app.include_router(health_router)
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
