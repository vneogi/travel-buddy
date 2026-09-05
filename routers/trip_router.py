"""Travel Buddy MVP - Trip Router (FastAPI)

Implements all API endpoints with the 5 guardrail levers:
1. 5-Reroute Throttle
2. Semantic Cache Check
3. Runaway Agent Circuit Breaker
4. Asymmetric Route Switcher
5. Ad-Injection Weight Lever

All user/trip endpoints require a verified identity (see security.py); the
authenticated user_id is the source of truth and trip ownership is enforced.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status

from config.disclaimers import FOOD_DISCLAIMER
from config.regions import REGIONS
from config.settings import settings
from models.schemas import (
    FeaturedStop,
    FeaturedTrip,
    NodeStatus,
    TripState,
    TripSummary,
    TripEventRequest,
    TripEventResponse,
    CreateTripRequest,
    TripPartyIn,
    EventType,
)
from services.catalog_itinerary import (
    InsufficientCatalog,
    advertised_regions,
    context_for_region,
    nodes_from_catalog,
)
from services.db_provider import db_service
from services.cache_service import cache_service
from agents.state_machine import state_machine
from security import get_current_user_id, resolve_identity, ResolvedIdentity, require_trip_owner

router = APIRouter(prefix="/api/v1", tags=["trip"])


# ==============================================================================
# Health & Status Endpoints
# ==============================================================================


@router.get("/health")
async def health_check():
    """Health check endpoint (public)."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
        "geo_fence": settings.geo_fence,
        "venues_loaded": db_service.get_venue_count(),
        "cache_stats": cache_service.get_stats(),
    }


@router.get("/user/status")
async def get_user_status(identity: ResolvedIdentity = Depends(resolve_identity)):
    """Get the authenticated user's tier info and remaining reroutes."""
    user_id = identity.user_id
    user = db_service.get_or_create_user(user_id, identity.identity_kind)
    allowed, remaining, max_reroutes = db_service.check_reroute_allowed(user_id)
    return {
        "user_id": user.user_id,
        "tier": user.tier_status.value,
        "daily_reroutes_used": user.daily_reroute_count,
        "daily_reroutes_remaining": remaining,
        "max_daily_reroutes": max_reroutes,
    }


# ==============================================================================
# Trip Management Endpoints
# ==============================================================================


@router.post("/trip/create")
async def create_trip(
    request: CreateTripRequest,
    identity: ResolvedIdentity = Depends(resolve_identity),
):
    """Create a catalog-backed one-day itinerary for a supported city."""
    user_id = identity.user_id
    db_service.get_or_create_user(user_id, identity.identity_kind)
    ready = advertised_regions(db_service.list_venues_for_region)
    geo_region = request.geo_region or (ready[0] if ready else None)
    if geo_region not in REGIONS or geo_region not in ready:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "unsupported_region",
                "message": (
                    f"Travel Buddy is not ready for {request.geo_region or geo_region} yet."
                ),
                "supported_regions": ready,
            },
        )

    start = request.start_date
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    else:
        start = start.astimezone(timezone.utc)
    start = start.replace(hour=9, minute=0, second=0)
    try:
        nodes = nodes_from_catalog(
            geo_region=geo_region,
            start=start,
            rows=db_service.list_venues_for_region(geo_region),
        )
    except InsufficientCatalog:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "unsupported_region",
                "message": f"Travel Buddy is not ready for {geo_region} yet.",
                "supported_regions": ready,
            },
        )

    trip = TripState(
        user_id=user_id,
        geo_region=geo_region,
        current_context=context_for_region(geo_region, request.initial_mood),
        nodes=nodes,
    )
    db_service.save_trip(trip)

    # SPEC-03: persist party (defaults to solo if absent)
    party_in = request.party or TripPartyIn(party_type="solo", size=1)
    party = db_service.save_trip_party(trip.trip_id, party_in)

    return {
        "trip_id": trip.trip_id,
        "status": "created",
        "message": f"Itinerary created with {len(nodes)} activities",
        "nodes": [n.model_dump(mode="json") for n in nodes],
        "locked_count": sum(1 for n in nodes if n.is_locked),
        "party": party.model_dump(mode="json"),
    }


def _summarize_trip(trip: TripState) -> TripSummary:
    starts_at = min((node.scheduled_start for node in trip.nodes), default=None)
    ends_at = max(
        (node.scheduled_start + timedelta(minutes=node.duration_minutes) for node in trip.nodes),
        default=None,
    )
    return TripSummary(
        trip_id=trip.trip_id,
        geo_region=trip.geo_region,
        starts_at=starts_at,
        ends_at=ends_at,
        node_count=len(trip.nodes),
        booking_count=sum(node.node_kind == "booking" for node in trip.nodes),
        updated_at=trip.updated_at,
    )


def _as_utc(value: datetime) -> datetime:
    """Normalize API datetimes for ordering without changing the wire value."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _featured_trip(trips: list[TripState], *, now: datetime | None = None) -> FeaturedTrip | None:
    """Pick the current trip, or the earliest upcoming trip.

    The server does not continuously stamp ``NodeStatus.ACTIVE``. Time windows,
    not that enum value, therefore determine whether a trip or stop is current.
    """
    current_time = _as_utc(now or datetime.now(tz=timezone.utc))
    candidates = []
    for trip in trips:
        summary = _summarize_trip(trip)
        actionable = sorted(
            (
                node
                for node in trip.nodes
                if node.status not in {NodeStatus.SKIPPED, NodeStatus.COMPLETED}
                and _as_utc(node.scheduled_start + timedelta(minutes=node.duration_minutes))
                > current_time
            ),
            key=lambda node: _as_utc(node.scheduled_start),
        )
        if actionable:
            candidates.append((trip, summary, actionable))

    active = [
        candidate
        for candidate in candidates
        if candidate[1].starts_at is not None
        and candidate[1].ends_at is not None
        and _as_utc(candidate[1].starts_at) <= current_time < _as_utc(candidate[1].ends_at)
    ]
    upcoming = [
        candidate
        for candidate in candidates
        if candidate[1].starts_at is not None and _as_utc(candidate[1].starts_at) > current_time
    ]
    chosen = (
        max(active, key=lambda candidate: _as_utc(candidate[1].starts_at))
        if active
        else min(upcoming, key=lambda candidate: _as_utc(candidate[1].starts_at))
        if upcoming
        else None
    )
    if chosen is None:
        return None

    trip_obj, summary, actionable = chosen
    is_active = chosen in active
    stop = actionable[0]
    featured_stop = FeaturedStop(
        node_id=stop.node_id,
        venue_id=stop.venue_id,
        venue_name=stop.venue_name,
        scheduled_start=stop.scheduled_start,
        status=stop.status,
    )

    return FeaturedTrip(
        trip_id=trip_obj.trip_id,
        geo_region=trip_obj.geo_region,
        starts_at=summary.starts_at,
        ends_at=summary.ends_at,
        is_active=is_active,
        actionable_stop=featured_stop,
    )


@router.get("/trips")
async def list_trips(user_id: str = Depends(get_current_user_id)):
    """Return the caller's trips as a lightweight home projection.

    SPEC-26: includes an optional featured_trip -- the currently active
    trip or the earliest upcoming one, with its actionable stop.
    Never includes state_json or a full node list.
    """
    trips = sorted(
        db_service.get_active_trips(user_id),
        key=lambda trip: trip.updated_at,
        reverse=True,
    )
    featured = _featured_trip(trips)
    return {
        "supported_regions": advertised_regions(db_service.list_venues_for_region),
        "trips": [_summarize_trip(trip).model_dump(mode="json") for trip in trips],
        "featured_trip": featured.model_dump(mode="json") if featured else None,
    }


@router.get("/trip/{trip_id}")
async def get_trip(trip_id: str, user_id: str = Depends(get_current_user_id)):
    """Get the current state of a trip the caller owns."""
    trip = require_trip_owner(db_service.get_trip(trip_id), user_id)
    result = trip.model_dump(mode="json")
    # SPEC-03: include party so client can display AudienceBadge
    party = db_service.get_trip_party(trip_id)
    if party:
        result["party"] = party.model_dump(mode="json")
    return result


# ==============================================================================
# Main Event Processing Endpoint (with all 5 guardrails)
# ==============================================================================


@router.post("/trip/event", response_model=TripEventResponse)
async def process_trip_event(
    request: TripEventRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Process a trip event with the full guardrail stack."""

    # --- Ownership: authorize before doing any work or consuming quota ---
    trip = require_trip_owner(db_service.get_trip(request.trip_id), user_id)

    # --- SPEC-10: Booking mutations (no quota, no LLM) ---
    booking_mutation_events = {EventType.EDIT_BOOKING, EventType.DELETE_BOOKING}
    if request.event_type in booking_mutation_events:
        if not request.target_node_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "missing_target_node_id",
                    "message": "edit_booking and delete_booking require target_node_id.",
                },
            )
        target = next(
            (n for n in trip.nodes if n.node_id == request.target_node_id),
            None,
        )
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "target_not_found",
                    "message": f"No node with id '{request.target_node_id}' in this trip.",
                },
            )
        if target.node_kind != "booking":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "target_not_a_booking",
                    "message": (
                        f"'{target.venue_name}' is not a booking "
                        "(node_kind='{target.node_kind}'). "
                        "Use cancel_activity for activities."
                    ),
                },
            )

    # --- LEVER 1: Reroute Throttle (keyed on the authenticated user) ---
    structural_events = {
        EventType.CANCEL_ACTIVITY,
        EventType.SWAP_ACTIVITY,
        EventType.ADD_ACTIVITY,
        EventType.REROUTE,
        EventType.CHANGE_MOOD,
        EventType.WEATHER_ALERT,
    }

    if request.event_type in structural_events:
        # SPEC-29 D6: Locked cancel refusal must not consume quota.
        # Validate target before reserving for CANCEL_ACTIVITY.
        if request.event_type == EventType.CANCEL_ACTIVITY and request.target_node_id:
            target = next(
                (n for n in trip.nodes if n.node_id == request.target_node_id),
                None,
            )
            if target and target.is_locked:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": "locked_cancel_refused",
                        "message": (
                            f"'{target.venue_name}' is a locked booking and "
                            "cannot be canceled. Unlock it first if you need "
                            "to remove it."
                        ),
                    },
                )

        # Atomic reserve -- closes the check-then-increment race. Structural
        # events are always HEAVY and never served from cache, so reserving
        # up front never over-charges a cache hit.
        if db_service.consume_reroute(user_id) is None:
            _, _, max_reroutes = db_service.check_reroute_allowed(user_id)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "daily_reroute_limit_reached",
                    "message": (
                        f"You've used all {max_reroutes} daily reroutes. "
                        "Upgrade to Pro for 50 reroutes/day, or wait until tomorrow."
                    ),
                    "resets_at": "midnight_local",
                },
            )

    # Levers 2-5 are handled inside the state machine / router agent / search.
    result = await state_machine.process_event(
        trip_state=trip,
        event_type=request.event_type.value,
        message=request.message,
        target_node_id=request.target_node_id,
        preferences=request.preferences,
    )

    updated_trip = result["updated_trip_state"]
    updated_trip.updated_at = datetime.now(tz=timezone.utc)
    db_service.save_trip(updated_trip)

    db_service.log_event(
        user_id=user_id,
        trip_id=request.trip_id,
        event_type=request.event_type.value,
        routing_tier=result["routing_tier_used"],
        from_cache=result["from_cache"],
    )

    _, remaining, _ = db_service.check_reroute_allowed(user_id)

    return TripEventResponse(
        trip_id=request.trip_id,
        status="processed",
        message=result["response"],
        updated_nodes=updated_trip.nodes,
        routing_tier_used=result["routing_tier_used"],
        from_cache=result["from_cache"],
        reroutes_remaining=remaining,
        food_disclaimer=FOOD_DISCLAIMER,
    )


# ==============================================================================
# Utility Endpoints
# ==============================================================================

# NOTE: The old `POST /user/{user_id}/upgrade` endpoint was removed. It granted
# Pro with no payment and no auth. Tier upgrades now happen only via verified
# payments (see routers/payment_router.py -- fix #2).


@router.get("/venues/search")
async def search_venues(
    query: str,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    trip_id: Optional[str] = None,
    radius_km: float = 15.0,
    top_k: int = 5,
    user_id: str = Depends(get_current_user_id),
):
    """Search venues using hybrid RAG search.

    SPEC-34: Coordinates resolve in priority order:
    1. Explicit lat/lng params (client already resolved from trip context).
    2. Trip context coords (trip_id -> current_context.location_lat/lng).
    3. Region defaults from config/regions.py (trip_id -> geo_region).
    4. Refuse with 422 -- never silently default to Dubai.
    """
    resolved_lat, resolved_lng = lat, lng

    if resolved_lat is None or resolved_lng is None:
        if trip_id:
            trip = db_service.get_trip(trip_id)
            if trip and trip.user_id == user_id:
                ctx = trip.current_context
                resolved_lat = ctx.location_lat
                resolved_lng = ctx.location_lng
                # If context coords are still the schema default (Dubai)
                # but the trip is not Dubai, use region defaults instead.
                if (
                    resolved_lat == 25.1972
                    and resolved_lng == 55.2744
                    and trip.geo_region != "dubai_uae"
                ):
                    region = REGIONS.get(trip.geo_region)
                    if region:
                        resolved_lat = region.default_lat
                        resolved_lng = region.default_lng
                    else:
                        resolved_lat, resolved_lng = None, None

    if resolved_lat is None or resolved_lng is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "missing_coordinates",
                "message": (
                    "Cannot search venues without location. "
                    "Pass lat/lng or trip_id with a known region."
                ),
            },
        )

    results = db_service.hybrid_venue_search(
        query=query,
        user_lat=resolved_lat,
        user_lng=resolved_lng,
        radius_km=radius_km,
        top_k=top_k,
    )
    # SPEC-14: strip dietary suitability claims; add food disclaimer.
    sanitized = []
    for r in results:
        d = r.model_dump(mode="json")
        # suitable_for must never appear in API responses as a claim.
        venue = d.get("venue", {})
        venue.pop("suitable_for", None)
        for dish in venue.get("dishes", []):
            dish.pop("suitable_for", None)
        sanitized.append(d)

    return {
        "query": query,
        "results_count": len(sanitized),
        "results": sanitized,
        "food_disclaimer": FOOD_DISCLAIMER,
    }


@router.get("/stats")
async def get_stats(user_id: str = Depends(get_current_user_id)):
    """Get system statistics (requires auth -- exposes internal analytics)."""
    return {
        "cache": cache_service.get_stats(),
        "events": db_service.get_event_stats(),
        "venues_loaded": db_service.get_venue_count(),
    }
