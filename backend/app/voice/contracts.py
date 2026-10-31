"""Voice screening contracts; the server owns consent wording, context and limits."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.pipeline.contracts import Assessment, Category, FactKind, Status

NOTICE_VERSION = "2026-10-27"
NOTICE_TEXT = (
    "This screening is a short voice conversation with an AI assistant about the role's "
    "job-related requirements. Your microphone audio is sent to Deepgram for speech "
    "recognition, and the conversation text is processed by our backend and Amazon Bedrock "
    "to choose the next question. The AI does not score you or make any decision: a human "
    "recruiter reviews the conversation and decides next steps. The conversation is kept only "
    "temporarily in server memory. You can stop at any time, and you can use the text option "
    "instead of your voice."
)
Capability = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{43,64}$")]
CandidateId = Annotated[str, StringConstraints(pattern=r"^demo_[a-z0-9_]+$", max_length=64)]
MAX_CONTEXT_CHARACTERS = 32_768


class VoiceFailure(Exception):
    """A safe public error code; never carries capabilities, tokens or transcript text."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class Consent(StrictInput):
    audio_capture: bool
    ai_processing: bool
    notice_version: str = Field(max_length=32)


class DemoCandidateRef(StrictInput):
    kind: Literal["demo"]
    candidate_id: CandidateId


class UploadCandidateRef(StrictInput):
    kind: Literal["upload"]
    context: str = Field(min_length=1, max_length=MAX_CONTEXT_CHARACTERS)


class ScreeningRequest(StrictInput):
    job_id: Annotated[str, StringConstraints(pattern=r"^demo_[a-z0-9_]+$", max_length=64)]
    candidate: Annotated[DemoCandidateRef | UploadCandidateRef, Field(discriminator="kind")]
    consent: Consent
    # Text needs no microphone, Deepgram token or public backend URL.
    mode: Literal["voice", "text"] = "voice"
    # The Cloudflare Turnstile token; required only when the bot check is configured.
    bot_check_token: Annotated[str, StringConstraints(pattern=r"^[\x21-\x7e]{1,2048}$")] | None = (
        None
    )


class CapabilityRequest(StrictInput):
    capability: Capability


class MessageRequest(StrictInput):
    capability: Capability
    text: Annotated[str, StringConstraints(min_length=1, max_length=2000, pattern=r"\S")]


class MessageReply(BaseModel):
    reply: str
    ended: bool


class Notice(BaseModel):
    notice_version: str
    text: str
    screening_minutes: int
    voice_available: bool
    text_available: bool
    # The public Turnstile site key when a bot check must pass before a screening starts.
    bot_check_site_key: str | None = None


class ScreeningStart(BaseModel):
    session_id: str
    capability: str
    mode: Literal["voice", "text"]
    expires_at: datetime
    greeting: str
    screening_seconds: int
    max_turns: int
    # Voice only; null for text screenings.
    agent_url: str | None
    deepgram_token: str | None
    token_expires_in: int | None
    settings: dict | None


class TokenGrant(BaseModel):
    deepgram_token: str
    token_expires_in: int


class ScreeningState(BaseModel):
    session_id: str
    state: Literal["issued", "active", "ended"]


class ContextFact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: FactKind
    value: str = Field(min_length=1, max_length=200)


class ContextJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    requirement_id: str = Field(min_length=1, max_length=64)
    status: Status


class Topic(BaseModel):
    requirement_id: str
    category: Category
    description: str
    status: Status
    question: str | None


class InterviewContext(BaseModel):
    """What the interviewer may know: job topics and short verified resume phrases, no names."""

    job_id: str
    job_title: str
    candidate_kind: Literal["demo", "upload"]
    assessment_available: bool
    topics: list[Topic]
    facts: list[ContextFact]


class UploadAssessment(Assessment):
    """A temporary upload assessment plus signed context for starting a screening."""

    screening_context: str | None = None
