"""Per-process screening sessions: opaque IDs, hashed capabilities, expiry and admission.

State is memory only. A restart drops every session, and several API processes would each
apply their own limits; this is a single-process safeguard, not a distributed quota.
"""

import hashlib
import hmac
import logging
import secrets
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from app.voice.contracts import InterviewContext, VoiceFailure

logger = logging.getLogger(__name__)
MAX_SESSIONS = 64
# An issued session that never reaches the interviewer stops holding a slot after this.
ACTIVATION_SECONDS = 180
# An active session whose client keeps talking past the limit stops counting as open.
OVERRUN_GRACE_SECONDS = 60
MAX_TRANSCRIPT_TURNS = 120
# Start times are kept for a day: the hourly and daily limits both count them.
HOUR_SECONDS = 3600
DAY_SECONDS = 86_400
# The application deletes expired sessions this often, even when no request arrives.
PURGE_INTERVAL_SECONDS = 60
State = Literal["issued", "active", "ended"]


def _hash(capability: str) -> bytes:
    return hashlib.sha256(capability.encode("ascii", "replace")).digest()


@dataclass
class TranscriptTurn:
    role: Literal["candidate", "interviewer"]
    text: str


@dataclass(eq=False)
class ScreeningSession:
    id: str
    capability_hash: bytes = field(repr=False)
    context: InterviewContext = field(repr=False)
    created: float
    expires: float
    mode: Literal["voice", "text"] = "voice"
    # The latest request that presented this session's capability, for the usage line.
    last_seen: float = 0.0
    # Groups this screening's usage rows on Neon; unrelated to the ID and capability.
    usage_ref: str = field(default_factory=lambda: secrets.token_hex(8))
    state: State = "issued"
    started: float | None = None
    reconnects: int = 0
    # Finished interviewer turns, for the conversation cap.
    turns: int = 0
    # Every turn request, including ones a newer request replaced; a larger safety cap.
    requests: int = 0
    failures: int = 0
    # The newest turn request; an older model stream stops when this moves past it.
    active_turn: int = 0
    # Set while the active model turn runs; a stale value cannot block the session forever.
    in_flight_since: float | None = None
    transcript: list[TranscriptTurn] = field(default_factory=list, repr=False)
    # How the screening ended, for the report: interviewer, time_limit, failure or ended_early.
    end_reason: str | None = None
    # The temporary report, built once after the screening ends and shared by repeat requests.
    report: object | None = field(default=None, repr=False)
    report_task: object | None = field(default=None, repr=False)


class SessionStore:
    def __init__(self, settings, clock: Callable[[], float] = time.monotonic, recorder=None):
        self.settings = settings
        self.clock = clock
        self.recorder = recorder
        self._sessions: dict[str, ScreeningSession] = {}
        self._created: deque[float] = deque()

    def purge(self) -> None:
        now = self.clock()
        for session_id, session in list(self._sessions.items()):
            if now >= session.expires or (
                session.state == "issued" and now - session.created >= ACTIVATION_SECONDS
            ):
                del self._sessions[session_id]
                log_usage(session)
                self._record_deepgram(session)
            elif (
                session.state == "active"
                and session.started is not None
                and now - session.started
                >= self.settings.voice_screening_seconds + OVERRUN_GRACE_SECONDS
            ):
                session.state = "ended"
                session.end_reason = session.end_reason or "time_limit"

    def open_count(self) -> int:
        return sum(session.state != "ended" for session in self._sessions.values())

    def create(
        self, context: InterviewContext, mode: Literal["voice", "text"] = "voice"
    ) -> tuple[ScreeningSession, str]:
        self.purge()
        now = self.clock()
        while self._created and self._created[0] <= now - DAY_SECONDS:
            self._created.popleft()
        if (
            self.open_count() >= self.settings.voice_max_concurrent
            or len(self._sessions) >= MAX_SESSIONS
        ):
            raise VoiceFailure("voice_busy")
        if len(self._created) >= self.settings.voice_sessions_per_day:
            raise VoiceFailure("voice_daily_limit")
        if (
            sum(created > now - HOUR_SECONDS for created in self._created)
            >= self.settings.voice_sessions_per_hour
        ):
            raise VoiceFailure("voice_rate_limited")
        capability = secrets.token_urlsafe(32)
        session = ScreeningSession(
            id=secrets.token_urlsafe(16),
            capability_hash=_hash(capability),
            context=context,
            created=now,
            expires=now + self.settings.voice_session_expiry_seconds,
            mode=mode,
            last_seen=now,
        )
        self._sessions[session.id] = session
        self._created.append(now)
        return session, capability

    def get(self, session_id: str, capability: str) -> ScreeningSession:
        """Unknown, expired and wrong-capability lookups are indistinguishable."""
        self.purge()
        session = self._sessions.get(session_id)
        if session is None or not hmac.compare_digest(_hash(capability), session.capability_hash):
            raise VoiceFailure("screening_not_found")
        session.last_seen = self.clock()
        return session

    def discard(self, session_id: str) -> None:
        # The admission timestamp stays, so failed starts still count towards the hourly limit.
        self._sessions.pop(session_id, None)

    def _record_deepgram(self, session: ScreeningSession) -> None:
        """Estimate a voice call's Deepgram time; Deepgram bills the connection we never see."""
        if (
            self.recorder is None
            or session.mode != "voice"
            or self.settings.voice_mode != "deepgram"
        ):
            return
        self.recorder.add(
            "deepgram",
            "deepgram_session",
            outcome=end_outcome(session),
            provider="deepgram",
            model_id=f"{self.settings.voice_listen_model}+{self.settings.voice_speak_model}",
            seconds=round(session.last_seen - session.created, 1),
            screening_mode=session.mode,
            candidate_kind=session.context.candidate_kind,
            job_id=session.context.job_id,
            screening_ref=session.usage_ref,
            details={
                "estimate": "start_to_last_request",
                "token_grants": 1 + session.reconnects,
                "interviewer_turns": session.turns,
            },
        )

    def remaining_seconds(self, session: ScreeningSession) -> float:
        return max(0.0, session.expires - self.clock())


def end_outcome(session: ScreeningSession) -> str:
    return session.end_reason or ("not_started" if session.state == "issued" else "not_ended")


def log_usage(session: ScreeningSession) -> None:
    """One counts-only line as a session is deleted, for weekly usage checks: no text or IDs."""
    logger.info(
        "Screening usage: %s, %s candidate, %s, %.0f s to last request, %d answers, "
        "%d interviewer turns, %d turn requests, %d reconnects, report %s",
        session.mode,
        session.context.candidate_kind,
        end_outcome(session),
        session.last_seen - session.created,
        sum(turn.role == "candidate" for turn in session.transcript),
        session.turns,
        session.requests,
        session.reconnects,
        "built" if session.report is not None else "none",
    )
