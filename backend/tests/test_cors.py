"""Exercise the CORS protocol rather than inspecting middleware configuration."""

from collections.abc import Callable

import httpx
import pytest

from app.application import create_app
from app.config import Settings


def test_allows_only_exact_configured_origin(api_request: Callable[..., httpx.Response]) -> None:
    app = create_app(Settings(cors_allowed_origins=("http://localhost:3000",)))
    allowed = api_request(app, "GET", "/health", headers={"Origin": "http://localhost:3000"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "Origin" in allowed.headers["vary"]
    assert "access-control-allow-credentials" not in allowed.headers

    for origin in ("http://localhost:3001", "https://localhost:3000", "https://untrusted.example"):
        denied = api_request(app, "GET", "/health", headers={"Origin": origin})
        # CORS denies browser access, not execution of a simple HTTP request.
        assert denied.status_code == 200
        assert "access-control-allow-origin" not in denied.headers


def test_default_origins_deny_browser_access(api_request: Callable[..., httpx.Response]) -> None:
    response = api_request(
        create_app(Settings()),
        "GET",
        "/health",
        headers={"Origin": "https://untrusted.example"},
    )
    assert "access-control-allow-origin" not in response.headers


def test_allows_get_preflight_with_content_type(api_request: Callable[..., httpx.Response]) -> None:
    app = create_app(Settings(cors_allowed_origins=("http://localhost:3000",)))
    response = api_request(
        app,
        "OPTIONS",
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-allow-methods"] == "GET, POST"


@pytest.mark.parametrize(
    "overrides",
    [
        {"Origin": "https://untrusted.example"},
        {"Access-Control-Request-Method": "DELETE"},
        {"Access-Control-Request-Headers": "X-Unapproved-Header"},
    ],
)
def test_denies_unapproved_preflight(
    api_request: Callable[..., httpx.Response], overrides: dict[str, str]
) -> None:
    app = create_app(Settings(cors_allowed_origins=("http://localhost:3000",)))
    headers = {"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"}
    headers.update(overrides)
    assert api_request(app, "OPTIONS", "/health", headers=headers).status_code == 400
