"""Cloudflare Turnstile check before a screening starts; the secret key never leaves the backend."""

import logging
import re
import time

import httpx

from app.voice.contracts import VoiceFailure

logger = logging.getLogger(__name__)
VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
# The widget sends this action; a token minted for anything else is refused.
ACTION = "screening_start"
_VERIFY_TIMEOUT_SECONDS = 10
# Cloudflare error codes are short identifiers; anything else is not logged.
_ERROR_CODE = re.compile(r"^[a-z-]{1,40}$")
# Codes that mean the backend's own key or Cloudflare is at fault, not the visitor.
_SERVER_CODES = {"missing-input-secret", "invalid-input-secret", "internal-error"}


def bot_check_enabled(settings) -> bool:
    return settings.turnstile_secret_key is not None


async def verify_bot_check(
    settings, token: str | None, transport: httpx.AsyncBaseTransport | None = None
) -> None:
    """Return when the check is off or passed; otherwise fail closed with a safe code."""
    if not bot_check_enabled(settings):
        return
    if not token:
        raise VoiceFailure("bot_check_failed")
    # The visitor's IP address is optional and is not sent.
    form = {"secret": settings.turnstile_secret_key.get_secret_value(), "response": token}
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=_VERIFY_TIMEOUT_SECONDS, transport=transport, follow_redirects=False
        ) as client:
            response = await client.post(VERIFY_URL, data=form)
    except httpx.TimeoutException:
        logger.warning("Turnstile verification timed out")
        raise VoiceFailure("bot_check_unavailable") from None
    except httpx.HTTPError as exc:
        # Messages can include request details; log the class only.
        logger.warning("Turnstile verification failed with %s", type(exc).__name__)
        raise VoiceFailure("bot_check_unavailable") from None
    if response.status_code != 200:
        logger.warning("Turnstile verification returned HTTP %d", response.status_code)
        raise VoiceFailure("bot_check_unavailable")
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict) or not isinstance(body.get("success"), bool):
        logger.warning("Turnstile verification returned an unexpected response")
        raise VoiceFailure("bot_check_unavailable")
    codes = body.get("error-codes")
    codes = [code for code in codes if isinstance(code, str)] if isinstance(codes, list) else []
    shown = ", ".join(code for code in codes[:3] if _ERROR_CODE.match(code)) or "none"
    # Cloudflare's published test keys return no action. Only a test secret produces this
    # result, because production secrets reject test tokens.
    metadata = body.get("metadata")
    testing = isinstance(metadata, dict) and metadata.get("result_with_testing_key") is True
    if body["success"] and (body.get("action") == ACTION or testing):
        logger.info(
            "Bot check passed%s in %.0f ms",
            " with Cloudflare test keys" if testing else "",
            (time.perf_counter() - started) * 1000,
        )
        return
    if body["success"]:
        logger.warning("Bot check rejected: unexpected action")
        raise VoiceFailure("bot_check_failed")
    if _SERVER_CODES.intersection(codes):
        logger.warning("Bot check unavailable: %s", shown)
        raise VoiceFailure("bot_check_unavailable")
    logger.warning("Bot check rejected: %s", shown)
    raise VoiceFailure("bot_check_failed")
