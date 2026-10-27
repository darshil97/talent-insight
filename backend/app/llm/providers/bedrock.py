"""Amazon Bedrock Converse adapter; the pipeline, not the SDK, owns attempts and deadlines."""

import os

from app.llm.base import register_provider
from app.pipeline.contracts import ExtractionFailure

_CLIENT_ERRORS = {
    "AccessDeniedException": "provider_access_denied",
    "UnrecognizedClientException": "provider_access_denied",
    "ExpiredTokenException": "provider_access_denied",
    "ValidationException": "unsupported_model_capability",
    "ResourceNotFoundException": "provider_configuration_error",
    "ThrottlingException": "provider_throttled",
    "ServiceUnavailableException": "provider_throttled",
    "ModelTimeoutException": "provider_timeout",
}


class BedrockProvider:
    name = "bedrock"

    def check(self, settings) -> None:
        if not settings.aws_region or not settings.bedrock_model_id:
            raise ExtractionFailure("provider_configuration_error")

    def model_id(self, settings) -> str:
        return settings.bedrock_model_id

    def structured_method(self, settings):
        return settings.bedrock_structured_method

    def build(self, settings):
        from botocore.config import Config
        from langchain_aws import ChatBedrockConverse

        # Tracing can send full prompts to another service; keep it off in this process.
        for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING"):
            os.environ[name] = "false"
        options = {}
        if settings.aws_bearer_token_bedrock is not None:
            options["api_key"] = settings.aws_bearer_token_bedrock
        if settings.aws_profile is not None:
            options["credentials_profile_name"] = settings.aws_profile
        for name in ("aws_access_key_id", "aws_secret_access_key", "aws_session_token"):
            if getattr(settings, name) is not None:
                options[name] = getattr(settings, name)
        if settings.bedrock_reasoning_effort is not None:
            options["additional_model_request_fields"] = {
                "reasoning_effort": settings.bedrock_reasoning_effort
            }
        try:
            return ChatBedrockConverse(
                model_id=settings.bedrock_model_id,
                region_name=settings.aws_region,
                # Avoid implicit control-plane profile resolution; selection is explicit.
                base_model_id=settings.bedrock_model_id,
                max_tokens=settings.ai_max_output_tokens,
                temperature=settings.ai_temperature,
                config=Config(
                    connect_timeout=3,
                    read_timeout=min(60, settings.ai_timeout_seconds),
                    retries={"total_max_attempts": 1},
                    max_pool_connections=settings.ai_max_concurrent,
                ),
                cache=False,
                verbose=False,
                **options,
            )
        except (ValueError, TypeError):
            raise ExtractionFailure("provider_configuration_error") from None

    def error_code(self, exc: Exception) -> str | None:
        from botocore.exceptions import (
            BotoCoreError,
            ClientError,
            ConnectTimeoutError,
            NoCredentialsError,
            PartialCredentialsError,
            ReadTimeoutError,
        )

        if isinstance(exc, ClientError):
            code = exc.response.get("Error", {}).get("Code")
            return _CLIENT_ERRORS.get(code, "ai_unavailable")
        if isinstance(exc, ConnectTimeoutError | ReadTimeoutError):
            return "provider_timeout"
        if isinstance(exc, NoCredentialsError | PartialCredentialsError):
            return "provider_configuration_error"
        if isinstance(exc, BotoCoreError):
            return "ai_unavailable"
        return None


register_provider(BedrockProvider())
