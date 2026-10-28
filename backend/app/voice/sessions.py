"""Per-process screening sessions: opaque IDs, hashed capabilities, expiry and admission.

State is memory only. A restart drops every session, and several API processes would each
apply their own limits; this is a single-process safeguard, not a distributed quota.
"""

import hashlib
import hmac
import secrets
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from app.voice.contracts import InterviewContext, VoiceFailure

MAX_SESSIONS = 64
# An issued session that never reaches the interviewer stops holding a slot after this.
ACTIVATION_SECONDS = 180
# An active session whose client keeps talking past the limit stops counting as open.
OVERRUN_GRACE_SECONDS = 60
MAX_TRANSCRIPT_TURNS = 120
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
    state: State = "issued"
    started: float | None = None
    reconnects: int = 0
    turns: int = 0
    failures: int = 0
    # Set while a model turn runs; a stale value cannot block the session forever.
    in_flight_since: float | None = None
    transcript: list[TranscriptTurn] = field(default_factory=list, repr=False)


class SessionStore:
    def __init__(self, settings, clock: Callable[[], float] = time.monotonic):
        self.settings = settings
        self.clock = clock
        self._sessions: dict[str, ScreeningSession] = {}
        self._created: deque[float] = deque()

    def purge(self) -> None:
        now = self.clock()
        for session_id, session in list(self._sessions.items()):
            if now >= session.expires or (
                session.state == "issued" and now - session.created >= ACTIVATION_SECONDS
            ):
                del self._sessions[session_id]
            elif (
                session.state == "active"
                and session.started is not None
                and now - session.started
                >= self.settings.voice_screening_seconds + OVERRUN_GRACE_SECONDS
            ):
                session.state = "ended"

    def open_count(self) -> int:
        return sum(session.state != "ended" for session in self._sessions.values())

    def create(self, context: InterviewContext) -> tuple[ScreeningSession, str]:
        self.purge()
        now = self.clock()
        while self._created and self._created[0] <= now - 3600:
            self._created.popleft()
        if (
            self.open_count() >= self.settings.voice_max_concurrent
            or len(self._sessions) >= MAX_SESSIONS
        ):
            raise VoiceFailure("voice_busy")
        if len(self._created) >= self.settings.voice_sessions_per_hour:
            raise VoiceFailure("voice_rate_limited")
        capability = secrets.token_urlsafe(32)
        session = ScreeningSession(
            id=secrets.token_urlsafe(16),
            capability_hash=_hash(capability),
            context=context,
            created=now,
            expires=now + self.settings.voice_session_expiry_seconds,
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
        return session

    def discard(self, session_id: str) -> None:
        # The admission timestamp stays, so failed starts still count towards the hourly limit.
        self._sessions.pop(session_id, None)

    def remaining_seconds(self, session: ScreeningSession) -> float:
        return max(0.0, session.expires - self.clock())
