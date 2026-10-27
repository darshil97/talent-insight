"""Provider selection and one cached chat model per effective settings value."""

import app.llm.providers  # noqa: F401  Registers the available providers.
from app.llm.base import get_provider, provider_names
from app.pipeline.contracts import ExtractionFailure

MOCK_MODE = "mock"
_models: dict = {}


def ai_modes() -> tuple[str, ...]:
    return (MOCK_MODE, *provider_names())


def ensure_ai_configured(settings) -> None:
    """Fail before any upload, quota charge or call when AI is off or incomplete."""
    if settings.ai_mode is None:
        raise ExtractionFailure("ai_not_configured")
    if settings.ai_mode != MOCK_MODE:
        get_provider(settings.ai_mode).check(settings)


def model_id(settings) -> str | None:
    if settings.ai_mode == MOCK_MODE:
        return None
    return get_provider(settings.ai_mode).model_id(settings)


def get_chat_model(settings):
    # Settings are frozen and hashable; equal settings share one client and connection pool.
    model = _models.get(settings)
    if model is None:
        model = _models[settings] = get_provider(settings.ai_mode).build(settings)
    return model


def clear_model_cache() -> None:
    _models.clear()
