"""Request IDs reach responses and logs without carrying request content."""

import logging
import re

import pytest

from app.application import create_app
from app.config import Settings
from app.core.logging import FORMAT, RequestIdFilter, configure_logging
from app.core.request_context import get_request_id


@pytest.fixture
def app():
    return create_app(Settings(cors_allowed_origins=("http://localhost:3000",)))


def test_generated_id_is_returned_and_logged_with_the_route_template(app, api_request, caplog):
    caplog.set_level(logging.INFO, logger="app")
    response = api_request(app, "GET", "/jobs/demo_ds?private=query")
    request_id = response.headers["x-request-id"]
    assert re.fullmatch(r"[0-9a-f]{32}", request_id)
    line = next(r for r in caplog.records if r.name == "app.core.request_context")
    assert line.request_id == request_id
    assert line.getMessage().startswith("GET /jobs/{job_id} -> 503 in ")
    assert "private=query" not in caplog.text and "demo_ds" not in caplog.text


@pytest.mark.parametrize(
    "incoming,kept",
    [
        ("trace-123_A.b", True),
        ("x" * 64, True),
        ("x" * 65, False),
        ("bad id", False),
        ("forged\nline", False),
        ("", False),
    ],
)
def test_only_well_formed_caller_ids_are_propagated(app, api_request, incoming, kept):
    response = api_request(app, "GET", "/health", headers={"X-Request-ID": incoming})
    assert (response.headers["x-request-id"] == incoming) is kept


def test_errors_and_unhandled_exceptions_carry_the_id_and_cors_exposes_it(app, api_request, caplog):
    @app.get("/test-failure")
    async def fail() -> None:
        assert get_request_id() == "trace-500"
        raise RuntimeError("private detail")

    origin = {"Origin": "http://localhost:3000"}
    missing = api_request(app, "GET", "/absent", headers=origin)
    assert missing.status_code == 404 and len(missing.headers["x-request-id"]) == 32
    failed = api_request(
        app, "GET", "/test-failure", headers={**origin, "X-Request-ID": "trace-500"}
    )
    assert failed.status_code == 500 and failed.headers["x-request-id"] == "trace-500"
    assert "x-request-id" in failed.headers["access-control-expose-headers"].lower()
    error = next(r for r in caplog.records if r.name == "app.errors")
    assert error.request_id == "trace-500" and "private detail" not in caplog.text
    assert get_request_id() is None


def test_health_completion_is_debug_only(app, api_request, caplog):
    caplog.set_level(logging.INFO, logger="app")
    api_request(app, "GET", "/health")
    assert not [r for r in caplog.records if r.name == "app.core.request_context"]


def test_logging_configuration_is_idempotent_and_formats_the_id():
    configure_logging("INFO")
    configure_logging("WARNING")
    logger = logging.getLogger("app")
    handlers = [
        h for h in logger.handlers if any(isinstance(f, RequestIdFilter) for f in h.filters)
    ]
    assert len(handlers) == 1 and logger.level == logging.WARNING
    record = logging.LogRecord("app.x", logging.INFO, __file__, 1, "message", (), None)
    handlers[0].filter(record)
    assert logging.Formatter(FORMAT).format(record).split(" | ")[1:] == [
        "-",
        "INFO",
        "app.x",
        "message",
    ]
    configure_logging("INFO")
