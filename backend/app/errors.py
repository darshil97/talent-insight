"""Public error contracts and sanitized handling of unexpected exceptions."""

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


def error_response(status: int, code: str, message: str) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message))
    return JSONResponse(
        status_code=status,
        content=body.model_dump(),
        headers={"Cache-Control": "no-store"},
    )


async def http_error_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    code = {
        400: "bad_request",
        401: "authentication_required",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        413: "payload_too_large",
        415: "unsupported_media_type",
        422: "validation_error",
        429: "rate_limit_exceeded",
        500: "internal_error",
        503: "service_unavailable",
    }.get(exc.status_code, "http_error")
    if exc.status_code >= 500:
        message = "The service could not complete this request."
    else:
        try:
            message = HTTPStatus(exc.status_code).phrase + "."
        except ValueError:
            message = "Request could not be completed."
    response = error_response(exc.status_code, code, message)
    if exc.headers:
        response.headers.update(exc.headers)
    response.headers["Cache-Control"] = "no-store"
    return response


async def validation_error_handler(_request: Request, _exc: RequestValidationError) -> JSONResponse:
    # Pydantic error details may include submitted resumes or secret inputs.
    return error_response(422, "validation_error", "Request validation failed.")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)


class SafeErrorsMiddleware:
    """Catch inside CORS and outside routing; never log exception messages or bodies."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def track_start(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, track_start)
        except Exception as exc:
            logger.error("Unhandled API exception (%s).", type(exc).__name__)
            if response_started:
                # Headers cannot be replaced after streaming begins. Re-raise a
                # sanitized error so the server terminates the incomplete response.
                raise RuntimeError("Response stream interrupted.") from None
            response = error_response(
                500, "internal_error", "The service could not complete this request."
            )
            await response(scope, receive, send)
