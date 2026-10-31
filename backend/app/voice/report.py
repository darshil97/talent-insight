"""Structured screening reports: what the candidate's own answers show, scored by the server.

The model chooses statuses and levels and must quote the candidate's exact words. Every quote is
checked against candidate turns, and every score and the suggested next step are calculated here.
A report lives only in its session's memory and the browser; nothing is stored.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from statistics import fmean
from typing import Literal

from jinja2 import Environment, PackageLoader, StrictUndefined
from pydantic import BaseModel

from app.llm.factory import MOCK_MODE
from app.llm.invoke import invoke_structured
from app.pipeline.attempts import Outcome, run_attempts
from app.pipeline.contracts import Category, ExtractionFailure, Status, provider_json_schema
from app.pipeline.evidence import locate_quote
from app.voice.contracts import InterviewContext
from app.voice.integrity import (
    FLAG_KINDS,
    FLAG_LABELS,
    MAX_FLAG_QUOTE_CHARACTERS,
    MAX_FLAGS,
    FlagKind,
    IntegrityFlag,
    merge_flags,
    rule_flags,
    unflagged_parts,
)
from app.voice.sessions import ScreeningSession, TranscriptTurn

logger = logging.getLogger(__name__)

TopicStatus = Literal["supported", "partly_supported", "not_shown", "declined", "not_covered"]
Correctness = Literal[
    "correct", "correct_after_hint", "comparable", "partly_correct", "incorrect", "not_applicable"
]
Dimension = Literal["relevance", "specificity", "ownership", "explanation"]
NextStep = Literal["interview", "gather_information", "human_review"]
EndReason = Literal["interviewer", "time_limit", "failure", "ended_early"]

TOPIC_STATUSES: tuple[TopicStatus, ...] = (
    "supported",
    "partly_supported",
    "not_shown",
    "declined",
    "not_covered",
)
CORRECTNESS: tuple[Correctness, ...] = (
    "correct",
    "correct_after_hint",
    "comparable",
    "partly_correct",
    "incorrect",
    "not_applicable",
)
DIMENSIONS: tuple[Dimension, ...] = ("relevance", "specificity", "ownership", "explanation")
# Illustrative credits: recovering after a hint or explaining an equivalent is not penalised much.
CORRECTNESS_CREDITS: dict[str, float] = {
    "correct": 1.0,
    "correct_after_hint": 0.8,
    "comparable": 0.75,
    "partly_correct": 0.5,
    "incorrect": 0.0,
}
# Illustrative rules for the suggested next step; a human always decides.
INTERVIEW_THRESHOLD = 67.0
COMPLETE_MIN_ANSWERS = 3
MAX_QUOTES = 3
MAX_QUOTE_CHARACTERS = 300
MAX_NOTE_CHARACTERS = 200
MAX_FOLLOW_UPS = 5
MAX_SUMMARY_CHARACTERS = 600
# A ten-minute transcript is far below this; the cap only bounds a pathological session.
MAX_INPUT_CHARACTERS = 60_000

_environment = Environment(
    loader=PackageLoader("app", "voice/prompts"),
    undefined=StrictUndefined,
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


# --- model output (provider schema only; validation below is item by item) ---


class TopicOutput(BaseModel):
    requirement_id: str
    status: TopicStatus
    correctness: Correctness
    prompted: bool
    quotes: list[str]
    note: str


class DimensionOutput(BaseModel):
    name: Dimension
    level: int
    quotes: list[str]
    reason: str


class FlagOutput(BaseModel):
    kind: FlagKind
    quote: str
    note: str


class ReportOutput(BaseModel):
    topics: list[TopicOutput]
    dimensions: list[DimensionOutput]
    integrity_flags: list[FlagOutput]
    follow_ups: list[str]
    summary: str


# --- API response ---


class ReportTopic(BaseModel):
    requirement_id: str
    category: Category
    description: str
    # What the resume assessment showed before the screening, for a resume → screening view.
    resume_status: Status
    status: TopicStatus
    correctness: Correctness
    prompted: bool
    quotes: list[str]
    note: str
    # Partly correct and incorrect rest on the model's own knowledge; a human should confirm.
    needs_check: bool


class ReportDimension(BaseModel):
    name: Dimension
    level: int
    score: float | None
    quotes: list[str]
    reason: str


class ScreeningReport(BaseModel):
    job_id: str
    job_title: str
    candidate_kind: Literal["demo", "upload"]
    evaluated_by: Literal["model", "mock", "none"]
    complete: bool
    end_reason: EndReason
    candidate_answers: int
    overall_score: float | None
    correctness_score: float | None
    dimensions: list[ReportDimension]
    topics: list[ReportTopic]
    unresolved: list[str]
    follow_ups: list[str]
    summary: str
    next_step: NextStep
    # Plain-language reasons for the suggestion, written from the same rules that chose it.
    next_step_reasons: list[str]
    # Attempts to steer the AI; captured as evidence, never obeyed, always sent to a human.
    integrity_flags: list[IntegrityFlag]


# --- validation ---


@dataclass
class ReportSalvage:
    topics: list[ReportTopic]
    dimensions: list[ReportDimension]
    follow_ups: list[str]
    summary: str
    flags: list[IntegrityFlag] = field(default_factory=list)
    claimed: int = 0
    discarded: int = 0
    issues: list[str] = field(default_factory=list)


def _topics(context: InterviewContext) -> list:
    """One entry per requirement, in the interviewer's priority order."""
    seen: dict[str, object] = {}
    for topic in context.topics:
        seen.setdefault(topic.requirement_id, topic)
    return list(seen.values())


def _text(raw: object, limit: int) -> str:
    if not isinstance(raw, str):
        return ""
    text = " ".join(raw.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# The model's usual copying slips: sentences stitched together across skipped words (with or
# without "…"), and a full stop or ellipsis added where it cut a sentence short. Repairs only
# ever move towards the transcript's own text.
_PARTS = re.compile(r"\s*(?:\.{3}|…)\s*|(?<=[.?!])\s+")
_ADDED_END = re.compile(r"(?:\.{3}|…|[\s.,;:!?])+$")
_SENTENCE_END = re.compile(r"[.?!](?=\s)")
_WORD = re.compile(r"\w+")


def _lower(text: str) -> str:
    """Lower case without changing length, so a match maps back to the original span."""
    return "".join(char.lower() if len(char.lower()) == 1 else char for char in text)


def _locate(answers: list[str], quote: str) -> str | None:
    """The exact candidate span for a quote, then allowing changed case or an added end mark.

    The fallbacks need three words, so a short fragment never matches by accident.
    """
    trimmed = _ADDED_END.sub("", quote)
    for needle in dict.fromkeys((quote, trimmed)):
        for fold in (False, True):
            if (needle != quote or fold) and len(_WORD.findall(needle)) < 3:
                continue
            for answer in answers:
                haystack, target = (_lower(answer), _lower(needle)) if fold else (answer, needle)
                span = locate_quote(haystack, target, unique=False)
                if isinstance(span, tuple):
                    start, end = span
                    # Keep the transcript's own end mark where the model replaced it.
                    if needle != quote and answer[end : end + 1] in (".", "?", "!"):
                        end += 1
                    return answer[start:end]
    return None


def _bounded(span: str) -> str | None:
    """An over-long passage cut after its last whole sentence within the limit."""
    if len(span) <= MAX_QUOTE_CHARACTERS:
        return span
    ends = [found.end() for found in _SENTENCE_END.finditer(span[: MAX_QUOTE_CHARACTERS + 1])]
    prefix = span[: ends[-1]] if ends else ""
    return prefix if len(_WORD.findall(prefix)) >= 3 else None


def _quotes(
    raw: object, answers: list[str], location: str, issues: list[str], *, whole: bool = False
) -> list[str]:
    """Exact candidate spans for the model's quotes; interviewer text never matches.

    Each kept quote is an exact span of one candidate turn. A quote stitched from sentences or
    "…" parts is kept as those parts only if every part matches; one changed or invented part
    rejects it. An over-long passage keeps its whole sentences up to the limit. With `whole`
    (integrity flags), a quote must match as one passage within the limit.
    """
    if not isinstance(raw, list):
        return []
    kept: list[str] = []
    for index, quote in enumerate(raw[:MAX_QUOTES]):
        if not isinstance(quote, str) or not quote.strip():
            continue
        quote = quote.strip()
        spans = [_locate(answers, quote)]
        if spans[0] is None and not whole:
            parts = [part for part in _PARTS.split(quote) if len(_WORD.findall(part)) >= 3]
            if len(parts) > 1:
                spans = [_locate(answers, part) for part in parts]
                spans = spans if all(spans) else [None]
        located = [span for span in spans if span is not None]
        bounded = [
            span if len(span) <= MAX_QUOTE_CHARACTERS else (None if whole else _bounded(span))
            for span in located
        ]
        for span in bounded:
            if span is not None and span not in kept:
                kept.append(span)
        if not located:
            issues.append(
                f"{location}.quotes[{index}]: is not copied exactly from one candidate turn"
            )
        elif not any(bounded):
            issues.append(f"{location}.quotes[{index}]: is over {MAX_QUOTE_CHARACTERS} characters")
    return kept[:MAX_QUOTES]


def _uncovered(topic) -> ReportTopic:
    return ReportTopic(
        requirement_id=topic.requirement_id,
        category=topic.category,
        description=topic.description,
        resume_status=topic.status,
        status="not_covered",
        correctness="not_applicable",
        prompted=False,
        quotes=[],
        note="",
        needs_check=False,
    )


def _unassessed(name: Dimension) -> ReportDimension:
    return ReportDimension(name=name, level=0, score=None, quotes=[], reason="")


def empty_salvage(context: InterviewContext, summary: str) -> ReportSalvage:
    return ReportSalvage(
        topics=[_uncovered(topic) for topic in _topics(context)],
        dimensions=[_unassessed(name) for name in DIMENSIONS],
        follow_ups=[],
        summary=summary,
    )


def salvage_report(
    value: object, context: InterviewContext, transcript: list[TranscriptTurn]
) -> ReportSalvage:
    """Keep each judgment only with a verified candidate quote; everything else is unassessed."""
    if not isinstance(value, dict):
        raise ExtractionFailure(
            "invalid_model_output",
            retryable=True,
            issues=("response: return one JSON object with topics, dimensions and the rest",),
        )
    answers = [turn.text for turn in transcript if turn.role == "candidate"]
    result = empty_salvage(context, "")
    issues = result.issues

    raw_topics = {}
    raw_list = value.get("topics") if isinstance(value.get("topics"), list) else []
    for index, raw in enumerate(raw_list):
        if isinstance(raw, dict) and isinstance(raw.get("requirement_id"), str):
            raw_topics.setdefault(raw["requirement_id"], (index, raw))
    for position, topic in enumerate(_topics(context)):
        found = raw_topics.get(topic.requirement_id)
        if found is None:
            issues.append(f"topics: {topic.requirement_id} is missing; return one entry per topic")
            continue
        index, raw = found
        status, correctness = raw.get("status"), raw.get("correctness")
        if status not in TOPIC_STATUSES or status == "not_covered":
            continue
        result.claimed += 1
        location = f"topics[{index}]"
        quotes = _quotes(raw.get("quotes"), answers, location, issues)
        if not quotes:
            result.discarded += 1
            issues.append(f"{location}: has no verifiable candidate quote, so it was discarded")
            continue
        if status == "declined" or correctness not in CORRECTNESS:
            correctness = "not_applicable"
        result.topics[position] = ReportTopic(
            requirement_id=topic.requirement_id,
            category=topic.category,
            description=topic.description,
            resume_status=topic.status,
            status=status,
            correctness=correctness,
            prompted=raw.get("prompted") is True,
            quotes=quotes,
            note=_text(raw.get("note"), MAX_NOTE_CHARACTERS),
            needs_check=correctness in ("partly_correct", "incorrect"),
        )

    raw_dimensions = {}
    raw_list = value.get("dimensions") if isinstance(value.get("dimensions"), list) else []
    for index, raw in enumerate(raw_list):
        if isinstance(raw, dict) and raw.get("name") in DIMENSIONS:
            raw_dimensions.setdefault(raw["name"], (index, raw))
    for position, name in enumerate(DIMENSIONS):
        found = raw_dimensions.get(name)
        if found is None:
            issues.append(f"dimensions: {name} is missing; return all four dimensions")
            continue
        index, raw = found
        level = raw.get("level")
        if type(level) is not int or not 1 <= level <= 4:
            continue
        result.claimed += 1
        location = f"dimensions[{index}]"
        quotes = _quotes(raw.get("quotes"), answers, location, issues)
        if not quotes:
            result.discarded += 1
            issues.append(f"{location}: has no verifiable candidate quote, so it was discarded")
            continue
        result.dimensions[position] = ReportDimension(
            name=name,
            level=level,
            score=round((level - 1) / 3 * 100, 1),
            quotes=quotes,
            reason=_text(raw.get("reason"), MAX_NOTE_CHARACTERS),
        )

    raw_flags = value.get("integrity_flags")
    for index, raw in enumerate(raw_flags[:MAX_FLAGS] if isinstance(raw_flags, list) else []):
        if not isinstance(raw, dict) or raw.get("kind") not in FLAG_KINDS:
            continue
        quotes = _quotes(
            [raw.get("quote")], answers, f"integrity_flags[{index}]", issues, whole=True
        )
        if not quotes or len(quotes[0]) > MAX_FLAG_QUOTE_CHARACTERS:
            continue
        result.flags.append(
            IntegrityFlag(
                kind=raw["kind"],
                quote=quotes[0],
                note=_text(raw.get("note"), MAX_NOTE_CHARACTERS),
                detected_by="ai",
            )
        )

    follow_ups = value.get("follow_ups") if isinstance(value.get("follow_ups"), list) else []
    for raw in follow_ups:
        text = _text(raw, MAX_NOTE_CHARACTERS)
        if text and text not in result.follow_ups and len(result.follow_ups) < MAX_FOLLOW_UPS:
            result.follow_ups.append(text)
    result.summary = _text(value.get("summary"), MAX_SUMMARY_CHARACTERS)
    return result


def _kept_evidence(quotes: list[str], flags: list[IntegrityFlag]) -> list[str]:
    kept: list[str] = []
    for quote in quotes:
        kept.extend(part for part in unflagged_parts(quote, flags) if part not in kept)
    return kept[:MAX_QUOTES]


def without_flagged_evidence(result: ReportSalvage, flags: list[IntegrityFlag]) -> None:
    """Remove manipulation attempts from quotes; a judgment left without any is unassessed."""
    if not flags:
        return
    for index, topic in enumerate(result.topics):
        kept = _kept_evidence(topic.quotes, flags)
        if kept != topic.quotes:
            result.topics[index] = (
                topic.model_copy(update={"quotes": kept})
                if kept
                else topic.model_copy(
                    update={
                        "status": "not_covered",
                        "correctness": "not_applicable",
                        "prompted": False,
                        "quotes": [],
                        "note": "",
                        "needs_check": False,
                    }
                )
            )
    for index, dimension in enumerate(result.dimensions):
        kept = _kept_evidence(dimension.quotes, flags)
        if kept != dimension.quotes:
            result.dimensions[index] = (
                dimension.model_copy(update={"quotes": kept})
                if kept
                else _unassessed(dimension.name)
            )


# --- deterministic scoring ---


def correctness_score(topics: list[ReportTopic]) -> float | None:
    credits = [
        CORRECTNESS_CREDITS[topic.correctness]
        for topic in topics
        if topic.correctness in CORRECTNESS_CREDITS
    ]
    return round(fmean(credits) * 100, 1) if credits else None


def overall_score(dimensions: list[ReportDimension], correctness: float | None) -> float | None:
    """Equal-weight mean of the assessed dimensions and correctness; needs at least two parts."""
    parts = [d.score for d in dimensions if d.score is not None]
    if correctness is not None:
        parts.append(correctness)
    return round(fmean(parts), 1) if len(parts) >= 2 else None


def is_complete(end_reason: EndReason, candidate_answers: int) -> bool:
    return end_reason in ("interviewer", "time_limit") and candidate_answers >= COMPLETE_MIN_ANSWERS


def _blocking(topics: list[ReportTopic]) -> list[ReportTopic]:
    """Mandatory topics the candidate declined, did not show or explained incorrectly."""
    return [
        topic
        for topic in topics
        if topic.category == "mandatory"
        and (topic.status in ("declined", "not_shown") or topic.correctness == "incorrect")
    ]


def next_step(
    complete: bool,
    overall: float | None,
    topics: list[ReportTopic],
    flags: list[IntegrityFlag] = (),
) -> NextStep:
    if not complete or flags:
        return "human_review"
    if overall is not None and overall >= INTERVIEW_THRESHOLD and not _blocking(topics):
        return "interview"
    return "gather_information"


def next_step_reasons(
    end_reason: EndReason,
    answers: int,
    overall: float | None,
    topics: list[ReportTopic],
    flags: list[IntegrityFlag] = (),
) -> list[str]:
    """The rule outcomes behind `next_step`, in the order the rules apply."""
    if flags:
        kinds = list(dict.fromkeys(flag.kind for flag in flags))
        return [
            *(f"Integrity flag: the candidate {FLAG_LABELS[kind]}" for kind in kinds),
            "Screenings with integrity flags always go to human review",
        ]
    if not is_complete(end_reason, answers):
        reasons = []
        if end_reason not in ("interviewer", "time_limit"):
            reasons.append(
                "Stopped by a technical problem"
                if end_reason == "failure"
                else "Ended before the interviewer closed it"
            )
        if answers < COMPLETE_MIN_ANSWERS:
            noun = "answer" if answers == 1 else "answers"
            reasons.append(f"Only {answers} candidate {noun} ({COMPLETE_MIN_ANSWERS} needed)")
        return [*reasons, "Incomplete screenings always go to human review"]
    threshold = round(INTERVIEW_THRESHOLD)
    if overall is None:
        reasons = ["Too little evidence to calculate answer quality"]
    else:
        verb = "meets" if overall >= INTERVIEW_THRESHOLD else "is below"
        reasons = [f"Answer quality {round(overall)} {verb} the interview threshold ({threshold})"]
    blocking = _blocking(topics)
    if blocking:
        names = "; ".join(topic.description.rstrip(".") for topic in blocking)
        reasons.append(f"Mandatory topic needs attention: {names}")
    else:
        reasons.append("No gaps in mandatory topics")
    return reasons


def unresolved(topics: list[ReportTopic]) -> list[str]:
    return [
        topic.description
        for topic in topics
        if topic.status != "supported" or topic.correctness in ("partly_correct", "incorrect")
    ]


# --- model call ---


def report_prompt(context: InterviewContext, issues: tuple[str, ...]) -> str:
    return (
        _environment.get_template("report.md")
        .render(
            job_title=context.job_title,
            max_quotes=MAX_QUOTES,
            max_quote_characters=MAX_QUOTE_CHARACTERS,
            max_note_characters=MAX_NOTE_CHARACTERS,
            max_follow_ups=MAX_FOLLOW_UPS,
            max_summary_characters=MAX_SUMMARY_CHARACTERS,
            max_flags=MAX_FLAGS,
            issues=issues,
            schema_json=json.dumps(provider_json_schema(ReportOutput), ensure_ascii=False),
        )
        .strip()
    )


def report_payload(context: InterviewContext, transcript: list[TranscriptTurn]) -> str:
    return json.dumps(
        {
            "topics": [
                {
                    "requirement_id": topic.requirement_id,
                    "category": topic.category,
                    "description": topic.description,
                }
                for topic in _topics(context)
            ],
            "transcript": [
                {"turn": index, "speaker": turn.role, "text": turn.text}
                for index, turn in enumerate(transcript)
            ],
        },
        ensure_ascii=False,
    )


async def _report_once(
    context: InterviewContext,
    transcript: list[TranscriptTurn],
    settings,
    attempt: int,
    issues: tuple[str, ...],
) -> Outcome[ReportSalvage]:
    value = await invoke_structured(
        settings,
        stage="report",
        attempt=attempt,
        system=report_prompt(context, issues),
        payload=report_payload(context, transcript),
        schema=provider_json_schema(ReportOutput),
        output_name="ScreeningReview",
        root_key="topics",
    )
    result = salvage_report(value, context, transcript)
    # Retry only when most judgments could not be verified; otherwise unassessed is honest.
    retry = tuple(result.issues) if result.discarded * 2 > max(result.claimed, 1) else ()
    return Outcome(result, quality=result.claimed - result.discarded, retry_issues=retry)


async def build_report(
    session: ScreeningSession, settings, end_reason: EndReason
) -> ScreeningReport:
    context = session.context
    transcript = list(session.transcript)
    answers = sum(turn.role == "candidate" for turn in transcript)
    if not answers:
        evaluated_by = "none"
        result = empty_salvage(context, "The candidate gave no answers, so nothing was assessed.")
    elif settings.ai_mode == MOCK_MODE:
        evaluated_by = "mock"
        result = empty_salvage(
            context, "Mock mode: no AI evaluation ran, so every topic is shown as not covered."
        )
    else:
        if len(report_payload(context, transcript)) > MAX_INPUT_CHARACTERS:
            raise ExtractionFailure("ai_input_too_large")
        evaluated_by = "model"
        result = await run_attempts(
            "report",
            settings,
            lambda attempt, issues: _report_once(context, transcript, settings, attempt, issues),
        )
    # Server rules run on every transcript, so a flag survives even a manipulated model.
    flags = merge_flags(
        rule_flags([turn.text for turn in transcript if turn.role == "candidate"]), result.flags
    )
    without_flagged_evidence(result, flags)
    correctness = correctness_score(result.topics)
    overall = overall_score(result.dimensions, correctness)
    complete = is_complete(end_reason, answers)
    report = ScreeningReport(
        job_id=context.job_id,
        job_title=context.job_title,
        candidate_kind=context.candidate_kind,
        evaluated_by=evaluated_by,
        complete=complete,
        end_reason=end_reason,
        candidate_answers=answers,
        overall_score=overall,
        correctness_score=correctness,
        dimensions=result.dimensions,
        topics=result.topics,
        unresolved=unresolved(result.topics),
        follow_ups=result.follow_ups,
        summary=result.summary,
        next_step=next_step(complete, overall, result.topics, flags),
        next_step_reasons=next_step_reasons(end_reason, answers, overall, result.topics, flags),
        integrity_flags=flags,
    )
    logger.info(
        "Screening report: %s, %d answers, %d of %d judgments verified, %d integrity flags, "
        "next step %s",
        evaluated_by,
        answers,
        result.claimed - result.discarded,
        result.claimed,
        len(flags),
        report.next_step,
    )
    return report
