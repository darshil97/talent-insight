"""Application log format with the active request ID; callers log codes and counts only."""

import logging

from app.core.request_context import get_request_id

FORMAT = "%(asctime)s | %(request_id)s | %(levelname)s | %(name)s | %(message)s"


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


class _AppHandler(logging.StreamHandler):
    """Marker type so repeated configuration never duplicates output."""


def configure_logging(level: str = "INFO") -> None:
    """Configure only the `app` logger; Uvicorn and SDK loggers keep their own settings."""
    logger = logging.getLogger("app")
    logger.setLevel(level)
    if not any(isinstance(handler, _AppHandler) for handler in logger.handlers):
        handler = _AppHandler()
        handler.setFormatter(logging.Formatter(FORMAT))
        handler.addFilter(RequestIdFilter())
        logger.addHandler(handler)
