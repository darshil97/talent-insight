"""Availability is logistics, not evidence of fit: a small capped bonus used only for ranking."""

from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import Settings

NoticeStatus = Literal["immediate", "serving_notice", "not_serving"]


class AvailabilityInput(BaseModel):
    """Self-reported notice details; every field empty means not provided."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    status: NoticeStatus | None = None
    last_working_day: date | None = None
    notice_days: int | None = Field(default=None, ge=0, le=365)

    @model_validator(mode="after")
    def fields_match_status(self) -> Self:
        expected = {
            None: (False, False),
            "immediate": (False, False),
            "serving_notice": (True, False),
            "not_serving": (False, True),
        }[self.status]
        if (self.last_working_day is not None, self.notice_days is not None) != expected:
            raise ValueError("Notice fields do not match the availability status")
        return self


class Availability(AvailabilityInput):
    days_to_join: int | None
    bonus: int


def days_to_join(value: AvailabilityInput, today: date) -> int | None:
    if value.status == "immediate":
        return 0
    if value.status == "serving_notice":
        return max(0, (value.last_working_day - today).days)
    if value.status == "not_serving":
        return value.notice_days
    return None


def availability_bonus(days: int | None, tiers: tuple[tuple[int, int], ...]) -> int:
    """Unknown or slow availability earns no bonus; it is never a deduction."""
    if days is None:
        return 0
    return next((bonus for limit, bonus in tiers if days <= limit), 0)


def describe(
    value: AvailabilityInput, settings: Settings, today: date | None = None
) -> Availability:
    days = days_to_join(value, today or date.today())
    return Availability(
        **value.model_dump(),
        days_to_join=days,
        bonus=availability_bonus(days, settings.ranking_availability_tiers),
    )


def ranking_score(match_estimate: float | None, availability: Availability) -> float | None:
    """Match estimate plus the availability bonus; no estimate means nothing to rank by."""
    if match_estimate is None:
        return None
    return round(match_estimate + availability.bonus, 1)
