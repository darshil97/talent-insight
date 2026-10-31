"""Metered usage rows: what is recorded and priced, and that recording never blocks or leaks."""

import asyncio
import logging
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError
from test_bedrock_adapter import FakeModel, raw_message
from test_extraction import bedrock_settings
from test_resumes import pdf
from test_screenings import voice_settings

from app import usage
from app.application import create_app
from app.core.logging import configure_logging
from app.llm import invoke
from app.pipeline.contracts import ExtractionFailure
from app.usage import MAX_QUEUED, UsageRecorder
from app.voice.contracts import InterviewContext
from app.voice.sessions import SessionStore

# Loopback, so settings validate without TLS; nothing in these tests connects to it.
DATABASE = "postgresql://user:password@127.0.0.1:5432/talent"
PRICES = (("openai.gpt-oss-120b-1:0", 2.0, 8.0),)


def recorder(**values) -> UsageRecorder:
    return UsageRecorder(bedrock_settings(database_url=DATABASE, **values))


def test_recording_needs_a_database_and_can_be_turned_off():
    assert not UsageRecorder(bedrock_settings()).enabled
    assert not recorder(usage_recording=False).enabled
    assert recorder().enabled


def test_costs_use_configured_prices_and_stay_empty_without_one():
    priced = recorder(usage_token_prices=PRICES, usage_deepgram_minute_price=0.065)
    priced.add(
        "pdf",
        "resume_extraction",
        model_id="openai.gpt-oss-120b-1:0",
        input_tokens=1_000,
        output_tokens=500,
    )
    priced.add("pdf", "resume_extraction", model_id="other-model", input_tokens=1, output_tokens=1)
    priced.add("deepgram", "deepgram_session", seconds=90.0)
    priced.add("pdf", "pdf_parse", pages=2)
    rows = list(priced._queue)
    assert [row["cost_usd"] for row in rows] == [
        Decimal("0.006000"),
        None,
        Decimal("0.097500"),
        None,
    ]
    assert all(row["origin"] in ("local", "render") and row["created_at"] for row in rows)


def test_packaged_prices_cost_both_deployed_models():
    # Render's BEDROCK_MODEL_ID and VOICE_BEDROCK_MODEL_ID must match these IDs exactly.
    priced = recorder()
    priced.add(
        "response_analysis",
        "screening_report",
        model_id="openai.gpt-oss-120b-1:0",
        input_tokens=10_000,
        output_tokens=2_000,
    )
    priced.add(
        "voice_response",
        "interviewer_turn",
        model_id="au.anthropic.claude-haiku-4-5-20251001-v1:0",
        input_tokens=1_200,
        output_tokens=40,
    )
    assert [row["cost_usd"] for row in priced._queue] == [Decimal("0.002781"), Decimal("0.001540")]


def test_the_queue_is_bounded():
    bounded = recorder()
    for _ in range(MAX_QUEUED + 3):
        bounded.add("pdf", "pdf_parse")
    assert (len(bounded._queue), bounded.dropped) == (MAX_QUEUED, 3)


class FakeEngine:
    def __init__(self, error=None):
        self.error = error
        self.batches = []

    @contextmanager
    def begin(self):
        yield self

    def execute(self, statement, rows=None):
        if self.error is not None:
            raise self.error
        if rows is not None:
            self.batches.append(rows)


def test_flush_writes_one_batch_and_keeps_rows_only_while_neon_is_unreachable(caplog):
    batch = recorder()
    batch.add("pdf", "pdf_parse")
    batch.add("pdf", "pdf_parse")
    engine = FakeEngine()
    asyncio.run(batch.flush(engine))
    assert len(engine.batches) == 1 and len(engine.batches[0]) == 2
    assert not batch._queue

    batch.add("pdf", "pdf_parse")
    asyncio.run(batch.flush(FakeEngine(OperationalError("SELECT", {}, Exception("down")))))
    assert len(batch._queue) == 1
    asyncio.run(batch.flush(FakeEngine(IntegrityError("INSERT", {}, Exception("bad")))))
    assert not batch._queue
    assert "Usage rows dropped: 1 (IntegrityError)" in caplog.text
    asyncio.run(batch.flush(None))


# --- what each operation records ---


def bound(**values) -> UsageRecorder:
    usage.capture_model_calls()  # create_app installs this; these tests build no app
    scoped = recorder(**values)
    usage.bind(
        scoped, candidate_kind="upload", job_id="demo_ds", candidate_ref="up_0123456789abcdef"
    )
    return scoped


def test_structured_model_calls_are_read_from_the_invoke_lines(monkeypatch):
    scoped = bound(usage_token_prices=PRICES)
    model = FakeModel(raw_message(content=None, stop="end_turn"))
    monkeypatch.setattr(invoke, "get_chat_model", lambda settings: model)
    settings = bedrock_settings()

    async def call(stage):
        with pytest.raises(ExtractionFailure):
            await invoke.invoke_structured(
                settings,
                stage=stage,
                attempt=2,
                system="s",
                payload="{}",
                schema={},
                output_name="ResumeFacts",
                root_key="facts",
            )

    async def run():
        for stage in ("extraction", "interpretation", "report"):
            await call(stage)

    asyncio.run(run())
    rows = list(scoped._queue)
    assert [(row["category"], row["operation"]) for row in rows] == [
        ("pdf", "resume_extraction"),
        ("pdf", "resume_interpretation"),
        ("response_analysis", "screening_report"),
    ]
    first = rows[0]
    assert (first["provider"], first["model_id"], first["region"]) == (
        "bedrock",
        "openai.gpt-oss-120b-1:0",
        "ap-southeast-2",
    )
    assert (first["input_tokens"], first["output_tokens"], first["attempt"]) == (10, 5, 2)
    assert (first["stop_reason"], first["outcome"], first["cost_usd"]) == (
        "end_turn",
        "ok",
        Decimal("0.000060"),
    )
    assert (first["candidate_kind"], first["job_id"]) == ("upload", "demo_ds")
    assert {row["candidate_ref"] for row in rows} == {"up_0123456789abcdef"}


def test_failed_calls_are_recorded_and_mock_calls_are_not(monkeypatch):
    scoped = bound()

    def broken(settings):
        raise RuntimeError("private detail")

    monkeypatch.setattr(invoke, "get_chat_model", broken)
    settings = bedrock_settings()

    async def call():
        with pytest.raises(ExtractionFailure):
            await invoke.invoke_structured(
                settings,
                stage="extraction",
                attempt=1,
                system="s",
                payload="{}",
                schema={},
                output_name="ResumeFacts",
                root_key="facts",
            )

    asyncio.run(call())
    logging.getLogger("app.llm.invoke").info(
        usage._COMPLETED, "extraction", 1, "mock", "mock", "end_turn", 1, 1, 1.0
    )
    (row,) = scoped._queue
    assert (row["outcome"], row["input_tokens"], row["model_id"]) == (
        "ai_unavailable",
        None,
        "openai.gpt-oss-120b-1:0",
    )


def test_capture_works_when_log_level_hides_info(caplog):
    caplog.set_level(logging.WARNING, logger="app")
    configure_logging("WARNING")
    try:
        scoped = bound()
        logging.getLogger("app.llm.invoke").info(
            usage._COMPLETED, "report", 1, "bedrock", "m", "end_turn", 3, 4, 5.0
        )
        assert len(scoped._queue) == 1
    finally:
        configure_logging("INFO")


def test_pdf_parses_record_no_row(api_request):
    # Parsing runs locally and costs nothing, so only the model calls that follow are recorded.
    app = create_app(bedrock_settings(database_url=DATABASE))
    response = api_request(
        app,
        "POST",
        "/resumes/extract",
        content=pdf(("Page one text " * 20,)),
        headers={"Content-Type": "application/pdf"},
    )
    assert response.status_code == 200
    assert not app.state.usage._queue


CONTEXT = InterviewContext(
    job_id="demo_ds",
    job_title="Senior Data Scientist",
    candidate_kind="demo",
    assessment_available=False,
    topics=[],
    facts=[],
)


def test_voice_sessions_record_an_estimated_deepgram_row_when_deleted():
    settings = voice_settings(
        voice_mode="deepgram",
        deepgram_api_key="dg-key",
        voice_public_api_url="https://api.example.test",
        database_url=DATABASE,
        usage_deepgram_minute_price=0.065,
    )
    now = [1000.0]
    store = SessionStore(settings, clock=lambda: now[0], recorder=UsageRecorder(settings))
    voice, voice_capability = store.create(CONTEXT, "voice", "demo_ds_avery")
    voice.started, voice.state = now[0], "active"
    now[0] += 120
    store.get(voice.id, voice_capability)
    voice.state, voice.end_reason, voice.reconnects = "ended", "interviewer", 1
    now[0] = 1000.0 + settings.voice_session_expiry_seconds
    store.purge()
    text, _ = store.create(CONTEXT, "text")
    text.expires = 0
    store.purge()
    (row,) = store.recorder._queue
    assert (row["category"], row["operation"], row["outcome"]) == (
        "deepgram",
        "deepgram_session",
        "interviewer",
    )
    assert (row["seconds"], row["cost_usd"]) == (120.0, Decimal("0.130000"))
    assert row["model_id"] == "flux-general-en+aura-2-thalia-en"
    assert row["screening_ref"] == voice.usage_ref != voice.id
    assert row["candidate_ref"] == "demo_ds_avery"
    assert row["details"] == {
        "estimate": "start_to_last_request",
        "token_grants": 2,
        "interviewer_turns": 0,
    }


def test_lifespan_writes_queued_rows_on_shutdown(monkeypatch):
    app = create_app(bedrock_settings(database_url=DATABASE))
    written = []

    async def flush(engine):
        written.append(len(app.state.usage._queue))

    monkeypatch.setattr(app.state.usage, "flush", flush)
    monkeypatch.setattr(
        "app.application.create_database_engine",
        lambda url: SimpleNamespace(dispose=lambda: None),
    )
    app.state.usage.add("pdf", "pdf_parse")

    async def run():
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(run())
    assert written == [1]


def test_deepgram_time_runs_to_the_hang_up_when_the_browser_reports_it():
    settings = voice_settings(
        voice_mode="deepgram",
        deepgram_api_key="dg-key",
        voice_public_api_url="https://api.example.test",
        database_url=DATABASE,
        usage_deepgram_minute_price=0.065,
    )
    now = [1000.0]
    store = SessionStore(settings, clock=lambda: now[0], recorder=UsageRecorder(settings))
    voice, capability = store.create(CONTEXT, "voice")
    voice.state, voice.end_reason, voice.call_ended = "ended", "interviewer", 1090.0
    now[0] = 1300.0
    store.get(voice.id, capability)  # a later report request, after the call
    now[0] = 1000.0 + settings.voice_session_expiry_seconds
    store.purge()
    (row,) = store.recorder._queue
    assert (row["seconds"], row["details"]["estimate"]) == (90.0, "start_to_hang_up")
