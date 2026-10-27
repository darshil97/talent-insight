"""Per-request trace IDs for logs and responses; an ID never carries request content."""

import logging
import re
import time
import uuid
from contextvars import ContextVar, Token

from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADER = "X-Request-ID"
# Caller IDs are echoed into logs, so accept only short opaque tokens.
_valid_id = re.compile(r"[A-Za-z0-9._-]{1,64}")
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
logger = logging.getLogger(__name__)


def get_request_id() -> str | None:
    return _request_id.get()


def set_request_id(value: str | None) -> Token:
    return _request_id.set(value)


def reset_request_id(token: Token) -> None:
    _request_id.reset(token)


class RequestIdMiddleware:
    """Accept a well-formed caller ID or create one, echo it, and log one completion line."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        incoming = headers.get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _valid_id.fullmatch(incoming) else uuid.uuid4().hex
        token = _request_id.set(request_id)
        status = 500
        started = time.perf_counter()

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            # Log the route template, never the raw URL or query string.
            path = getattr(scope.get("route"), "path", None) or "unmatched"
            logger.log(
                logging.DEBUG if path == "/health" else logging.INFO,
                "%s %s -> %d in %.0f ms",
                scope["method"],
                path,
                status,
                (time.perf_counter() - started) * 1000,
            )
            _request_id.reset(token)
