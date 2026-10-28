"""Short-lived signed upload context: tamper-evident and readable by its holder, not secret."""

import base64
import hashlib
import hmac
import json
import time

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.pipeline.contracts import Assessment
from app.voice.contracts import (
    MAX_CONTEXT_CHARACTERS,
    ContextFact,
    ContextJudgment,
    VoiceFailure,
)

_PURPOSE = b"talent-insight.screening-context.v1."
_CLOCK_SKEW_SECONDS = 60


class EnvelopePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    v: int
    job_id: str = Field(min_length=1, max_length=64)
    iat: int
    exp: int
    facts: list[ContextFact] = Field(max_length=40)
    judgments: list[ContextJudgment] = Field(max_length=100)


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _signature(secret: str, body: str) -> str:
    digest = hmac.new(secret.encode(), _PURPOSE + body.encode("ascii"), hashlib.sha256)
    return _encode(digest.digest())


def sign_context(assessment: Assessment, secret: str, ttl_seconds: int) -> str | None:
    """Sign only short fact phrases and requirement statuses; no quotes, pages or identity."""
    now = int(time.time())
    payload = EnvelopePayload(
        v=1,
        job_id=assessment.structured.job.id,
        iat=now,
        exp=now + ttl_seconds,
        facts=[
            ContextFact(kind=fact.kind, value=fact.value) for fact in assessment.structured.facts
        ],
        judgments=[
            ContextJudgment(requirement_id=item.requirement_id, status=item.status)
            for item in assessment.judgments
        ],
    )
    body = _encode(payload.model_dump_json().encode())
    token = f"{body}.{_signature(secret, body)}"
    # An oversized envelope could not be returned to /screenings, so do not issue one.
    return token if len(token) <= MAX_CONTEXT_CHARACTERS else None


def verify_context(token: str, secret: str, job_id: str) -> EnvelopePayload:
    body, separator, signature = token.partition(".")
    if (
        not separator
        or not body
        or not signature
        or len(token) > MAX_CONTEXT_CHARACTERS
        or not token.isascii()
    ):
        raise VoiceFailure("invalid_screening_context")
    if not hmac.compare_digest(signature, _signature(secret, body)):
        raise VoiceFailure("invalid_screening_context")
    try:
        payload = EnvelopePayload.model_validate(json.loads(_decode(body)))
    except (ValueError, ValidationError):
        raise VoiceFailure("invalid_screening_context") from None
    now = int(time.time())
    if (
        payload.v != 1
        or payload.job_id != job_id
        or payload.iat > now + _CLOCK_SKEW_SECONDS
        or payload.exp <= now
    ):
        raise VoiceFailure("invalid_screening_context")
    return payload
