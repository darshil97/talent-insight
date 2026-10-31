"""Exercise the application factory without external services."""

from collections.abc import Callable

import httpx
import pytest

from app.application import create_app
from app.config import Settings


def test_health_is_typed_minimal_and_not_cached(api_request: Callable[..., httpx.Response]) -> None:
    app = create_app(Settings())
    response = api_request(app, "GET", "/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"


def test_unimplemented_api_returns_safe_not_found(
    api_request: Callable[..., httpx.Response],
) -> None:
    response = api_request(create_app(Settings()), "GET", "/not-implemented")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not Found."}}


def test_unsupported_method_preserves_allow_header(
    api_request: Callable[..., httpx.Response],
) -> None:
    response = api_request(create_app(Settings()), "POST", "/health")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert "GET" in response.headers["allow"]


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_documentation_can_be_disabled_explicitly(
    api_request: Callable[..., httpx.Response], path: str
) -> None:
    response = api_request(create_app(Settings(docs_enabled=False)), "GET", path)
    assert response.status_code == 404


def test_openapi_describes_health_contract(
    api_request: Callable[..., httpx.Response],
) -> None:
    app = create_app(Settings())
    assert api_request(app, "GET", "/docs").status_code == 200
    schema = api_request(app, "GET", "/openapi.json").json()
    assert set(schema["paths"]) == {
        "/health",
        "/jobs",
        "/jobs/{job_id}",
        "/jobs/{job_id}/candidates",
        "/jobs/{job_id}/candidates/{candidate_id}",
        "/resumes/limits",
        "/resumes/extract",
        "/jobs/{job_id}/resumes/structure",
        "/jobs/{job_id}/resumes/assess",
        "/availability",
        "/screenings/notice",
        "/screenings",
        "/screenings/{session_id}/token",
        "/screenings/{session_id}/end",
        "/screenings/{session_id}/report",
        "/screenings/{session_id}/messages",
        "/screenings/{session_id}/chat/completions",
    }
    assert all(
        set(path)
        == (
            {"post"}
            if name in {"/resumes/extract", "/availability", "/screenings"}
            or name.endswith(
                ("/structure", "/assess", "/token", "/end", "/report", "/completions", "/messages")
            )
            else {"get"}
        )
        for name, path in schema["paths"].items()
    )
    assert (
        schema["components"]["schemas"]["HealthResponse"]["properties"]["status"]["const"] == "ok"
    )


def test_factory_creates_isolated_configuration() -> None:
    first = create_app(Settings(cors_allowed_origins=("http://localhost:3000",)))
    second = create_app(Settings(docs_enabled=False))
    assert first.state.settings.cors_allowed_origins == ("http://localhost:3000",)
    assert second.state.settings.cors_allowed_origins == ()
    assert first.debug is False
    assert second.debug is False


def test_factory_rejects_invalid_settings_before_serving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOCS_ENABLED", "invalid-flag")
    with pytest.raises(RuntimeError, match="Invalid backend configuration"):
        create_app()
