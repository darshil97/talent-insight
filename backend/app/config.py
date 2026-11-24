"""Validated nested YAML defaults with private environment overrides."""

import os
import re
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import (
    AnyHttpUrl,
    Field,
    SecretStr,
    StringConstraints,
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
    "api.log_level": "log_level",
    "database.url": "database_url",
    "database.direct_url": "direct_database_url",
    "resumes.max_bytes": "resume_max_bytes",
    "resumes.max_pages": "resume_max_pages",
    "resumes.max_characters": "resume_max_characters",
    "resumes.timeout_seconds": "resume_timeout_seconds",
    "resumes.upload_timeout_seconds": "resume_upload_timeout_seconds",
    "resumes.max_concurrent": "resume_max_concurrent",
    "ai.mode": "ai_mode",
    "ai.temperature": "ai_temperature",
    "ai.max_input_characters": "ai_max_input_characters",
    "ai.max_output_tokens": "ai_max_output_tokens",
    "ai.timeout_seconds": "ai_timeout_seconds",
    "ai.max_attempts": "ai_max_attempts",
    "ai.max_concurrent": "ai_max_concurrent",
    "ai.requests_per_minute": "ai_requests_per_minute",
    "ai.assessments_per_day": "ai_assessments_per_day",
    "ai.bedrock.region": "aws_region",
    "ai.bedrock.model_id": "bedrock_model_id",
    "ai.bedrock.bearer_token": "aws_bearer_token_bedrock",
    "ai.bedrock.profile": "aws_profile",
    "ai.bedrock.access_key_id": "aws_access_key_id",
    "ai.bedrock.secret_access_key": "aws_secret_access_key",
    "ai.bedrock.session_token": "aws_session_token",
    "ai.bedrock.structured_method": "bedrock_structured_method",
    "ai.bedrock.reasoning_effort": "bedrock_reasoning_effort",
    "matching.weights.mandatory": "match_weight_mandatory",
    "matching.weights.experience": "match_weight_experience",
    "matching.weights.preferred": "match_weight_preferred",
    "matching.weights.qualification": "match_weight_qualification",
    "matching.credits.transferable": "match_credit_transferable",
    "matching.credits.partial": "match_credit_partial",
    "ranking.availability_tiers": "ranking_availability_tiers",
    "voice.mode": "voice_mode",
    "voice.deepgram_api_key": "deepgram_api_key",
    "voice.signing_secret": "session_signing_secret",
    "voice.public_api_url": "voice_public_api_url",
    "voice.agent_url": "voice_agent_url",
    "voice.api_url": "voice_api_url",
    "voice.listen_model": "voice_listen_model",
    "voice.speak_model": "voice_speak_model",
    "voice.token_ttl_seconds": "voice_token_ttl_seconds",
    "voice.screening_seconds": "voice_screening_seconds",
    "voice.wrap_up_seconds": "voice_wrap_up_seconds",
    "voice.session_expiry_seconds": "voice_session_expiry_seconds",
    "voice.context_ttl_seconds": "voice_context_ttl_seconds",
    "voice.max_turns": "voice_max_turns",
    "voice.max_reconnects": "voice_max_reconnects",
    "voice.max_concurrent": "voice_max_concurrent",
    "voice.sessions_per_hour": "voice_sessions_per_hour",
    "voice.sessions_per_day": "voice_sessions_per_day",
    "voice.max_messages": "voice_max_messages",
    "voice.max_history_characters": "voice_max_history_characters",
    "voice.max_output_tokens": "voice_max_output_tokens",
    "voice.bedrock_model_id": "voice_bedrock_model_id",
    "voice.aws_region": "voice_aws_region",
    "voice.reasoning_effort": "voice_reasoning_effort",
    "voice.turn_timeout_seconds": "voice_turn_timeout_seconds",
    "bot_check.turnstile_site_key": "turnstile_site_key",
    "usage.recording": "usage_recording",
    "usage.token_prices": "usage_token_prices",
    "usage.deepgram_minute_price": "usage_deepgram_minute_price",
    "bot_check.turnstile_secret_key": "turnstile_secret_key",
}
_model_name = r"^[a-z0-9][a-z0-9.-]{0,79}$"


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
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", validation_alias="LOG_LEVEL"
    )
    # "mock" or a registered LLM provider name; see app/llm/providers.
    ai_mode: str | None = Field(default=None, validation_alias="AI_MODE")
    ai_temperature: float = Field(default=0, ge=0, le=1, validation_alias="AI_TEMPERATURE")
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
    bedrock_reasoning_effort: Literal["low", "medium", "high"] | None = Field(
        default=None, validation_alias="BEDROCK_REASONING_EFFORT"
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
    # Upload assessments admitted per process in a rolling 24 hours.
    ai_assessments_per_day: int = Field(
        default=100, ge=1, le=5000, validation_alias="AI_ASSESSMENTS_PER_DAY"
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
    # Requirement credit: met is 1 and not_met is 0; the middle levels are configurable.
    match_credit_transferable: float = Field(
        default=0.75, gt=0, lt=1, validation_alias="MATCH_CREDIT_TRANSFERABLE"
    )
    match_credit_partial: float = Field(
        default=0.5, gt=0, lt=1, validation_alias="MATCH_CREDIT_PARTIAL"
    )
    # (maximum days to join, ranking bonus) pairs; slower or unknown availability earns 0.
    ranking_availability_tiers: tuple[tuple[int, int], ...] = Field(
        default=((15, 5), (30, 4), (45, 3), (60, 2), (90, 1)),
        max_length=10,
        validation_alias="RANKING_AVAILABILITY_TIERS",
    )
    # Voice screening; credentials are checked when a screening starts, like AI_MODE.
    voice_mode: Literal["mock", "deepgram"] | None = Field(
        default=None, validation_alias="VOICE_MODE"
    )
    deepgram_api_key: SecretStr | None = Field(default=None, validation_alias="DEEPGRAM_API_KEY")
    session_signing_secret: SecretStr | None = Field(
        default=None, validation_alias="SESSION_SIGNING_SECRET"
    )
    voice_public_api_url: str | None = Field(default=None, validation_alias="VOICE_PUBLIC_API_URL")
    voice_agent_url: str = Field(
        default="wss://agent.deepgram.com/v1/agent/converse", validation_alias="VOICE_AGENT_URL"
    )
    voice_api_url: str = Field(default="https://api.deepgram.com", validation_alias="VOICE_API_URL")
    voice_listen_model: str = Field(
        default="flux-general-en", pattern=_model_name, validation_alias="VOICE_LISTEN_MODEL"
    )
    voice_speak_model: str = Field(
        default="aura-2-thalia-en", pattern=_model_name, validation_alias="VOICE_SPEAK_MODEL"
    )
    voice_token_ttl_seconds: int = Field(
        default=30, ge=10, le=300, validation_alias="VOICE_TOKEN_TTL_SECONDS"
    )
    voice_screening_seconds: int = Field(
        default=600, ge=60, le=1800, validation_alias="VOICE_SCREENING_SECONDS"
    )
    voice_wrap_up_seconds: int = Field(
        default=540, ge=30, le=1800, validation_alias="VOICE_WRAP_UP_SECONDS"
    )
    voice_session_expiry_seconds: int = Field(
        default=900, ge=120, le=3600, validation_alias="VOICE_SESSION_EXPIRY_SECONDS"
    )
    voice_context_ttl_seconds: int = Field(
        default=1800, ge=60, le=7200, validation_alias="VOICE_CONTEXT_TTL_SECONDS"
    )
    voice_max_turns: int = Field(default=40, ge=4, le=100, validation_alias="VOICE_MAX_TURNS")
    voice_max_reconnects: int = Field(
        default=2, ge=0, le=5, validation_alias="VOICE_MAX_RECONNECTS"
    )
    voice_max_concurrent: int = Field(
        default=1, ge=1, le=4, validation_alias="VOICE_MAX_CONCURRENT"
    )
    voice_sessions_per_hour: int = Field(
        default=6, ge=1, le=60, validation_alias="VOICE_SESSIONS_PER_HOUR"
    )
    voice_sessions_per_day: int = Field(
        default=20, ge=1, le=500, validation_alias="VOICE_SESSIONS_PER_DAY"
    )
    voice_max_messages: int = Field(
        default=80, ge=10, le=200, validation_alias="VOICE_MAX_MESSAGES"
    )
    voice_max_history_characters: int = Field(
        default=60_000, ge=2_000, le=200_000, validation_alias="VOICE_MAX_HISTORY_CHARACTERS"
    )
    voice_max_output_tokens: int = Field(
        default=300, ge=64, le=1024, validation_alias="VOICE_MAX_OUTPUT_TOKENS"
    )
    voice_bedrock_model_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
        pattern=r"^[a-zA-Z0-9.:/_-]+$",
        validation_alias="VOICE_BEDROCK_MODEL_ID",
    )
    voice_aws_region: str | None = Field(
        default=None, pattern=r"^[a-z]{2}(?:-[a-z]+)+-\d$", validation_alias="VOICE_AWS_REGION"
    )
    voice_reasoning_effort: Literal["low", "medium", "high"] | None = Field(
        default="low", validation_alias="VOICE_REASONING_EFFORT"
    )
    voice_turn_timeout_seconds: float = Field(
        default=20, ge=5, le=60, validation_alias="VOICE_TURN_TIMEOUT_SECONDS"
    )
    # Cloudflare Turnstile before a screening or upload assessment; off unless both keys are set.
    turnstile_site_key: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$", validation_alias="TURNSTILE_SITE_KEY"
    )
    turnstile_secret_key: SecretStr | None = Field(
        default=None, validation_alias="TURNSTILE_SECRET_KEY"
    )

    # Metered usage rows on Neon; recording needs DATABASE_URL as well.
    usage_recording: bool = Field(default=True, validation_alias="USAGE_RECORDING")
    # [model ID, USD per million input tokens, USD per million output tokens]; a tuple keeps
    # Settings hashable for the model-client cache.
    usage_token_prices: tuple[
        tuple[
            Annotated[str, StringConstraints(min_length=1, max_length=256)],
            Annotated[float, Field(ge=0)],
            Annotated[float, Field(ge=0)],
        ],
        ...,
    ] = Field(default=(), max_length=20, validation_alias="USAGE_TOKEN_PRICES")
    usage_deepgram_minute_price: float | None = Field(
        default=None, ge=0, validation_alias="USAGE_DEEPGRAM_MINUTE_PRICE"
    )

    @model_validator(mode="after")
    def turnstile_keys_are_paired(self):
        if (self.turnstile_site_key is None) != (self.turnstile_secret_key is None):
            raise ValueError("Set both Turnstile keys or neither")
        return self

    @model_validator(mode="after")
    def voice_times_are_ordered(self):
        if not (
            self.voice_wrap_up_seconds
            < self.voice_screening_seconds
            < self.voice_session_expiry_seconds
        ):
            raise ValueError("Voice wrap-up must precede the screening limit and session expiry")
        return self

    @field_validator("voice_public_api_url", "voice_api_url")
    @classmethod
    def voice_http_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        url = _http_url.validate_python(value)
        if url.scheme == "http" and not is_loopback(url.host or ""):
            raise ValueError("Non-loopback voice URLs must use HTTPS")
        if (
            value != value.strip()
            or url.username is not None
            or url.password is not None
            or url.query is not None
            or url.fragment is not None
        ):
            raise ValueError("Voice URLs cannot include credentials, queries or fragments")
        return str(url).removesuffix("/")

    @field_validator("voice_agent_url")
    @classmethod
    def voice_agent_websocket(cls, value: str) -> str:
        if (
            not re.fullmatch(r"wss://[a-z0-9.-]+\.deepgram\.com/v1/agent/converse", value)
            or ".." in value
        ):
            raise ValueError("VOICE_AGENT_URL must be a Deepgram wss:// agent endpoint")
        return value

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

    @model_validator(mode="after")
    def credits_are_ordered(self):
        if not self.match_credit_partial < self.match_credit_transferable:
            raise ValueError("Partial credit must be below transferable credit")
        return self

    @field_validator("ranking_availability_tiers")
    @classmethod
    def tiers_are_ordered(cls, tiers: tuple[tuple[int, int], ...]) -> tuple[tuple[int, int], ...]:
        days = [day for day, _ in tiers]
        bonuses = [bonus for _, bonus in tiers]
        if (
            any(day < 0 or day > 365 for day in days)
            or any(bonus < 0 or bonus > 10 for bonus in bonuses)
            or days != sorted(set(days))
            or bonuses != sorted(bonuses, reverse=True)
        ):
            raise ValueError("Availability tiers need ascending days and non-increasing bonuses")
        return tiers

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

    @field_validator("ai_mode")
    @classmethod
    def registered_ai_mode(cls, value: str | None) -> str | None:
        from app.llm.factory import ai_modes

        if value is not None and value not in ai_modes():
            raise ValueError("AI_MODE must be mock or a registered LLM provider")
        return value

    @field_validator("bedrock_model_id", "voice_bedrock_model_id")
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
            "CORS_ALLOWED_ORIGINS, LOG_LEVEL, "
            "database URLs, RESUME_*/AI_*/MATCH_*/RANKING_* settings, "
            "AWS/Bedrock settings, VOICE_*/DEEPGRAM_*/SESSION_SIGNING_SECRET settings, "
            "TURNSTILE_* keys, USAGE_* settings "
            "and backend/.env; "
            "remove legacy APP_ENV."
        ) from None
