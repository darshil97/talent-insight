"""Bounded model attempts: one stage deadline, server-written retry hints, best result kept."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.pipeline.contracts import (
    MAX_CITATIONS,
    MAX_FACTS,
    MAX_QUOTE_CHARACTERS,
    MAX_QUOTES_PER_FACT,
    MAX_REASON_CHARACTERS,
    MAX_VALUE_CHARACTERS,
    ExtractionFailure,
)

logger = logging.getLogger(__name__)
MAX_HINTS = 10
# Retry hints describe failed checks by location only. They never echo model or resume text.
HINTS = {
    "invalid_fact": "is not an object with a valid kind, a value and a non-empty evidence list",
    "value_too_long": f"value exceeds {MAX_VALUE_CHARACTERS} characters; use a short phrase",
    "invalid_citation": "needs an integer page_number and a non-empty quote",
    "page_out_of_range": "cites a page that does not exist",
    "quote_too_long": f"quote exceeds {MAX_QUOTE_CHARACTERS} characters",
    "quote_not_found": "quote does not appear verbatim on the cited page",
    "quote_ambiguous": "quote appears more than once on the page; quote a longer unique line",
    "no_verified_quote": "has no verifiable quote, so the fact was discarded",
    "value_not_in_quote": "value does not appear in its own quote",
    "duplicate_fact": "repeats an earlier fact",
    "over_fact_limit": f"exceeds the {MAX_FACTS}-fact limit",
    "extra_quotes_ignored": f"has more than {MAX_QUOTES_PER_FACT} quotes",
    "invalid_judgment": "is not an object with requirement_id, status, fact_indices and reason",
    "unknown_requirement": "uses a requirement_id that is not in the job",
    "missing_judgment": "has no judgment; return exactly one per requirement",
    "conflicting_judgments": "has more than one different judgment",
    "uncited_judgment": "is resolved but cites no valid verified mention",
    "invalid_fact_index": "cites an index outside the verified mentions",
    "too_many_citations": f"cites more than {MAX_CITATIONS} mentions",
    "reason_too_long": f"reason exceeds {MAX_REASON_CHARACTERS} characters",
    "missing_information_not_contrary": "is not_met but cites only missing-information text",
}


@dataclass(frozen=True)
class Outcome[T]:
    """One usable attempt; `retry_issues` is non-empty when another attempt is worthwhile."""

    value: T
    quality: int
    retry_issues: tuple[str, ...] = ()


def describe(issues: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    hints = []
    for issue in issues:
        location, _, code = issue.rpartition(": ")
        hint = f"{location}: {HINTS[code]}" if code in HINTS and location else issue
        if hint not in hints:
            hints.append(hint)
    return tuple(hints[:MAX_HINTS])


async def run_attempts[T](
    stage: str,
    settings,
    attempt_once: Callable[[int, tuple[str, ...]], Awaitable[Outcome[T]]],
) -> T:
    best: Outcome[T] | None = None
    feedback: tuple[str, ...] = ()
    try:
        async with asyncio.timeout(settings.ai_timeout_seconds):
            for attempt in range(1, settings.ai_max_attempts + 1):
                last = attempt == settings.ai_max_attempts
                try:
                    outcome = await attempt_once(attempt, feedback)
                except ExtractionFailure as exc:
                    if best is not None and (last or not exc.retryable):
                        return best.value
                    if last or not exc.retryable:
                        raise
                    logger.warning("%s attempt %d failed (%s); retrying", stage, attempt, exc.code)
                    feedback = describe(exc.issues)
                    await asyncio.sleep(0.2)
                    continue
                if best is None or outcome.quality > best.quality:
                    best = outcome
                if last or not outcome.retry_issues:
                    return best.value
                logger.warning(
                    "%s attempt %d: most returned items failed validation; retrying", stage, attempt
                )
                feedback = describe(outcome.retry_issues)
                await asyncio.sleep(0.2)
    except TimeoutError:
        if best is not None:
            logger.warning("%s deadline reached; keeping the best validated attempt", stage)
            return best.value
        raise ExtractionFailure("ai_timeout") from None
    raise ExtractionFailure("ai_unavailable")
