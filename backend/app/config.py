"""Validated server configuration; provider use remains an explicit choice."""

from pathlib import Path
from typing import Literal

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
    resume_max_bytes: int = Field(
        default=5 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024, validation_alias="RESUME_MAX_BYTES"
    )
    resume_max_pages: int = Field(default=20, ge=1, le=50, validation_alias="RESUME_MAX_PAGES")
    resume_max_characters: int = Field(
        default=100_000, ge=100, le=200_000, validation_alias="RESUME_MAX_CHARACTERS"
    )
    resume_timeout_seconds: float = Field(
        default=10, ge=0.1, le=30, validation_alias="RESUME_TIMEOUT_SECONDS"
    )
    resume_upload_timeout_seconds: float = Field(
        default=15, ge=0.1, le=60, validation_alias="RESUME_UPLOAD_TIMEOUT_SECONDS"
    )
    resume_max_concurrent: int = Field(
        default=2, ge=1, le=4, validation_alias="RESUME_MAX_CONCURRENT"
    )
    ai_mode: Literal["mock", "bedrock"] | None = Field(default=None, validation_alias="AI_MODE")
    aws_region: str | None = Field(
        default=None, pattern=r"^[a-z]{2}(?:-[a-z]+)+-\d$", validation_alias="AWS_REGION"
    )
    bedrock_model_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
        pattern=r"^[a-zA-Z0-9.:/_-]+$",
        validation_alias="BEDROCK_MODEL_ID",
    )
    aws_bearer_token_bedrock: SecretStr | None = Field(
        default=None, validation_alias="AWS_BEARER_TOKEN_BEDROCK"
    )
    aws_profile: str | None = Field(
        default=None, min_length=1, max_length=128, validation_alias="AWS_PROFILE"
    )
    aws_access_key_id: SecretStr | None = Field(default=None, validation_alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: SecretStr | None = Field(
        default=None, validation_alias="AWS_SECRET_ACCESS_KEY"
    )
    aws_session_token: SecretStr | None = Field(default=None, validation_alias="AWS_SESSION_TOKEN")
    bedrock_structured_method: Literal["json_schema", "function_calling"] = Field(
        default="json_schema", validation_alias="BEDROCK_STRUCTURED_METHOD"
    )
    ai_max_input_characters: int = Field(
        default=20_000, ge=100, le=50_000, validation_alias="AI_MAX_INPUT_CHARACTERS"
    )
    ai_max_output_tokens: int = Field(
        default=3000, ge=256, le=8192, validation_alias="AI_MAX_OUTPUT_TOKENS"
    )
    ai_timeout_seconds: float = Field(
        default=45, ge=5, le=120, validation_alias="AI_TIMEOUT_SECONDS"
    )
    ai_max_attempts: int = Field(default=2, ge=1, le=2, validation_alias="AI_MAX_ATTEMPTS")
    ai_max_concurrent: int = Field(default=1, ge=1, le=2, validation_alias="AI_MAX_CONCURRENT")
    ai_requests_per_minute: int = Field(
        default=5, ge=1, le=20, validation_alias="AI_REQUESTS_PER_MINUTE"
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

    @field_validator("bedrock_model_id")
    @classmethod
    def model_is_not_an_endpoint(cls, value: str | None) -> str | None:
        if value is not None and "://" in value:
            raise ValueError("Use a Bedrock model or inference profile ID, not a URL")
        return value

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
            "database URLs, RESUME_*/AI_* limits, AWS/Bedrock settings and backend/.env; "
            "remove legacy APP_ENV."
        ) from None
