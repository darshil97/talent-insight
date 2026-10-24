"""Ensure errors remain useful without exposing input or exception payloads."""

from collections.abc import Callable

import httpx
import pytest
from fastapi import HTTPException
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from app.application import create_app
from app.config import Settings

PRIVATE = "synthetic-sensitive-value-do-not-echo"


class Payload(BaseModel):
    years: int


def test_validation_error_does_not_echo_inputs_or_logs(
    api_request: Callable[..., httpx.Response], caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(Settings())

    @app.post("/test-input")
    async def validate(payload: Payload) -> Payload:
        return payload

    response = api_request(app, "POST", "/test-input", json={"years": PRIVATE})
    assert response.status_code == 422
    assert response.json() == {
        "error": {"code": "validation_error", "message": "Request validation failed."}
    }
    assert PRIVATE not in response.text + caplog.text
    assert response.headers["cache-control"] == "no-store"


def test_unhandled_error_keeps_cors_and_redacts_logs(
    api_request: Callable[..., httpx.Response], caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(Settings(cors_allowed_origins=("http://localhost:3000",)))

    @app.get("/test-failure")
    async def fail() -> None:
        raise RuntimeError(PRIVATE)

    response = api_request(app, "GET", "/test-failure", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "The service could not complete this request.",
        }
    }
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["cache-control"] == "no-store"
    assert "RuntimeError" in caplog.text
    assert PRIVATE not in response.text + caplog.text


def test_http_error_preserves_retry_header_without_echoing_details(
    api_request: Callable[..., httpx.Response], caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(Settings())

    @app.get("/test-limit")
    async def limited() -> None:
        raise HTTPException(429, detail=PRIVATE, headers={"Retry-After": "30"})

    response = api_request(app, "GET", "/test-limit")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limit_exceeded"
    assert response.headers["retry-after"] == "30"
    assert PRIVATE not in response.text + caplog.text


def test_invalid_response_model_is_internal_error(
    api_request: Callable[..., httpx.Response],
) -> None:
    app = create_app(Settings())

    @app.get("/test-invalid-response", response_model=Payload)
    async def invalid_response() -> dict[str, str]:
        return {"years": PRIVATE}

    response = api_request(app, "GET", "/test-invalid-response")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert PRIVATE not in response.text


def test_midstream_error_terminates_with_sanitized_exception(
    api_request: Callable[..., httpx.Response], caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(Settings())

    @app.get("/test-stream")
    async def stream() -> StreamingResponse:
        async def chunks():
            yield b"first chunk"
            raise RuntimeError(PRIVATE)

        return StreamingResponse(chunks())

    with pytest.raises(RuntimeError, match="Response stream interrupted") as caught:
        api_request(app, "GET", "/test-stream")
    assert caught.value.__suppress_context__ is True
    assert PRIVATE not in str(caught.value) + caplog.text
