"""Provider registration and tolerant capture of one complete JSON object."""

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.llm import base
from app.llm.base import get_provider, provider_names, register_provider
from app.llm.factory import ai_modes, ensure_ai_configured, model_id
from app.llm.response import extract_text, parse_json_object
from app.pipeline.contracts import ExtractionFailure


class SyntheticProvider:
    name = "synthetic"

    def check(self, settings):
        return None

    def model_id(self, settings):
        return "synthetic-model"

    def structured_method(self, settings):
        return "json_schema"

    def build(self, settings):
        raise AssertionError("Not called in this test")

    def error_code(self, exc):
        return None


def test_bedrock_is_registered_and_mock_stays_an_offline_mode():
    assert "bedrock" in provider_names()
    assert ai_modes()[0] == "mock" and "mock" not in provider_names()
    with pytest.raises(ValueError, match="reserved"):
        register_provider(type("Mock", (SyntheticProvider,), {"name": "mock"})())
    with pytest.raises(KeyError, match="Unknown LLM provider"):
        get_provider("absent")


def test_registering_a_provider_makes_it_selectable_without_other_changes(monkeypatch):
    monkeypatch.setattr(base, "_PROVIDERS", dict(base._PROVIDERS))
    with pytest.raises(ValidationError):
        Settings(ai_mode="synthetic")
    register_provider(SyntheticProvider())
    settings = Settings(ai_mode="synthetic")
    ensure_ai_configured(settings)
    assert model_id(settings) == "synthetic-model"


def test_incomplete_bedrock_settings_fail_before_any_call():
    with pytest.raises(ExtractionFailure, match="provider_configuration_error"):
        ensure_ai_configured(Settings(ai_mode="bedrock", aws_region="ap-southeast-2"))


@pytest.mark.parametrize(
    "text",
    [
        '{"facts": []}',
        '  ```json\n{"facts": []}\n```  ',
        '```\n{"facts": []}\n```',
        'Note {not json} then {"facts": []} and a trailing remark',
        '{"output": {"facts": []}}',
        '{"{"facts": []}',
        '{\n{"facts": []}}',
    ],
)
def test_one_complete_object_is_captured(text):
    assert parse_json_object(text, "facts") == {"facts": []}


@pytest.mark.parametrize(
    "text",
    ['{"facts": [', '{"facts": [{"kind": "skill", "value": {"x": 1}', "[]", "facts: []", ""],
)
def test_partial_or_non_object_output_is_never_completed(text):
    try:
        value = parse_json_object(text, "facts")
    except ValueError:
        return
    # A stray one-key fragment may be captured, but it never becomes a facts result.
    assert "facts" not in value


def test_text_capture_ignores_reasoning_and_tool_blocks():
    content = [
        {"type": "reasoning_content", "reasoning_content": {"text": "private"}},
        {"type": "text", "text": '{"facts":'},
        {"type": "tool_use", "name": "x"},
        {"type": "text", "text": " []}"},
    ]
    assert extract_text(content) == '{"facts": []}'
    assert extract_text(None) == ""
