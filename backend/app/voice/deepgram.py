"""Deepgram temporary-token grants; the permanent API key never leaves the backend."""

import logging
import time
from dataclasses import dataclass

import httpx

from app.voice.contracts import VoiceFailure
from app.voice.interviewer import check_interviewer

logger = logging.getLogger(__name__)
MOCK_TOKEN = "mock-deepgram-token"
_GRANT_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class Grant:
    access_token: str
    expires_in: int


def check_screening_configured(settings) -> None:
    """Any screening, voice or text, needs the interviewer and the context signing secret."""
    check_interviewer(settings)
    secret = settings.session_signing_secret
    if secret is None or len(secret.get_secret_value()) < 32:
        raise VoiceFailure("voice_configuration_error")


def check_voice_configured(settings) -> None:
    """Fail before any session or provider call when voice is off or incomplete."""
    if settings.voice_mode is None:
        raise VoiceFailure("voice_not_configured")
    check_screening_configured(settings)
    url = settings.voice_public_api_url
    if url is None:
        raise VoiceFailure("voice_configuration_error")
    if settings.voice_mode == "deepgram" and (
        settings.deepgram_api_key is None or not url.startswith("https://")
    ):
        raise VoiceFailure("voice_configuration_error")


async def grant_token(settings, transport: httpx.AsyncBaseTransport | None = None) -> Grant:
    if settings.voice_mode == "mock":
        return Grant(MOCK_TOKEN, settings.voice_token_ttl_seconds)
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            base_url=settings.voice_api_url,
            timeout=_GRANT_TIMEOUT_SECONDS,
            transport=transport,
            follow_redirects=False,
        ) as client:
            response = await client.post(
                "/v1/auth/grant",
                headers={"Authorization": f"Token {settings.deepgram_api_key.get_secret_value()}"},
                json={"ttl_seconds": settings.voice_token_ttl_seconds},
            )
    except httpx.TimeoutException:
        logger.warning("Deepgram grant timed out")
        raise VoiceFailure("voice_provider_timeout") from None
    except httpx.HTTPError as exc:
        # Messages can include request details; log the class only.
        logger.warning("Deepgram grant failed with %s", type(exc).__name__)
        raise VoiceFailure("voice_provider_unavailable") from None
    status = response.status_code
    if status != 200:
        code = (
            "voice_provider_access_denied"
            if status in (401, 403)
            else "voice_provider_throttled"
            if status == 429
            else "voice_provider_unavailable"
        )
        logger.warning("Deepgram grant returned HTTP %d (%s)", status, code)
        raise VoiceFailure(code)
    try:
        body = response.json()
        token = body["access_token"]
        expires_in = int(body.get("expires_in", settings.voice_token_ttl_seconds))
    except (ValueError, KeyError, TypeError):
        raise VoiceFailure("voice_provider_unavailable") from None
    if not isinstance(token, str) or not token or len(token) > 4096 or expires_in <= 0:
        raise VoiceFailure("voice_provider_unavailable")
    logger.info("Deepgram grant issued in %.0f ms", (time.perf_counter() - started) * 1000)
    return Grant(token, expires_in)
