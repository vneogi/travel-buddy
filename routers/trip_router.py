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

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status

from config.settings import settings
from models.schemas import (
    TripState,
    TripNode,
    TripEventRequest,
    TripEventResponse,
    CreateTripRequest,
    CurrentContext,
    EventType,
)
from services.database_service import db_service
from services.cache_service import cache_service
from agents.state_machine import state_machine
from security import get_current_user_id, require_trip_owner

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
async def get_user_status(user_id: str = Depends(get_current_user_id)):
    """Get the authenticated user's tier info and remaining reroutes."""
    user = db_service.get_or_create_user(user_id)
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
    user_id: str = Depends(get_current_user_id),
):
    """Create a new trip with a sample Dubai itinerary for the caller."""
    db_service.get_or_create_user(user_id)

    start = request.start_date.replace(hour=9, minute=0, second=0)
    nodes = [
        TripNode(
            venue_name="Dubai Museum (Al Fahidi Fort)",
            scheduled_start=start,
            duration_minutes=90,
            micro_location="Al Fahidi",
            vibe_tags=["cultural", "authentic", "historical"],
            lat=25.2637,
            lng=55.2972,
        ),
        TripNode(
            venue_name="XVA Art Gallery & Cafe",
            scheduled_start=start + timedelta(hours=2),
            duration_minutes=60,
            micro_location="Al Fahidi",
            vibe_tags=["artistic", "leisurely", "premium_interiors"],
            lat=25.2633,
            lng=55.2975,
        ),
        TripNode(
            venue_name="La Petite Maison (DIFC)",
            scheduled_start=start + timedelta(hours=3, minutes=30),
            duration_minutes=90,
            is_locked=True,  # Locked reservation!
            micro_location="DIFC",
            vibe_tags=["premium_interiors", "leisurely", "executive"],
            lat=25.2100,
            lng=55.2800,
        ),
        TripNode(
            venue_name="Alserkal Avenue Galleries",
            scheduled_start=start + timedelta(hours=5, minutes=30),
            duration_minutes=120,
            micro_location="Al Quoz",
            vibe_tags=["artistic", "authentic", "independent"],
            lat=25.1436,
            lng=55.2250,
        ),
        TripNode(
            venue_name="Drift Beach Dubai",
            scheduled_start=start + timedelta(hours=8),
            duration_minutes=180,
            micro_location="Jumeirah",
            vibe_tags=["leisurely", "premium_interiors", "energetic"],
            lat=25.2103,
            lng=55.2490,
        ),
    ]

    trip = TripState(
        user_id=user_id,
        current_context=CurrentContext(mood=request.initial_mood or "exploratory"),
        nodes=nodes,
    )
    db_service.save_trip(trip)

    return {
        "trip_id": trip.trip_id,
        "status": "created",
        "message": f"Dubai itinerary created with {len(nodes)} activities",
        "nodes": [n.model_dump(mode="json") for n in nodes],
        "locked_count": sum(1 for n in nodes if n.is_locked),
    }


@router.get("/trip/{trip_id}")
async def get_trip(trip_id: str, user_id: str = Depends(get_current_user_id)):
    """Get the current state of a trip the caller owns."""
    trip = require_trip_owner(db_service.get_trip(trip_id), user_id)
    return trip.model_dump(mode="json")


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
    )


# ==============================================================================
# Utility Endpoints
# ==============================================================================

# NOTE: The old `POST /user/{user_id}/upgrade` endpoint was removed. It granted
# Pro with no payment and no auth. Tier upgrades now happen only via verified
# payments (see routers/payment_router.py — fix #2).

@router.get("/venues/search")
async def search_venues(
    query: str,
    lat: float = 25.1972,
    lng: float = 55.2744,
    radius_km: float = 15.0,
    top_k: int = 5,
    user_id: str = Depends(get_current_user_id),
):
    """Search venues using hybrid RAG search."""
    results = db_service.hybrid_venue_search(
        query=query,
        user_lat=lat,
        user_lng=lng,
        radius_km=radius_km,
        top_k=top_k,
    )
    return {
        "query": query,
        "results_count": len(results),
        "results": [r.model_dump(mode="json") for r in results],
    }


@router.get("/stats")
async def get_stats(user_id: str = Depends(get_current_user_id)):
    """Get system statistics (requires auth — exposes internal analytics)."""
    return {
        "cache": cache_service.get_stats(),
        "events": db_service.get_event_stats(),
        "venues_loaded": db_service.get_venue_count(),
    }
