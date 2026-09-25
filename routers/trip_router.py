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
import uuid
from fastapi import APIRouter, Depends, HTTPException, status

from config.disclaimers import FOOD_DISCLAIMER
from config.interests import (
    ACCEPTED_PARTY_TYPE_IDS,
    INTERESTS,
    PARTY_TYPE_IDS,
    PARTY_TYPES,
    validate_interest_ids,
)
from config.regions import REGIONS
from config.settings import settings
from models.schemas import (
    CreationContext,
    FeaturedStop,
    FeaturedTrip,
    NodeStatus,
    TripState,
    TripSummary,
    TripEventRequest,
    TripEventResponse,
    CreateTripRequest,
    TripPartyIn,
    TripSegment,
    EventType,
)
from config.interests import MAX_AUTO_POPULATED_DAYS, TRIP_SPAN_SANITY_DAYS
from services.catalog_itinerary import (
    InsufficientCatalog,
    advertised_regions,
    compute_max_days_for_region,
    context_for_region,
    nodes_from_catalog,
    range_nodes_from_catalog,
)
from services.corridor_itinerary import (
    InvalidCorridor,
    UnsupportedCorridor,
    advertised_corridors,
    build_corridor_nodes,
    validate_corridor_segments,
)
from config.corridors import CORRIDORS, require_corridor
from services.db_provider import db_service
from services.trip_persistence import (
    CommandPayloadMismatch,
    RerouteLimitReached,
    TripVersionConflict,
)
from services.cache_service import cache_service
from agents.state_machine import state_machine
from security import get_current_user_id, resolve_identity, ResolvedIdentity, require_trip_owner

router = APIRouter(prefix="/api/v1", tags=["trip"])


def _request_command_payload(request) -> dict:
    return request.model_dump(
        mode="json",
        exclude={"user_id", "command_id"},
    )


def _commit_trip_command(**kwargs):
    try:
        return db_service.commit_trip_command(**kwargs)
    except RerouteLimitReached as exc:
        _, _, max_reroutes = db_service.check_reroute_allowed(kwargs["trip_state"].user_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": exc.code,
                "message": (
                    f"You've used all {max_reroutes} daily reroutes. "
                    "Upgrade to Pro for 50 reroutes/day, or wait until tomorrow."
                ),
                "resets_at": "midnight_local",
            },
        ) from exc
    except (TripVersionConflict, CommandPayloadMismatch) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": exc.code, "message": str(exc)},
        ) from exc


def _get_trip_command(**kwargs):
    try:
        return db_service.get_trip_command(**kwargs)
    except CommandPayloadMismatch as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": exc.code, "message": str(exc)},
        ) from exc


def _build_create_response(command) -> dict:
    """Build or replay a create-trip response from a committed command.

    Both the initial response and any idempotent replay call this,
    ensuring the JSON is identical for the same command_id.
    """
    trip = command.trip_state
    meta = command.response_data or {}
    return {
        "trip_id": trip.trip_id,
        "version": trip.version,
        "status": "created",
        "message": meta.get("message", f"Itinerary created with {len(trip.nodes)} activities"),
        "nodes": [n.model_dump(mode="json") for n in trip.nodes],
        "locked_count": meta.get("locked_count", sum(1 for n in trip.nodes if n.is_locked)),
        "party": command.party.model_dump(mode="json") if command.party else None,
    }


def _event_response_from_command(command) -> TripEventResponse:
    response_data = command.response_data or {
        "status": "processed",
        "message": "Command already processed.",
    }
    return TripEventResponse(
        trip_id=command.trip_state.trip_id,
        version=command.trip_state.version,
        updated_nodes=command.trip_state.nodes,
        **response_data,
    )


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
    """Create a catalog-backed itinerary for a city or corridor."""
    user_id = identity.user_id
    db_service.get_or_create_user(user_id, identity.identity_kind)
    if request.command_id:
        prior = _get_trip_command(
            user_id=user_id,
            command_id=request.command_id,
            command_type="create_trip",
            command_payload=_request_command_payload(request),
        )
        if prior is not None:
            return _build_create_response(prior)

    # SPEC-36: Corridor mode vs single-city mode
    if request.segments is not None:
        return await _create_corridor_trip(request, user_id)

    # SPEC-40: range create when end_date is present
    if request.end_date is not None:
        return await _create_range_trip(request, user_id)

    # SPEC-36: single-city mode requires start_date
    if request.start_date is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "invalid_corridor",
                "message": "Single-city mode requires start_date and geo_region.",
                "field": "start_date",
                "supported_corridors": list(CORRIDORS.keys()),
            },
        )

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

    # SPEC-35: Construct 09:00 in the region's IANA timezone, then store UTC.
    from zoneinfo import ZoneInfo

    region_tz = ZoneInfo(REGIONS[geo_region].timezone)
    raw_date = request.start_date
    if raw_date.tzinfo is not None:
        raw_date = raw_date.replace(tzinfo=None)
    start = datetime(
        raw_date.year, raw_date.month, raw_date.day, 9, 0, 0, tzinfo=region_tz
    ).astimezone(timezone.utc)
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
        schedule_basis="region_local_v1",
    )
    party_in = request.party or TripPartyIn(party_type="solo", size=1)
    committed = _commit_trip_command(
        trip_state=trip,
        command_id=request.command_id or str(uuid.uuid4()),
        command_type="create_trip",
        command_payload=_request_command_payload(request),
        expected_version=None,
        party=party_in,
        response_data={
            "message": f"Itinerary created with {len(nodes)} activities",
            "locked_count": sum(1 for n in nodes if n.is_locked),
        },
    )
    return _build_create_response(committed)


async def _create_corridor_trip(request: CreateTripRequest, user_id: str):
    """SPEC-36: Create a multi-city corridor trip."""
    if (
        request.start_date is not None
        or request.geo_region is not None
        or request.end_date is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "invalid_corridor",
                "message": "Corridor mode must not include start_date, end_date, or geo_region.",
                "field": "segments",
                "supported_corridors": list(CORRIDORS.keys()),
            },
        )

    segments = request.segments
    # Infer corridor from segment regions
    seg_regions = tuple(s.geo_region for s in segments)
    corridor = None
    for c in CORRIDORS.values():
        if c.geo_regions == seg_regions:
            corridor = c
            break
    if corridor is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "invalid_corridor",
                "message": f"No corridor matches regions {list(seg_regions)}.",
                "field": "segments",
                "supported_corridors": list(CORRIDORS.keys()),
            },
        )

    try:
        validate_corridor_segments(segments, corridor)
    except InvalidCorridor as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "invalid_corridor",
                "message": str(e),
                "field": "segments",
                "supported_corridors": list(CORRIDORS.keys()),
            },
        )

    try:
        nodes, stored_segments, corridor_warnings = build_corridor_nodes(
            segments, db_service.list_venues_for_region, corridor
        )
    except UnsupportedCorridor as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "unsupported_corridor",
                "message": str(e),
                "field": "segments",
                "supported_corridors": list(CORRIDORS.keys()),
            },
        )

    # B10: if any requested day packed zero venues, fail honestly.
    if corridor_warnings:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "corridor_empty_days",
                "message": (
                    "Some requested dates have no available venues: " + "; ".join(corridor_warnings)
                ),
                "empty_dates": corridor_warnings,
            },
        )

    from services.catalog_itinerary import context_for_region

    first_region = segments[0].geo_region
    trip = TripState(
        user_id=user_id,
        geo_region=first_region,
        current_context=context_for_region(first_region, request.initial_mood),
        nodes=nodes,
        schedule_basis="region_local_v1",
        corridor_id=corridor.corridor_id,
        segments=stored_segments,
    )
    party_in = request.party or TripPartyIn(party_type="solo", size=1)
    committed = _commit_trip_command(
        trip_state=trip,
        command_id=request.command_id or str(uuid.uuid4()),
        command_type="create_trip",
        command_payload=_request_command_payload(request),
        expected_version=None,
        party=party_in,
        response_data={
            "message": f"Corridor itinerary created with {len(nodes)} activities",
            "locked_count": sum(1 for n in nodes if n.is_locked),
        },
    )
    return _build_create_response(committed)


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
        corridor_id=trip.corridor_id,
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
        geo_region=getattr(stop, "geo_region", None) or trip_obj.geo_region,
    )

    return FeaturedTrip(
        trip_id=trip_obj.trip_id,
        geo_region=trip_obj.geo_region,
        starts_at=summary.starts_at,
        ends_at=summary.ends_at,
        is_active=is_active,
        actionable_stop=featured_stop,
        corridor_id=trip_obj.corridor_id,
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
    ready = advertised_regions(db_service.list_venues_for_region)
    max_days_map = {}
    for r in ready:
        md = compute_max_days_for_region(db_service.list_venues_for_region, r)
        if md is not None:
            max_days_map[r] = md
    return {
        "supported_regions": ready,
        "supported_corridors": advertised_corridors(db_service.list_venues_for_region),
        "trips": [_summarize_trip(trip).model_dump(mode="json") for trip in trips],
        "featured_trip": featured.model_dump(mode="json") if featured else None,
        "create_trip_options": {
            "party_types": [{"id": p.id, "label": p.label} for p in PARTY_TYPES],
            "interests": [{"id": i.id, "label": i.label} for i in INTERESTS],
            "max_days_by_region": max_days_map,
            "max_auto_populated_days": MAX_AUTO_POPULATED_DAYS,
            "trip_span_sanity_days": TRIP_SPAN_SANITY_DAYS,
        },
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
    identity: "ResolvedIdentity" = Depends(resolve_identity),
):
    user_id = identity.user_id
    is_anonymous = identity.identity_kind == "anonymous"
    """Process a trip event with the full guardrail stack."""

    # --- Ownership: authorize before doing any work or consuming quota ---
    trip = require_trip_owner(db_service.get_trip(request.trip_id), user_id)
    loaded_version = trip.version
    is_ask = request.event_type == EventType.ASK_INFO
    if request.command_id and not is_ask:
        prior = _get_trip_command(
            user_id=user_id,
            command_id=request.command_id,
            command_type=request.event_type.value,
            command_payload=_request_command_payload(request),
        )
        if prior is not None:
            return _event_response_from_command(prior)

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

    if request.event_type == EventType.SWAP_ACTIVITY:
        target = next(
            (n for n in trip.nodes if n.node_id == request.target_node_id),
            None,
        )
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "target_not_found",
                    "message": "The activity to swap is no longer in this trip.",
                },
            )
        if target.is_locked:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "locked_swap_refused",
                    "message": "Locked bookings cannot be swapped.",
                },
            )
        replacement_id = (request.preferences or {}).get("replacement_venue_id")
        if replacement_id and replacement_id == target.venue_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "same_venue",
                    "message": "Choose a different venue for this swap.",
                },
            )
        if replacement_id:
            replacement = db_service.get_venue_by_id(replacement_id)
            target_region = target.geo_region or trip.geo_region
            if replacement is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "error": "replacement_not_found",
                        "message": "That replacement venue is no longer available.",
                    },
                )
            if replacement.geo_region and target_region and replacement.geo_region != target_region:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": "replacement_wrong_region",
                        "message": "Choose a replacement in the same city.",
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

        # Fail fast before expensive work. The actual quota reservation is part
        # of commit_trip_command, so replays and losing concurrent writes never
        # consume a second reroute.
        allowed, _, max_reroutes = db_service.check_reroute_allowed(user_id)
        if not allowed:
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

    # Bug #3: pass authenticated identity into process_event
    result = await state_machine.process_event(
        trip_state=trip,
        event_type=request.event_type.value,
        message=request.message,
        target_node_id=request.target_node_id,
        preferences=request.preferences,
        user_id=user_id,
        is_anonymous=is_anonymous,
    )

    # B3: booking refused -- return 422 with the refusal message.
    if result.get("booking_refused"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "booking_refused",
                "message": result.get("response", "Booking refused."),
                "schedule_warnings": result.get("schedule_warnings") or [],
            },
        )

    # Bug #2: ASK_INFO does not save_trip or bump updated_at
    updated_trip = result["updated_trip_state"]
    _, remaining, _ = db_service.check_reroute_allowed(user_id)
    if not is_ask:
        updated_trip.updated_at = datetime.now(tz=timezone.utc)
        response_data = TripEventResponse(
            trip_id=request.trip_id,
            version=loaded_version + 1,
            status="processed",
            message=result["response"],
            routing_tier_used=result["routing_tier_used"],
            from_cache=result["from_cache"],
            reroutes_remaining=remaining,
            food_disclaimer=FOOD_DISCLAIMER,
            schedule_warnings=result.get("schedule_warnings") or [],
            ask_response=result.get("ask_response"),
        ).model_dump(
            mode="json",
            exclude={"trip_id", "version", "updated_nodes"},
        )
        committed = _commit_trip_command(
            trip_state=updated_trip,
            command_id=request.command_id or str(uuid.uuid4()),
            command_type=request.event_type.value,
            command_payload=_request_command_payload(request),
            expected_version=(
                request.expected_version if request.expected_version is not None else loaded_version
            ),
            response_data=response_data,
            consume_reroute=request.event_type in structural_events,
        )
        if committed.replayed:
            return _event_response_from_command(committed)
        updated_trip = committed.trip_state
        if committed.response_data is not None:
            remaining = committed.response_data.get(
                "reroutes_remaining",
                remaining,
            )

    db_service.log_event(
        user_id=user_id,
        trip_id=request.trip_id,
        event_type=request.event_type.value,
        routing_tier=result["routing_tier_used"],
        from_cache=result["from_cache"],
    )

    return TripEventResponse(
        trip_id=request.trip_id,
        version=trip.version if is_ask else updated_trip.version,
        status="processed",
        message=result["response"],
        updated_nodes=[] if is_ask else updated_trip.nodes,
        routing_tier_used=result["routing_tier_used"],
        from_cache=result["from_cache"],
        reroutes_remaining=remaining,
        food_disclaimer=FOOD_DISCLAIMER,
        schedule_warnings=result.get("schedule_warnings") or [],
        ask_response=result.get("ask_response"),
    )


# ==============================================================================
# Utility Endpoints
# ==============================================================================

# NOTE: The old `POST /user/{user_id}/upgrade` endpoint was removed. It granted
# Pro with no payment and no auth. Tier upgrades now happen only via verified
# payments (see routers/payment_router.py -- fix #2).


@router.get("/trip/{trip_id}/swap_candidates/{node_id}")
async def swap_candidates(
    trip_id: str,
    node_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Return pre-filtered swap candidates for a target activity.

    Applies the same predicates SWAP_ACTIVITY uses on confirm:
    hours, unified reachability, flight buffer, hotel-return, same geo_region.
    Both in-memory and Supabase paths use the same filtering (R4).
    """
    from services.opening_hours import HoursResult, hours_for_slot
    from services.catalog_itinerary import duration_for as _dur_for, is_swap_eligible_venue
    from agents.state_machine import _is_swap_reachable

    trip = db_service.get_trip(trip_id)
    if trip is None or trip.user_id != user_id:
        raise HTTPException(status_code=404, detail="Trip not found.")
    target = next((n for n in trip.nodes if n.node_id == node_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Node not found.")
    if target.is_locked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Locked bookings cannot be swapped.",
        )

    target_region = target.geo_region or trip.geo_region
    target_idx = trip.nodes.index(target)
    venues_raw = db_service.list_venues_for_region(target_region)

    # Existing node venue_ids to exclude
    existing_ids = {n.venue_id for n in trip.nodes if n.venue_id}

    results = []
    target_slot = getattr(target, "slot_name", None)
    for row in venues_raw:
        vid = str(row.get("venue_id") or "")
        if not vid or vid in existing_ids:
            continue
        # G0-B4: shared eligibility: excludes infrastructure + slot-typed filter.
        if not is_swap_eligible_venue(row, target_slot):
            continue
        # Same filtering as state_machine swap confirm path
        structured = row.get("opening_hours_structured")
        dwell = _dur_for(row)
        hr = hours_for_slot(structured, target.scheduled_start, dwell, target_region)
        if hr == HoursResult.CLOSED:
            continue
        cand_lat = row.get("lat")
        cand_lng = row.get("lng")
        if not _is_swap_reachable(target, cand_lat, cand_lng, dwell, trip.nodes, target_idx):
            continue
        results.append(
            {
                "venue_id": vid,
                "name": row.get("name", ""),
                "category": row.get("category", ""),
                "micro_location": row.get("micro_location", ""),
                "vibe_tags": row.get("vibe_tags") or [],
                "lat": cand_lat,
                "lng": cand_lng,
                "slot_name": target_slot,
            }
        )
    return {"candidates": results}


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
    # SPEC-17 decision 15 + SPEC-14: Flatten each result to the contract
    # Flutter expects.  Never return the nested venue object.  Strip
    # suitable_for (dietary claim).  Derive sponsored_boost_applied from
    # an actual positive ranking contribution on the server -- never from
    # client input.
    flat_results = []
    for r in results:
        v = r.venue
        # Supabase's RPC exposes the pre/post-boost scores but not the private
        # bid. A positive score delta is therefore the cross-backend source of
        # truth that paid placement influenced this result.
        boost_applied = r.final_score > r.similarity_score
        flat_results.append(
            {
                "venue_id": v.venue_id,
                "name": v.name,
                "description": v.description,
                "micro_location": v.micro_location,
                "vibe_tags": v.vibe_tags,
                "distance_km": None,
                "is_sponsored": v.is_sponsored or boost_applied,
                "sponsored_boost_applied": boost_applied,
            }
        )

    return {
        "query": query,
        "results_count": len(flat_results),
        "results": flat_results,
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


async def _create_range_trip(request: CreateTripRequest, user_id: str):
    """SPEC-40: Create a multi-day guided trip with interest scoring."""
    from datetime import date as date_type
    from zoneinfo import ZoneInfo

    if request.start_date is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "missing_start_date",
                "message": "Range create requires start_date.",
            },
        )
    if request.segments is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "invalid_corridor",
                "message": "Range create must not include segments.",
            },
        )

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

    # Parse destination-local dates
    raw_start = request.start_date
    raw_end = request.end_date
    if raw_start.tzinfo is not None:
        raw_start = raw_start.replace(tzinfo=None)
    if raw_end.tzinfo is not None:
        raw_end = raw_end.replace(tzinfo=None)
    start_local = date_type(raw_start.year, raw_start.month, raw_start.day)
    end_local = date_type(raw_end.year, raw_end.month, raw_end.day)

    # Validate: reversed
    if end_local < start_local:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "reversed_dates",
                "message": "end_date must not be before start_date.",
            },
        )

    # Validate: past (in destination timezone, not UTC)
    from zoneinfo import ZoneInfo as _ZI

    _dest_tz = _ZI(REGIONS[geo_region].timezone)
    today = datetime.now(tz=_dest_tz).date()
    if start_local < today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "past_dates",
                "message": "start_date must not be in the past.",
            },
        )

    # Validate: 90-day API sanity bound (SPEC-42)
    num_days = (end_local - start_local).days + 1
    if num_days > TRIP_SPAN_SANITY_DAYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "trip_span_exceeded",
                "message": (
                    f"Trip span {num_days} days exceeds the "
                    f"{TRIP_SPAN_SANITY_DAYS}-day safety limit."
                ),
                "max_span_days": TRIP_SPAN_SANITY_DAYS,
            },
        )

    # Validate party type for guided create
    if request.party and request.party.party_type not in ACCEPTED_PARTY_TYPE_IDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "invalid_party_type",
                "message": f"Unknown party type: {request.party.party_type}",
            },
        )

    # Validate interests
    raw_interests = request.preferences.interest_ids if request.preferences else []
    try:
        interest_ids = validate_interest_ids(raw_interests)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "invalid_interests",
                "message": str(exc),
            },
        )

    # Build nodes -- sparse generation (SPEC-42): populates
    # min(5, calendar_days, feasible_days); never raises InsufficientCatalog.
    nodes = range_nodes_from_catalog(
        geo_region=geo_region,
        start_date_local=start_local.isoformat(),
        end_date_local=end_local.isoformat(),
        rows=db_service.list_venues_for_region(geo_region),
        interest_ids=interest_ids,
    )

    # Build and save trip (atomic: only after all days succeed)
    creation_ctx = CreationContext(
        destination=geo_region,
        start_date_local=start_local.isoformat(),
        end_date_local=end_local.isoformat(),
        interest_ids=interest_ids,
    )
    trip = TripState(
        user_id=user_id,
        geo_region=geo_region,
        current_context=context_for_region(geo_region, request.initial_mood),
        nodes=nodes,
        schedule_basis="region_local_v1",
        creation_context=creation_ctx,
    )
    party_in = request.party or TripPartyIn(party_type="solo", size=1)
    committed = _commit_trip_command(
        trip_state=trip,
        command_id=request.command_id or str(uuid.uuid4()),
        command_type="create_trip",
        command_payload=_request_command_payload(request),
        expected_version=None,
        party=party_in,
        response_data={
            "message": f"Itinerary created with {len(nodes)} activities over {num_days} days",
            "locked_count": sum(1 for n in nodes if n.is_locked),
        },
    )
    return _build_create_response(committed)
