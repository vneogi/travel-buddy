"""SPEC-25 trip-optional Ask: POST /api/v1/ask (slice 1, backend).

Deterministic templates or refuse. No model call, no GPS, no trip read or
write, no version bump, no quota. A request carrying trip_id is refused with
use_trip_event; the trip composer keeps POST /api/v1/trip/event unchanged.

Trip-only intents (today_tonight, trip_current_next, plan_change) are refused
with a start-a-trip offer. Catalog intents go through the unchanged
AskService.handle_ask, with a venue name matched from the question text in
this route only. No budget is enforced this slice (no model is called);
activation is deferred with the LLM slice. Nothing here logs question text.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, field_validator

from config.regions import REGIONS
from models.schemas import AskResponseEnvelope
from security import ResolvedIdentity, resolve_identity
from services.ask_service import (
    AskIntent,
    AskPath,
    AskResponse,
    AskService,
    AskTelemetry,
    TrustTier,
    classify_ask_intent,
    load_dish_glossary,
)
from services.db_provider import db_service

router = APIRouter(prefix="/api/v1", tags=["ask"])

QUESTION_MAX = 500
VENUE_NAME_MIN = 4
TRIP_ONLY_INTENTS = frozenset()  # R17a sabotage: no trip-only refusal
NO_TRIP_REASON = "no_trip"
NO_TRIP_COPY = (
    "That question is about a trip plan, and there is no trip here yet. "
    "Start a trip to ask about your stops and plans."
)
USE_TRIP_EVENT_COPY = "Questions about a trip go through POST /api/v1/trip/event with its trip_id."


class AskRequest(BaseModel):
    """Closed request: question, geo_region, optional trip_id. Extras are 422."""

    model_config = ConfigDict(extra="forbid")

    question: str
    geo_region: str
    trip_id: Optional[str] = None

    @field_validator("question")
    @classmethod
    def _question(cls, value: str) -> str:
        value = value.strip()
        if not 1 <= len(value) <= QUESTION_MAX:
            raise ValueError("question must be 1 to 500 characters")
        return value

    @field_validator("geo_region")
    @classmethod
    def _region(cls, value: str) -> str:
        if value not in REGIONS:
            raise ValueError("geo_region is not a supported region")
        return value


class AskOnlyResponse(BaseModel):
    """Wraps the same ask_response envelope the trip route returns."""

    model_config = ConfigDict(extra="forbid")

    ask_response: AskResponseEnvelope


def _normalise(text: str) -> str:
    return " ".join(text.split()).casefold()


def match_question_venue(question: str, venues: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The one catalog venue whose name appears as a whole-word phrase.

    Names shorter than VENUE_NAME_MIN are ignored. When one matched name is
    contained in another, the longer one wins. Exactly one venue must remain;
    zero or several return None (never guess between venues).
    """
    asked = _normalise(question)
    hits = []
    for venue in venues:
        name = _normalise(str(venue.get("name") or ""))
        if len(name) < VENUE_NAME_MIN:
            continue
        if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", asked):
            hits.append((name, venue))
    kept = [
        (name, venue)
        for name, venue in hits
        if not any(name != other and name in other for other, _ in hits)
    ]
    if len(kept) != 1:
        return None
    return kept[0][1]


def _envelope(resp: AskResponse) -> AskResponseEnvelope:
    proposal = None
    if resp.proposal:
        proposal = {
            "event_type": resp.proposal.get("event_type", "swap_activity"),
            "target_node_id": resp.proposal.get("target_node_id", ""),
            "summary": resp.proposal.get("summary", ""),
        }
    return AskResponseEnvelope(
        answer=resp.answer,
        tier=resp.tier.value,
        path=resp.path.value,
        intent=resp.intent.value,
        source_ids=list(resp.source_ids),
        source_class=resp.source_class,
        from_cache=resp.from_cache,
        fallback_reason=resp.fallback_reason,
        proposal=proposal,
        food_disclaimer=resp.food_disclaimer,
        what_now=resp.what_now,
    )


@router.post("/ask", response_model=AskOnlyResponse)
async def ask_without_trip(
    request: AskRequest,
    identity: ResolvedIdentity = Depends(resolve_identity),
) -> AskOnlyResponse:
    """Trip-optional Ask. Read only; deterministic; region from the request."""
    if request.trip_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "use_trip_event", "message": USE_TRIP_EVENT_COPY},
        )

    service = AskService(
        llm_service=None,
        db=db_service,
        dish_glossary=load_dish_glossary(request.geo_region),
    )
    intent = classify_ask_intent(request.question)
    if intent in TRIP_ONLY_INTENTS:
        resp = AskResponse(
            answer=NO_TRIP_COPY,
            tier=TrustTier.REFUSE,
            path=AskPath.RETRIEVAL_MISS,
            intent=intent,
            fallback_reason=NO_TRIP_REASON,
        )
        service._emit_telemetry(
            AskTelemetry(
                intent=intent.value,
                path=resp.path.value,
                geo_region=request.geo_region,
                fallback_reason=NO_TRIP_REASON,
            )
        )
        return AskOnlyResponse(ask_response=_envelope(resp))

    venues = db_service.list_venues_for_region(request.geo_region) or []
    venue = match_question_venue(request.question, venues)
    resp = await service.handle_ask(
        question=request.question,
        geo_region=request.geo_region,
        user_id=identity.user_id,
        is_anonymous=identity.identity_kind == "anonymous",
        venue_name=venue.get("name") if venue else None,
        venue_id=venue.get("venue_id") if venue else None,
        llm_key_present=False,
    )
    return AskOnlyResponse(ask_response=_envelope(resp))
