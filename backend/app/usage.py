"""Metered usage rows on Neon: counts, timings and prices only, never candidate content.

Rows wait in memory and a background task writes them in batches, so a slow or failing
database never delays a request. A clean shutdown writes queued rows once more; a crash loses them.
"""

import asyncio
import logging
import os
import secrets
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import insert, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.core.request_context import get_request_id
from app.models import UsageEvent

logger = logging.getLogger(__name__)
FLUSH_SECONDS = 10
MAX_QUEUED = 1000
# Render sets RENDER on its services; anything else is a local run against the same Neon.
ORIGIN = "render" if os.environ.get("RENDER") else "local"
COLUMNS = tuple(column.name for column in UsageEvent.__table__.columns if column.name != "id")
_MICRO = Decimal("0.000001")
# Structured model calls, recognised from the completion lines app.llm.invoke already writes.
# That package is part of the demo snapshot fingerprint, so it is read here, not changed.
STAGES = {
    "extraction": ("pdf", "resume_extraction"),
    "interpretation": ("pdf", "resume_interpretation"),
    "report": ("response_analysis", "screening_report"),
}
_COMPLETED = "%s attempt %d: %s %s stop=%s tokens=%s/%s in %.0f ms"
_FAILED = "%s attempt %d: %s call failed with %s (%s) after %.0f ms"


class UsageRecorder:
    def __init__(self, settings):
        self.settings = settings
        self.enabled = settings.usage_recording and settings.database_url is not None
        self.prices = {
            model: (inputs, outputs) for model, inputs, outputs in settings.usage_token_prices
        }
        self._queue: deque[dict] = deque()
        self.dropped = 0

    def add(self, category: str, operation: str, *, outcome: str = "ok", **values) -> None:
        if not self.enabled:
            return
        if len(self._queue) >= MAX_QUEUED:
            self.dropped += 1
            return
        row = dict.fromkeys(COLUMNS)
        row.update(values)
        row.update(
            created_at=datetime.now(UTC),
            origin=ORIGIN,
            category=category,
            operation=operation,
            outcome=outcome,
            request_id=get_request_id(),
        )
        if row["cost_usd"] is None:
            row["cost_usd"] = self.cost(row)
        self._queue.append(row)

    def cost(self, row: dict) -> Decimal | None:
        """USD at the configured prices; None when a price or a unit count is missing."""
        if row["category"] == "deepgram":
            price = self.settings.usage_deepgram_minute_price
            if price is None or row["seconds"] is None:
                return None
            return (Decimal(str(row["seconds"])) / 60 * Decimal(str(price))).quantize(_MICRO)
        prices = self.prices.get(row["model_id"] or "")
        if prices is None or row["input_tokens"] is None or row["output_tokens"] is None:
            return None
        total = row["input_tokens"] * Decimal(str(prices[0])) + row["output_tokens"] * Decimal(
            str(prices[1])
        )
        return (total / 1_000_000).quantize(_MICRO)

    async def flush(self, engine) -> None:
        if not self._queue or engine is None:
            return
        rows = list(self._queue)
        self._queue.clear()
        try:
            await asyncio.to_thread(_write, engine, rows)
        except OperationalError:
            # Neon unreachable or waking up: keep the rows for the next flush, within the cap.
            logger.warning("Usage rows not written yet: %d kept for retry", len(rows))
            room = MAX_QUEUED - len(self._queue)
            self._queue.extendleft(reversed(rows[:room]))
            self.dropped += max(0, len(rows) - room)
        except SQLAlchemyError as exc:
            logger.warning("Usage rows dropped: %d (%s)", len(rows), type(exc).__name__)
            self.dropped += len(rows)
        if self.dropped:
            logger.warning("Usage rows dropped so far: %d", self.dropped)
            self.dropped = 0


def _write(engine, rows: list[dict]) -> None:
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL statement_timeout = '5000ms'"))
        connection.execute(insert(UsageEvent), rows)


async def flush_periodically(app) -> None:
    """Write queued rows on a timer; the application stops it and flushes once more."""
    while True:
        await asyncio.sleep(FLUSH_SECONDS)
        try:
            await app.state.usage.flush(app.state.database_engine)
        except Exception as exc:
            logger.error("Usage flush failed (%s)", type(exc).__name__)


@dataclass(frozen=True)
class Scope:
    recorder: UsageRecorder
    screening_mode: str | None = None
    candidate_kind: str | None = None
    job_id: str | None = None
    screening_ref: str | None = None
    candidate_ref: str | None = None


_scope: ContextVar[Scope | None] = ContextVar("usage_scope", default=None)


def new_candidate_ref() -> str:
    """A random reference for one uploaded resume; it carries no identity."""
    return "up_" + secrets.token_hex(8)


def bind(recorder: UsageRecorder, **context) -> None:
    """Attach the recorder and screening context to the rest of this request's task.

    Not reset on purpose: a streamed reply and a report task started here still see it.
    """
    _scope.set(Scope(recorder, **context))


def record(category: str, operation: str, **values) -> None:
    scope = _scope.get()
    if scope is None:
        return
    scope.recorder.add(
        category,
        operation,
        screening_mode=scope.screening_mode,
        candidate_kind=scope.candidate_kind,
        job_id=scope.job_id,
        screening_ref=scope.screening_ref,
        candidate_ref=scope.candidate_ref,
        **values,
    )


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


class _ModelCallHandler(logging.Handler):
    """Turns app.llm.invoke completion and failure lines into usage rows."""

    def emit(self, entry: logging.LogRecord) -> None:
        scope = _scope.get()
        if scope is None or entry.msg not in (_COMPLETED, _FAILED):
            return
        try:
            if entry.msg == _COMPLETED:
                stage, attempt, provider, model_id, stop, inputs, outputs, ms = entry.args
                outcome = "ok"
            else:
                stage, attempt, provider, outcome, _kind, ms = entry.args
                model_id = stop = inputs = outputs = None
        except (TypeError, ValueError):
            return
        if provider == "mock" or stage not in STAGES:
            return
        settings = scope.recorder.settings
        values = {
            "outcome": outcome,
            "provider": provider,
            "model_id": model_id or settings.bedrock_model_id,
            "region": settings.aws_region,
            "attempt": attempt,
            "input_tokens": _count(inputs),
            "output_tokens": _count(outputs),
            "latency_ms": round(ms),
            "stop_reason": stop,
        }
        record(*STAGES[stage], **values)


def capture_model_calls() -> None:
    """Install the handler once; completion lines are needed even when LOG_LEVEL is higher."""
    source = logging.getLogger("app.llm.invoke")
    source.setLevel(logging.INFO)
    if not any(isinstance(handler, _ModelCallHandler) for handler in source.handlers):
        source.addHandler(_ModelCallHandler())
