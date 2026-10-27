"""Isolate tests from real configuration and issue HTTP requests in process."""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from starlette.types import ASGIApp

from app.config import Settings
from app.llm.factory import clear_model_cache


@pytest.fixture(autouse=True)
def isolate_configuration(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if request.node.get_closest_marker("neon"):
        return
    for name in (
        "APP_ENV",
        "DOCS_ENABLED",
        "CORS_ALLOWED_ORIGINS",
        "DATABASE_URL",
        "DIRECT_DATABASE_URL",
        "RESUME_MAX_BYTES",
        "RESUME_MAX_PAGES",
        "RESUME_MAX_CHARACTERS",
        "RESUME_TIMEOUT_SECONDS",
        "RESUME_UPLOAD_TIMEOUT_SECONDS",
        "RESUME_MAX_CONCURRENT",
    ):
        monkeypatch.delenv(name, raising=False)
    for field in Settings.model_fields.values():
        if isinstance(field.validation_alias, str):
            monkeypatch.delenv(field.validation_alias, raising=False)
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-credentials"))
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no-aws-config"))
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING"):
        monkeypatch.setenv(name, "false")
    # Tests must never read a developer's backend/.env.
    monkeypatch.setitem(Settings.model_config, "env_file", tmp_path / "absent.env")
    # Each test builds its own chat model doubles.
    clear_model_cache()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--neon", action="store_true", help="Run read-only shared Neon checks")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not config.getoption("--neon"):
        skip = pytest.mark.skip(reason="Use --neon to enable read-only Neon checks")
        for item in items:
            if item.get_closest_marker("neon"):
                item.add_marker(skip)


@pytest.fixture
def api_request() -> Callable[..., httpx.Response]:
    def request(app: ASGIApp, method: str, path: str, **kwargs: Any) -> httpx.Response:
        async def send() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    return request
