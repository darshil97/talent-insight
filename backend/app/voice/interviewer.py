"""Server-side interviewer turns in OpenAI Chat Completions form, for Deepgram's think stage.

Incoming system prompts and model settings are discarded; the server renders its own
instructions from session context on every turn. Only spoken text is returned.
"""

import asyncio
import json
import logging
import math
import secrets
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from jinja2 import Environment, PackageLoader, StrictUndefined
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app import usage
from app.llm.base import get_provider
from app.llm.factory import MOCK_MODE, get_chat_model
from app.llm.response import extract_text
from app.pipeline.contracts import ExtractionFailure
from app.voice.agent_settings import END_FUNCTION, INTERVIEWER_MODEL_LABEL
from app.voice.contracts import InterviewContext, VoiceFailure
from app.voice.sessions import MAX_TRANSCRIPT_TURNS, ScreeningSession, TranscriptTurn

logger = logging.getLogger(__name__)
END_MARKER = "[[END]]"
MAX_CHAT_BYTES = 512 * 1024
MAX_RAW_MESSAGES = 400
MAX_MESSAGE_CHARACTERS = 20_000
MAX_CONSECUTIVE_FAILURES = 2
# Deepgram may send overlapping requests for one turn; allow that many per finished turn.
REQUEST_BUDGET_FACTOR = 3
CLOSING_TIME_UP = (
    "We've reached the end of our time. Thank you for speaking with me. "
    "A recruiter will review this conversation and follow up with next steps."
)
CLOSING_DONE = (
    "That's all my questions. Thank you for your time. "
    "A recruiter will review this conversation and follow up with next steps."
)
CLOSING_FAILURE = (
    "I'm having technical trouble, so I'll stop here. Thank you for your time. "
    "A recruiter will follow up, and you can also use the text option."
)
FALLBACK_LINE = "Sorry, I didn't catch that properly. Could you say that again?"
STATUS_NOTES = {
    "unknown": "not shown in the resume",
    "partial": "only partly shown in the resume",
    "transferable": "comparable but not identical experience shown",
    "not_met": "the resume does not show this",
    "met": "already shown in the resume; confirm briefly only if time remains",
}
_environment = Environment(
    loader=PackageLoader("app", "voice/prompts"),
    undefined=StrictUndefined,
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


class ChatMessage(BaseModel):
    # Deepgram may add OpenAI fields this endpoint does not use; ignore them.
    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)

    role: str = Field(max_length=32)
    content: str | list[dict] | None = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)

    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_RAW_MESSAGES)
    stream: bool = False


@dataclass
class Turn:
    """A fixed reply that needs no model call, or a model stream finished by MarkerFilter."""

    fixed: str | None
    end: bool
    deltas: AsyncIterator[str] | None = None
    # A conversational reply, counted toward the turn cap once it finishes.
    counted: bool = False


class MarkerFilter:
    """Strip the end marker from streamed text, holding back a possible partial marker."""

    def __init__(self) -> None:
        self.raw = ""
        self.sent = 0

    def _clean(self) -> str:
        return self.raw.replace(END_MARKER, "")

    def feed(self, delta: str) -> str:
        self.raw += delta
        clean = self._clean()
        safe = len(clean) - (len(END_MARKER) - 1)
        if safe <= self.sent:
            return ""
        out = clean[self.sent : safe]
        self.sent = safe
        return out

    def finish(self) -> str:
        clean = self._clean()
        out = clean[self.sent :]
        self.sent = len(clean)
        return out

    @property
    def ended(self) -> bool:
        return END_MARKER in self.raw

    @property
    def text(self) -> str:
        return self._clean().strip()


def parse_chat(body: bytes) -> ChatRequest:
    if len(body) > MAX_CHAT_BYTES:
        raise VoiceFailure("chat_request_too_large")
    try:
        chat = ChatRequest.model_validate_json(body)
    except ValidationError:
        raise VoiceFailure("invalid_chat_request") from None
    if any(
        len(message_text(message.content)) > MAX_MESSAGE_CHARACTERS for message in chat.messages
    ):
        raise VoiceFailure("invalid_chat_request")
    return chat


def message_text(content: str | list[dict] | None) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part["text"]
            for part in content
            if part.get("type") == "text" and isinstance(part.get("text"), str)
        )
    return ""


def conversation(chat: ChatRequest) -> list[tuple[str, str]]:
    """Candidate and interviewer text only; system, developer and tool messages are dropped."""
    turns: list[tuple[str, str]] = []
    for message in chat.messages:
        if message.role not in ("user", "assistant"):
            continue
        text = message_text(message.content).strip()
        if not text:
            continue
        if turns and turns[-1][0] == message.role:
            turns[-1] = (message.role, f"{turns[-1][1]}\n{text}")
        else:
            turns.append((message.role, text))
    return turns


def model_history(turns: list[tuple[str, str]], settings) -> list[tuple[str, str]]:
    """The most recent turns within budget, starting and ending with the candidate."""
    kept: list[tuple[str, str]] = []
    total = 0
    for role, text in reversed(turns[-settings.voice_max_messages :]):
        total += len(text)
        if total > settings.voice_max_history_characters:
            break
        kept.append((role, text))
    kept.reverse()
    while kept and kept[0][0] == "assistant":
        kept.pop(0)
    if not kept:
        kept = [("user", "[The candidate has joined the call and is ready.]")]
    elif kept[-1][0] == "assistant":
        kept.append(("user", "[No reply from the candidate yet.]"))
    return [("human" if role == "user" else "ai", text) for role, text in kept]


def render_prompt(context: InterviewContext, settings, elapsed_seconds: float) -> str:
    total = settings.voice_screening_seconds
    facts = json.dumps(
        [fact.model_dump() for fact in context.facts], ensure_ascii=False, indent=None
    )
    # Keep resume text from closing the delimiter; this stays valid JSON.
    facts = facts.replace("<", "\\u003c").replace(">", "\\u003e")
    template = _environment.get_template("interviewer.md")
    return template.render(
        job_title=context.job_title,
        topics=[
            {
                "description": topic.description,
                "note": STATUS_NOTES[topic.status],
                "question": topic.question,
            }
            for topic in context.topics
        ],
        facts_json=facts,
        wrap_up=elapsed_seconds >= settings.voice_wrap_up_seconds,
        elapsed_minutes=int(elapsed_seconds // 60),
        remaining_minutes=max(1, math.ceil((total - elapsed_seconds) / 60)),
        total_minutes=total // 60,
        max_follow_ups=1,
        end_marker=END_MARKER,
    ).strip()


def scripted_reply(context: InterviewContext, turns: list[tuple[str, str]]) -> tuple[str, bool]:
    """Mock mode: the job's authored questions in topic order, then a closing line."""
    questions = list(dict.fromkeys(topic.question or topic.description for topic in context.topics))
    answered = sum(role == "user" for role, _ in turns)
    index = max(0, answered - 1)
    if index < len(questions):
        prefix = "Thank you. " if index else ""
        return f"{prefix}{questions[index]}", False
    return CLOSING_DONE, True


def interviewer_settings(settings):
    """Model settings for interviewer turns: its own Bedrock model and region when configured.

    The extraction reasoning effort is cleared because its request field is model-specific; a
    separate value yields its own cached client, so turns never queue behind assessments.
    """
    return settings.model_copy(
        update={
            "bedrock_model_id": settings.voice_bedrock_model_id or settings.bedrock_model_id,
            "aws_region": settings.voice_aws_region or settings.aws_region,
            "bedrock_reasoning_effort": None,
        }
    )


def check_interviewer(settings) -> None:
    if settings.ai_mode is None:
        raise VoiceFailure("interviewer_not_configured")
    if settings.ai_mode != MOCK_MODE:
        try:
            get_provider(settings.ai_mode).check(interviewer_settings(settings))
        except ExtractionFailure:
            raise VoiceFailure("interviewer_not_configured") from None


def _add_usage(tokens: dict, metadata: object) -> None:
    """Bedrock reports token counts on the last streamed chunk; add whatever arrives."""
    if not isinstance(metadata, dict):
        return
    for key in tokens:
        value = metadata.get(key)
        if isinstance(value, int):
            tokens[key] = (tokens[key] or 0) + value


async def model_deltas(settings, system: str, history: list[tuple[str, str]]) -> AsyncIterator[str]:
    model_settings = interviewer_settings(settings)
    options: dict = {"max_tokens": settings.voice_max_output_tokens}
    # gpt-oss always reasons; other models get no reasoning field, so they answer directly.
    if (
        settings.ai_mode == "bedrock"
        and settings.voice_reasoning_effort is not None
        and "gpt-oss" in (model_settings.bedrock_model_id or "")
    ):
        options["additional_model_request_fields"] = {
            "reasoning_effort": settings.voice_reasoning_effort
        }
    started = time.perf_counter()
    first = None
    tokens = {"input_tokens": None, "output_tokens": None}
    stop = None
    # A newer request or a dropped client can close this stream mid-reply.
    outcome = "stopped"
    try:
        async with asyncio.timeout(settings.voice_turn_timeout_seconds):
            stream = get_chat_model(model_settings).astream(
                [("system", system), *history], config={"callbacks": []}, **options
            )
            async for chunk in stream:
                _add_usage(tokens, getattr(chunk, "usage_metadata", None))
                stop = (getattr(chunk, "response_metadata", None) or {}).get("stopReason") or stop
                text = extract_text(getattr(chunk, "content", ""))
                if text:
                    if first is None:
                        first = time.perf_counter()
                    yield text
        outcome = "ok"
    except VoiceFailure as exc:
        outcome = exc.code
        raise
    except TimeoutError:
        outcome = "provider_timeout"
        logger.warning("Interviewer turn timed out")
        raise VoiceFailure("provider_timeout") from None
    except Exception as exc:
        code = get_provider(settings.ai_mode).error_code(exc) or "ai_unavailable"
        outcome = code
        # Exception messages can contain request or credential details; log the class only.
        logger.warning("Interviewer turn failed with %s (%s)", code, type(exc).__name__)
        raise VoiceFailure(code) from None
    finally:
        usage.record(
            "voice_response",
            "interviewer_turn",
            outcome=outcome,
            provider=settings.ai_mode,
            model_id=model_settings.bedrock_model_id,
            region=model_settings.aws_region,
            latency_ms=round((time.perf_counter() - started) * 1000),
            first_output_ms=None if first is None else round((first - started) * 1000),
            stop_reason=stop,
            **tokens,
        )
    logger.info(
        "Interviewer turn: %s first text %s ms, total %.0f ms",
        model_settings.bedrock_model_id if settings.ai_mode == "bedrock" else settings.ai_mode,
        "none" if first is None else f"{(first - started) * 1000:.0f}",
        (time.perf_counter() - started) * 1000,
    )


def plan_turn(session: ScreeningSession, chat: ChatRequest, settings, now: float) -> Turn:
    """Decide the reply source; the caller owns in-flight state and transcript recording."""
    last_role = chat.messages[-1].role
    if last_role in ("tool", "function"):
        # The browser acknowledged end_screening; there is nothing more to say.
        return Turn("", False)
    if session.state == "ended":
        return Turn(CLOSING_TIME_UP, True)
    if session.started is None:
        session.started = now
        session.state = "active"
    session.requests += 1
    elapsed = now - session.started
    if (
        elapsed >= settings.voice_screening_seconds
        or session.turns >= settings.voice_max_turns
        or session.requests > settings.voice_max_turns * REQUEST_BUDGET_FACTOR
    ):
        return Turn(CLOSING_TIME_UP, True)
    turns = conversation(chat)
    if settings.ai_mode == MOCK_MODE:
        text, end = scripted_reply(session.context, turns)
        return Turn(text, end, counted=True)
    system = render_prompt(session.context, settings, elapsed)
    deltas = model_deltas(settings, system, model_history(turns, settings))
    return Turn(None, False, deltas, counted=True)


def record(
    session: ScreeningSession, chat: ChatRequest, reply: str, end: bool, counted: bool = False
) -> None:
    if counted:
        session.turns += 1
    turns = [
        TranscriptTurn("candidate" if role == "user" else "interviewer", text)
        for role, text in conversation(chat)
    ]
    if reply:
        turns.append(TranscriptTurn("interviewer", reply))
    session.transcript = turns[-MAX_TRANSCRIPT_TURNS:]
    if end and session.state != "ended":
        session.state = "ended"
        session.end_reason = (
            "time_limit"
            if reply == CLOSING_TIME_UP
            else "failure"
            if reply == CLOSING_FAILURE
            else "interviewer"
        )


def failure_reply(session: ScreeningSession) -> tuple[str, bool]:
    session.failures += 1
    if session.failures >= MAX_CONSECUTIVE_FAILURES:
        return CLOSING_FAILURE, True
    return FALLBACK_LINE, False


def _envelope(object_name: str, choice: dict) -> dict:
    return {
        "id": f"chatcmpl-{secrets.token_hex(8)}",
        "object": object_name,
        "created": int(time.time()),
        "model": INTERVIEWER_MODEL_LABEL,
        "choices": [{"index": 0, **choice}],
    }


def _tool_call() -> dict:
    return {
        "id": f"call_{END_FUNCTION}",
        "type": "function",
        "function": {"name": END_FUNCTION, "arguments": "{}"},
    }


def completion(text: str, end: bool) -> dict:
    message: dict = {"role": "assistant", "content": text}
    if end:
        message["tool_calls"] = [_tool_call()]
    return _envelope(
        "chat.completion",
        {"message": message, "finish_reason": "tool_calls" if end else "stop"},
    )


def chunk(delta: dict, finish_reason: str | None = None) -> str:
    body = _envelope("chat.completion.chunk", {"delta": delta, "finish_reason": finish_reason})
    return f"data: {json.dumps(body, ensure_ascii=False)}\n\n"


def final_chunks(end: bool) -> list[str]:
    events = []
    if end:
        events.append(chunk({"tool_calls": [{"index": 0, **_tool_call()}]}))
    events.append(chunk({}, "tool_calls" if end else "stop"))
    events.append("data: [DONE]\n\n")
    return events
