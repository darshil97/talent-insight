"""Stateless availability bonus for temporary uploads; no AI, database or storage."""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.errors import ErrorResponse
from app.ranking import Availability, AvailabilityInput, describe, ranking_score

router = APIRouter(tags=["availability"])


class AvailabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    availability: AvailabilityInput
    match_estimate: float | None = Field(default=None, ge=0, le=100)


class AvailabilityResponse(BaseModel):
    availability: Availability
    ranking_score: float | None


@router.post(
    "/availability", response_model=AvailabilityResponse, responses={422: {"model": ErrorResponse}}
)
async def availability(
    payload: AvailabilityRequest, request: Request, response: Response
) -> AvailabilityResponse:
    # Values arrive in the body, not the URL, and are never logged or stored.
    response.headers["Cache-Control"] = "no-store"
    result = describe(payload.availability, request.app.state.settings)
    return AvailabilityResponse(
        availability=result, ranking_score=ranking_score(payload.match_estimate, result)
    )
