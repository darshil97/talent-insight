"""Availability is a small, capped ranking aid; unknown is never a deduction."""

import logging
from datetime import date

import pytest
from pydantic import ValidationError

from app.application import create_app
from app.config import Settings
from app.ranking import (
    AvailabilityInput,
    availability_bonus,
    days_to_join,
    describe,
    ranking_score,
)

TODAY = date(2026, 10, 27)
TIERS = Settings().ranking_availability_tiers


@pytest.mark.parametrize(
    "days,bonus",
    [(None, 0), (0, 5), (15, 5), (16, 4), (30, 4), (45, 3), (60, 2), (61, 1), (90, 1), (91, 0)],
)
def test_bonus_tiers_are_small_and_unknown_earns_nothing(days, bonus):
    assert availability_bonus(days, TIERS) == bonus


@pytest.mark.parametrize(
    "value,days",
    [
        ({}, None),
        ({"status": "immediate"}, 0),
        ({"status": "serving_notice", "last_working_day": "2026-11-16"}, 20),
        ({"status": "serving_notice", "last_working_day": "2026-10-01"}, 0),
        ({"status": "not_serving", "notice_days": 60}, 60),
    ],
)
def test_days_to_join_follow_the_status(value, days):
    assert days_to_join(AvailabilityInput.model_validate(value), TODAY) == days


@pytest.mark.parametrize(
    "value",
    [
        {"status": "serving_notice"},
        {"status": "serving_notice", "notice_days": 30},
        {"status": "not_serving"},
        {"status": "not_serving", "notice_days": 366},
        {"status": "not_serving", "notice_days": -1},
        {"status": "immediate", "notice_days": 0},
        {"last_working_day": "2026-11-01"},
        {"status": "on_leave"},
        {"status": "immediate", "extra": True},
    ],
)
def test_inconsistent_notice_details_are_rejected(value):
    with pytest.raises(ValidationError):
        AvailabilityInput.model_validate(value)


def test_ranking_adds_the_bonus_to_the_estimate_only():
    fast = describe(AvailabilityInput(status="immediate"), Settings(), TODAY)
    unknown = describe(AvailabilityInput(), Settings(), TODAY)
    assert ranking_score(80.0, fast) == 85.0
    assert ranking_score(80.0, unknown) == 80.0
    assert ranking_score(None, fast) is None


@pytest.mark.parametrize(
    "values",
    [
        {"ranking_availability_tiers": ((30, 4), (15, 5))},
        {"ranking_availability_tiers": ((15, 3), (30, 4))},
        {"ranking_availability_tiers": ((15, 11),)},
        {"ranking_availability_tiers": ((400, 1),)},
        {"match_credit_transferable": 0.4, "match_credit_partial": 0.5},
        {"match_credit_transferable": 1.0},
        {"match_credit_partial": 0},
    ],
)
def test_unsafe_ranking_and_credit_settings_are_rejected(values):
    with pytest.raises(ValidationError):
        Settings(**values)


def test_tiers_and_credits_are_configurable_from_the_environment(monkeypatch):
    monkeypatch.setenv("RANKING_AVAILABILITY_TIERS", "[[20, 3], [40, 1]]")
    monkeypatch.setenv("MATCH_CREDIT_TRANSFERABLE", "0.8")
    settings = Settings()
    assert settings.ranking_availability_tiers == ((20, 3), (40, 1))
    assert settings.match_credit_transferable == 0.8


def test_availability_endpoint_is_stateless_no_store_and_never_logs_values(api_request, caplog):
    caplog.set_level(logging.INFO, logger="app")
    app = create_app(Settings())
    response = api_request(
        app,
        "POST",
        "/availability",
        json={
            "availability": {"status": "not_serving", "notice_days": 28},
            "match_estimate": 70,
        },
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["availability"] == {
        "status": "not_serving",
        "last_working_day": None,
        "notice_days": 28,
        "days_to_join": 28,
        "bonus": 4,
    }
    assert body["ranking_score"] == 74.0
    assert "not_serving" not in caplog.text and "notice" not in caplog.text
    missing = api_request(app, "POST", "/availability", json={"availability": {}})
    assert missing.json() == {
        "availability": {
            "status": None,
            "last_working_day": None,
            "notice_days": None,
            "days_to_join": None,
            "bonus": 0,
        },
        "ranking_score": None,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"availability": {"status": "serving_notice"}},
        {"availability": {}, "match_estimate": 101},
        {"availability": {}, "candidate_name": "x"},
    ],
)
def test_availability_endpoint_rejects_invalid_details_safely(api_request, payload):
    response = api_request(create_app(Settings()), "POST", "/availability", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
