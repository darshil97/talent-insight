"""Voice screening sessions: consent, Deepgram tokens and the server-side interviewer.

Browser calls use JSON bodies, so the capability never needs a CORS header. Deepgram calls
the chat-completions route server to server with the capability as a bearer token.
"""

import logging
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Request, Response
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, StreamingResponse

from app import catalog
from app.api.candidates import cached_for_candidate
from app.api.deps import catalog_session
from app.api.jobs import JobDetail
from app.demo_cache import load_cache
from app.errors import ErrorResponse, error_response
from app.pipeline.contracts import Assessment
from app.voice.agent_settings import build_settings, greeting
from app.voice.context import demo_context, upload_context
from app.voice.contracts import (
    NOTICE_TEXT,
    NOTICE_VERSION,
    CapabilityRequest,
    MessageReply,
    MessageRequest,
    Notice,
    ScreeningRequest,
    ScreeningStart,
    ScreeningState,
    TokenGrant,
    VoiceFailure,
)
from app.voice.deepgram import check_screening_configured, check_voice_configured, grant_token
from app.voice.envelope import verify_context
from app.voice.interviewer import (
    MAX_CHAT_BYTES,
    ChatRequest,
    MarkerFilter,
    chunk,
    completion,
    failure_reply,
    final_chunks,
    parse_chat,
    plan_turn,
    record,
)
from app.voice.sessions import TranscriptTurn

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/screenings", tags=["screenings"])
SessionPath = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{22,64}$")]
ERRORS = {
    "voice_not_configured": (
        503,
        "Voice screening is disabled. Select VOICE_MODE explicitly on the backend.",
    ),
    "interviewer_not_configured": (
        503,
        "Voice screening needs AI_MODE on the backend for the interviewer.",
    ),
    "voice_configuration_error": (
        503,
        "Screening is not configured correctly. "
        "Check the backend signing secret, public URL and Deepgram key.",
    ),
    "consent_required": (
        422,
        "Consent to audio capture and AI processing under the current notice is required.",
    ),
    "invalid_screening_context": (
        422,
        "The screening context is invalid or has expired. Assess the resume again.",
    ),
    "screening_not_found": (404, "The screening was not found or has expired."),
    "screening_ended": (409, "This screening has ended."),
    "reconnect_limit_reached": (
        409,
        "This screening cannot reconnect again. Start a new screening.",
    ),
    "voice_busy": (503, "Another screening is in progress. Try again shortly."),
    "voice_rate_limited": (429, "The screening limit was reached. Try again later."),
    "turn_in_progress": (409, "The interviewer is still answering the previous turn."),
    "chat_request_too_large": (413, "The conversation request is too large."),
    "invalid_chat_request": (422, "The conversation request is invalid."),
    "voice_provider_access_denied": (
        503,
        "Deepgram rejected the backend API key. Check its permissions and expiry.",
    ),
    "voice_provider_throttled": (503, "Deepgram is busy. Try again shortly."),
    "voice_provider_timeout": (504, "Deepgram did not respond in time. Try again."),
    "voice_provider_unavailable": (503, "Deepgram is unavailable. Try again later."),
}
_RETRY_AFTER = {
    "voice_busy": "30",
    "voice_rate_limited": "600",
    "voice_provider_throttled": "5",
    "turn_in_progress": "1",
}
responses = {status: {"model": ErrorResponse} for status in (404, 409, 413, 422, 429, 503, 504)}


async def voice_error_handler(_request: Request, exc: VoiceFailure) -> JSONResponse:
    code = exc.code if exc.code in ERRORS else "voice_provider_unavailable"
    status, message = ERRORS[code]
    logger.warning("Screening request failed with %s (HTTP %d)", code, status)
    result = error_response(status, code, message)
    if code in _RETRY_AFTER:
        result.headers["Retry-After"] = _RETRY_AFTER[code]
    return result


def load_screening_job(
    request: Request, job_id: str, candidate_id: str | None
) -> tuple[JobDetail, Assessment | None]:
    # Close the read-only transaction before any provider call.
    with contextmanager(catalog_session)(request) as session:
        row = catalog.get_job(session, job_id)
        if row is None:
            raise HTTPException(404)
        job = JobDetail.model_validate(row)
        if candidate_id is None:
            return job, None
        candidate = catalog.get_candidate_for_job(session, job_id, candidate_id)
        if candidate is None:
            raise HTTPException(404)
        settings = request.app.state.settings
        return job, cached_for_candidate(load_cache(), row, candidate, settings)


def _voice_available(settings) -> bool:
    try:
        check_voice_configured(settings)
    except VoiceFailure:
        return False
    return True


@router.get("/notice", response_model=Notice, responses=responses)
def notice(request: Request, response: Response) -> Notice:
    settings = request.app.state.settings
    # Text screenings work whenever the interviewer is configured; voice is optional.
    check_screening_configured(settings)
    response.headers["Cache-Control"] = "no-store"
    return Notice(
        notice_version=NOTICE_VERSION,
        text=NOTICE_TEXT,
        screening_minutes=settings.voice_screening_seconds // 60,
        voice_available=_voice_available(settings),
        text_available=True,
    )


@router.post("", status_code=201, response_model=ScreeningStart, responses=responses)
async def start_screening(
    body: ScreeningRequest, request: Request, response: Response
) -> ScreeningStart:
    settings = request.app.state.settings
    voice = body.mode == "voice"
    if voice:
        check_voice_configured(settings)
    else:
        check_screening_configured(settings)
    consent = body.consent
    # Text screenings capture no audio, so only AI processing consent is required.
    if not (
        (consent.audio_capture is True or not voice)
        and consent.ai_processing is True
        and consent.notice_version == NOTICE_VERSION
    ):
        raise VoiceFailure("consent_required")
    if body.candidate.kind == "upload":
        payload = verify_context(
            body.candidate.context,
            settings.session_signing_secret.get_secret_value(),
            body.job_id,
        )
        job, _ = await run_in_threadpool(load_screening_job, request, body.job_id, None)
        context = upload_context(job, payload)
    else:
        job, assessment = await run_in_threadpool(
            load_screening_job, request, body.job_id, body.candidate.candidate_id
        )
        context = demo_context(job, assessment)
    store = request.app.state.voice_sessions
    session, capability = store.create(context)
    opening = greeting(context.job_title, settings.voice_screening_seconds // 60)
    grant = None
    if voice:
        try:
            grant = await grant_token(settings, request.app.state.deepgram_transport)
        except VoiceFailure:
            store.discard(session.id)
            raise
    else:
        # Deepgram reports the spoken greeting in its history; text records it here.
        session.transcript = [TranscriptTurn("interviewer", opening)]
    logger.info(
        "Screening started: %s, %s candidate, %d topics, assessment %s",
        body.mode,
        context.candidate_kind,
        len(context.topics),
        "available" if context.assessment_available else "unavailable",
    )
    response.headers["Cache-Control"] = "no-store"
    return ScreeningStart(
        session_id=session.id,
        capability=capability,
        mode=body.mode,
        expires_at=datetime.now(UTC) + timedelta(seconds=store.remaining_seconds(session)),
        greeting=opening,
        screening_seconds=settings.voice_screening_seconds,
        max_turns=settings.voice_max_turns,
        agent_url=settings.voice_agent_url if voice else None,
        deepgram_token=grant.access_token if grant else None,
        token_expires_in=grant.expires_in if grant else None,
        settings=build_settings(settings, session.id, capability, context.job_title)
        if voice
        else None,
    )


@router.post("/{session_id}/token", response_model=TokenGrant, responses=responses)
async def reconnect_token(
    session_id: SessionPath, body: CapabilityRequest, request: Request, response: Response
) -> TokenGrant:
    settings = request.app.state.settings
    check_voice_configured(settings)
    session = request.app.state.voice_sessions.get(session_id, body.capability)
    if session.state == "ended":
        raise VoiceFailure("screening_ended")
    if session.reconnects >= settings.voice_max_reconnects:
        raise VoiceFailure("reconnect_limit_reached")
    session.reconnects += 1
    grant = await grant_token(settings, request.app.state.deepgram_transport)
    response.headers["Cache-Control"] = "no-store"
    return TokenGrant(deepgram_token=grant.access_token, token_expires_in=grant.expires_in)


@router.post("/{session_id}/end", response_model=ScreeningState, responses=responses)
async def end_screening(
    session_id: SessionPath, body: CapabilityRequest, request: Request, response: Response
) -> ScreeningState:
    session = request.app.state.voice_sessions.get(session_id, body.capability)
    session.state = "ended"
    response.headers["Cache-Control"] = "no-store"
    return ScreeningState(session_id=session.id, state=session.state)


@router.post("/{session_id}/messages", response_model=MessageReply, responses=responses)
async def text_message(
    session_id: SessionPath, body: MessageRequest, request: Request, response: Response
) -> MessageReply:
    """Text turns, for text screenings or after switching from voice; history stays server-side."""
    settings = request.app.state.settings
    store = request.app.state.voice_sessions
    session = store.get(session_id, body.capability)
    now = store.clock()
    started = session.in_flight_since
    if started is not None and now - started < settings.voice_turn_timeout_seconds + 5:
        raise VoiceFailure("turn_in_progress")
    history = [
        {"role": "user" if turn.role == "candidate" else "assistant", "content": turn.text}
        for turn in session.transcript
    ]
    chat = ChatRequest.model_validate(
        {"messages": [*history, {"role": "user", "content": body.text}]}
    )
    turn = plan_turn(session, chat, settings, now)
    result = await _complete(session, chat, turn, _begin(session, turn, now))
    response.headers["Cache-Control"] = "no-store"
    return MessageReply(
        reply=result["choices"][0]["message"]["content"], ended=session.state == "ended"
    )


def _bearer(header: str | None) -> str:
    scheme, _, value = (header or "").partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        raise VoiceFailure("screening_not_found")
    return value.strip()


async def _read_limited(request: Request) -> bytes:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_CHAT_BYTES:
        raise VoiceFailure("chat_request_too_large")
    body = bytearray()
    async for part in request.stream():
        body.extend(part)
        if len(body) > MAX_CHAT_BYTES:
            raise VoiceFailure("chat_request_too_large")
    return bytes(body)


@router.post(
    "/{session_id}/chat/completions",
    responses=responses,
    openapi_extra={"description": "OpenAI-compatible interviewer turn, called by Deepgram."},
)
async def chat_completions(session_id: SessionPath, request: Request):
    settings = request.app.state.settings
    store = request.app.state.voice_sessions
    session = store.get(session_id, _bearer(request.headers.get("authorization")))
    chat = parse_chat(await _read_limited(request))
    now = store.clock()
    # Deepgram can send the next request before it drops the previous one. Rejecting it made
    # Deepgram give up on the call, so the newest request wins and an older stream stops.
    turn = plan_turn(session, chat, settings, now)
    turn_id = _begin(session, turn, now)
    headers = {"Cache-Control": "no-store"}
    if not chat.stream:
        return JSONResponse(await _complete(session, chat, turn, turn_id), headers=headers)
    return StreamingResponse(
        _stream(session, chat, turn, turn_id), media_type="text/event-stream", headers=headers
    )


def _begin(session, turn, now: float) -> int:
    """Make this request the session's active turn, replacing any older one."""
    if session.in_flight_since is not None:
        logger.info("Interviewer turn replaced by a newer request")
    session.active_turn += 1
    session.in_flight_since = now if turn.deltas is not None else None
    return session.active_turn


def _finish(session, turn_id: int) -> bool:
    """Release in-flight state if this turn is still active; return whether it is."""
    active = session.active_turn == turn_id
    if active:
        session.in_flight_since = None
    return active


async def _complete(session, chat, turn, turn_id: int) -> dict:
    text, end = turn.fixed or "", turn.end
    if turn.deltas is not None:
        marker = MarkerFilter()
        try:
            async for delta in turn.deltas:
                if session.active_turn != turn_id:
                    break
                marker.feed(delta)
            else:
                text, end = marker.text, marker.ended
                if not text:
                    raise VoiceFailure("invalid_model_output")
                session.failures = 0
        except VoiceFailure:
            if session.active_turn == turn_id:
                text, end = failure_reply(session)
        finally:
            await turn.deltas.aclose()
    # A replaced turn changes nothing: the newer request carries the whole conversation.
    if not _finish(session, turn_id):
        return completion("", False)
    record(session, chat, text, end, turn.counted)
    return completion(text, end)


async def _stream(session, chat, turn, turn_id: int):
    marker = MarkerFilter()
    sent = False
    replaced = False
    text, end = turn.fixed or "", turn.end
    try:
        yield chunk({"role": "assistant", "content": ""})
        if turn.deltas is None:
            if text:
                yield chunk({"content": text})
        else:
            try:
                async for delta in turn.deltas:
                    if session.active_turn != turn_id:
                        # Deepgram has moved on to a newer request; stop the model and end.
                        replaced = True
                        return
                    piece = marker.feed(delta)
                    if piece:
                        sent = True
                        yield chunk({"content": piece})
                rest = marker.finish()
                if rest:
                    sent = True
                    yield chunk({"content": rest})
                text, end = marker.text, marker.ended
                if not text:
                    raise VoiceFailure("invalid_model_output")
                session.failures = 0
            except VoiceFailure:
                if session.active_turn != turn_id:
                    replaced = True
                    return
                if sent:
                    # Keep what was already spoken; the next turn starts normally.
                    text, end = marker.text, False
                else:
                    text, end = failure_reply(session)
                    yield chunk({"content": text})
        for event in final_chunks(end):
            yield event
    finally:
        if turn.deltas is not None:
            await turn.deltas.aclose()
        if _finish(session, turn_id) and not replaced:
            record(session, chat, text, end, turn.counted)
