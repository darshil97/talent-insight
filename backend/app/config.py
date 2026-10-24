"""Validated process configuration; no provider credentials are needed yet."""

from pathlib import Path

from pydantic import (
    AnyHttpUrl,
    Field,
    SecretStr,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    field_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict, SettingsError

from app.database import database_url, is_loopback

BACKEND_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
_http_url = TypeAdapter(AnyHttpUrl)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
        populate_by_name=True,
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )

    docs_enabled: bool = Field(default=True, validation_alias="DOCS_ENABLED")
    cors_allowed_origins: tuple[str, ...] = Field(
        default=(), validation_alias="CORS_ALLOWED_ORIGINS"
    )
    database_url: SecretStr | None = Field(default=None, validation_alias="DATABASE_URL")
    direct_database_url: SecretStr | None = Field(
        default=None, validation_alias="DIRECT_DATABASE_URL"
    )

    @field_validator("cors_allowed_origins")
    @classmethod
    def validate_origins(cls, origins: tuple[str, ...]) -> tuple[str, ...]:
        normalized = []
        for origin in origins:
            if origin != origin.strip() or "*" in origin:
                raise ValueError("CORS origins must be explicit HTTP(S) origins")
            url = _http_url.validate_python(origin)
            if url.scheme == "http" and not is_loopback(url.host or ""):
                raise ValueError("Non-loopback CORS origins must use HTTPS")
            if (
                url.username is not None
                or url.password is not None
                or url.path not in (None, "/")
                or url.query is not None
                or url.fragment is not None
            ):
                raise ValueError(
                    "CORS origins cannot include credentials, paths, queries or fragments"
                )
            normalized.append(str(url).removesuffix("/"))
        return tuple(dict.fromkeys(normalized))

    @field_validator("database_url", "direct_database_url")
    @classmethod
    def validate_database_urls(
        cls, value: SecretStr | None, info: ValidationInfo
    ) -> SecretStr | None:
        if value is not None:
            database_url(value, direct=info.field_name == "direct_database_url")
        return value


def load_settings() -> Settings:
    """Fail startup without echoing configuration values or parsing errors."""
    try:
        return Settings()
    except (ValidationError, SettingsError, OSError, UnicodeError):
        raise RuntimeError(
            "Invalid backend configuration. Check DOCS_ENABLED, CORS_ALLOWED_ORIGINS, "
            "database URLs and backend/.env; remove legacy APP_ENV."
        ) from None
