"""Validated nested YAML defaults with private environment overrides."""

import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import (
    AnyHttpUrl,
    Field,
    SecretStr,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict, SettingsError

from app.database import database_url, is_loopback

BACKEND_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
BACKEND_CONFIG_FILE = Path(__file__).with_name("config.yaml")
_http_url = TypeAdapter(AnyHttpUrl)
_placeholder = re.compile(r"\$\{([A-Z][A-Z0-9_]*)(?::-([^}]*))?\}")
_yaml_fields = {
    "api.docs_enabled": "docs_enabled",
    "api.cors_allowed_origins": "cors_allowed_origins",
    "database.url": "database_url",
    "database.direct_url": "direct_database_url",
    "resumes.max_bytes": "resume_max_bytes",
    "resumes.max_pages": "resume_max_pages",
    "resumes.max_characters": "resume_max_characters",
    "resumes.timeout_seconds": "resume_timeout_seconds",
    "resumes.upload_timeout_seconds": "resume_upload_timeout_seconds",
    "resumes.max_concurrent": "resume_max_concurrent",
    "ai.mode": "ai_mode",
    "ai.max_input_characters": "ai_max_input_characters",
    "ai.max_output_tokens": "ai_max_output_tokens",
    "ai.timeout_seconds": "ai_timeout_seconds",
    "ai.max_attempts": "ai_max_attempts",
    "ai.max_concurrent": "ai_max_concurrent",
    "ai.requests_per_minute": "ai_requests_per_minute",
    "ai.bedrock.region": "aws_region",
    "ai.bedrock.model_id": "bedrock_model_id",
    "ai.bedrock.bearer_token": "aws_bearer_token_bedrock",
    "ai.bedrock.profile": "aws_profile",
    "ai.bedrock.access_key_id": "aws_access_key_id",
    "ai.bedrock.secret_access_key": "aws_secret_access_key",
    "ai.bedrock.session_token": "aws_session_token",
    "ai.bedrock.structured_method": "bedrock_structured_method",
    "matching.weights.mandatory": "match_weight_mandatory",
    "matching.weights.experience": "match_weight_experience",
    "matching.weights.preferred": "match_weight_preferred",
    "matching.weights.qualification": "match_weight_qualification",
}


class _UniqueKeysLoader(yaml.SafeLoader):
    """Reject duplicate keys instead of silently accepting the last value."""


def _unique_mapping(loader: _UniqueKeysLoader, node: yaml.MappingNode) -> dict:
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise ValueError("Invalid or duplicate YAML configuration key")
        result[key] = loader.construct_object(value_node)
    return result


_UniqueKeysLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def _resolve_placeholder(value: object) -> object:
    if not isinstance(value, str) or "${" not in value:
        return value
    match = _placeholder.fullmatch(value)
    if match is None:
        raise ValueError("Malformed YAML environment placeholder")
    return os.environ.get(match[1]) or (match[2] if match[2] else None)


def _yaml_settings() -> dict:
    """Flatten only known nested keys; environment and dotenv sources win above this."""
    with BACKEND_CONFIG_FILE.open(encoding="utf-8") as file:
        document = yaml.load(file, Loader=_UniqueKeysLoader)
    if not isinstance(document, dict):
        raise ValueError("Backend YAML configuration must be a mapping")
    result = {}

    def visit(node: object, path: str) -> None:
        if path in _yaml_fields:
            field = Settings.model_fields[_yaml_fields[path]]
            result[str(field.validation_alias)] = _resolve_placeholder(node)
        elif isinstance(node, dict) and node:
            for key, value in node.items():
                visit(value, f"{path}.{key}" if path else key)
        else:
            raise ValueError("Unknown or invalid backend YAML configuration key")

    visit(document, "")
    return result


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ENV_FILE,
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        case_sensitive=True,
        populate_by_name=True,
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )

    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
    ):
        return (init_settings, env_settings, dotenv_settings, _yaml_settings, file_secret_settings)

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
        default=8192, ge=256, le=8192, validation_alias="AI_MAX_OUTPUT_TOKENS"
    )
    ai_timeout_seconds: float = Field(
        default=130, ge=5, le=150, validation_alias="AI_TIMEOUT_SECONDS"
    )
    ai_max_attempts: int = Field(default=2, ge=1, le=2, validation_alias="AI_MAX_ATTEMPTS")
    ai_max_concurrent: int = Field(default=1, ge=1, le=2, validation_alias="AI_MAX_CONCURRENT")
    ai_requests_per_minute: int = Field(
        default=5, ge=1, le=20, validation_alias="AI_REQUESTS_PER_MINUTE"
    )
    match_weight_mandatory: int = Field(
        default=50, ge=0, le=100, validation_alias="MATCH_WEIGHT_MANDATORY"
    )
    match_weight_experience: int = Field(
        default=25, ge=0, le=100, validation_alias="MATCH_WEIGHT_EXPERIENCE"
    )
    match_weight_preferred: int = Field(
        default=15, ge=0, le=100, validation_alias="MATCH_WEIGHT_PREFERRED"
    )
    match_weight_qualification: int = Field(
        default=10, ge=0, le=100, validation_alias="MATCH_WEIGHT_QUALIFICATION"
    )

    @model_validator(mode="after")
    def scoring_weights_sum_to_100(self):
        if (
            sum(
                (
                    self.match_weight_mandatory,
                    self.match_weight_experience,
                    self.match_weight_preferred,
                    self.match_weight_qualification,
                )
            )
            != 100
        ):
            raise ValueError("Matching weights must sum to 100")
        return self

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
    except (ValidationError, SettingsError, OSError, UnicodeError, ValueError, yaml.YAMLError):
        raise RuntimeError(
            "Invalid backend configuration. Check app/config.yaml, DOCS_ENABLED, "
            "CORS_ALLOWED_ORIGINS, "
            "database URLs, RESUME_*/AI_*/MATCH_WEIGHT_* settings, "
            "AWS/Bedrock settings and backend/.env; "
            "remove legacy APP_ENV."
        ) from None
