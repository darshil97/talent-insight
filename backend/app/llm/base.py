"""LLM provider protocol and registry; a new provider is one small registered adapter."""

from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from app.config import Settings

StructuredMethod = Literal["json_schema", "function_calling"]


class LLMProvider(Protocol):
    name: str

    def check(self, settings: "Settings") -> None:
        """Raise ExtractionFailure("provider_configuration_error") for incomplete settings."""

    def model_id(self, settings: "Settings") -> str:
        """The model identifier recorded with every result."""

    def structured_method(self, settings: "Settings") -> StructuredMethod:
        """How the model is asked for structured output."""

    def build(self, settings: "Settings") -> "BaseChatModel":
        """A configured chat model with SDK retries disabled; cached per settings value."""

    def error_code(self, exc: Exception) -> str | None:
        """A public error code for an SDK exception, or None when unrecognized."""


_PROVIDERS: dict[str, LLMProvider] = {}


def register_provider(provider: LLMProvider) -> LLMProvider:
    if provider.name == "mock":
        raise ValueError("'mock' is reserved for the offline pipeline mode")
    _PROVIDERS[provider.name] = provider
    return provider


def get_provider(name: str) -> LLMProvider:
    try:
        return _PROVIDERS[name]
    except KeyError:
        raise KeyError(f"Unknown LLM provider {name!r}; registered: {provider_names()}") from None


def provider_names() -> tuple[str, ...]:
    return tuple(sorted(_PROVIDERS))
