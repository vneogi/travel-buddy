"""Travel Buddy MVP - Trip Router (FastAPI)

Implements all API endpoints with the 5 guardrail levers:
1. 5-Reroute Throttle
2. Semantic Cache Check
3. Runaway Agent Circuit Breaker
4. Asymmetric Route Switcher
5. Ad-Injection Weight Lever

Endpoints:
  POST /api/v1/trip/create - Create a new trip
  POST /api/v1/trip/event  - Process a trip event (main endpoint)
  GET  /api/v1/trip/{trip_id} - Get trip state
  GET  /api/v1/user/{user_id}/status - Get user tier info
  GET  /api/v1/health - Health check
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from config.settings import settings
from models.schemas import (
    TripState,
    TripNode,
    TripEventRequest,
    TripEventResponse,
    CreateTripRequest,
    CurrentContext,
    ExecutionControl,
    NodeStatus,
    EventType,
)
from services.database_service import db_service
from services.cache_service import cache_service
from agents.state_machine import state_machine

router = APIRouter(prefix="/api/v1", tags=["trip"])


# ==============================================================================
# Health & Status Endpoints
# ==============================================================================

@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
        "geo_fence": settings.geo_fence,
        "venues_loaded": db_service.get_venue_count(),
        "cache_stats": cache_service.get_stats(),
    }


@router.get("/user/{user_id}/status")
async def get_user_status(user_id: str):
    """Get user tier information and remaining reroutes."""
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
async def create_trip(request: CreateTripRequest):
    """Create a new trip with a sample Dubai itinerary."""
    # Ensure user exists
    db_service.get_or_create_user(request.user_id)

    # Generate a sample Dubai itinerary
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
        user_id=request.user_id,
        current_context=CurrentContext(
            mood=request.initial_mood or "exploratory"
        ),
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
async def get_trip(trip_id: str):
    """Get the current state of a trip."""
    trip = db_service.get_trip(trip_id)
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip {trip_id} not found",
        )
    return trip.model_dump(mode="json")


# ==============================================================================
# Main Event Processing Endpoint (with all 5 guardrails)
# ==============================================================================

@router.post("/trip/event", response_model=TripEventResponse)
async def process_trip_event(request: TripEventRequest):
    """Process a trip event with full guardrail stack.

    Implements all 5 BRD levers in order:
    1. Reroute Throttle (free tier limit)
    2. Semantic Cache Check
    3. Circuit Breaker (handled in state machine)
    4. Asymmetric Routing (handled in router agent)
    5. Ad-Injection (handled in hybrid search)
    """

    # --- LEVER 1: Reroute Throttle ---
    structural_events = {
        EventType.CANCEL_ACTIVITY,
        EventType.SWAP_ACTIVITY,
        EventType.ADD_ACTIVITY,
        EventType.REROUTE,
        EventType.CHANGE_MOOD,
        EventType.WEATHER_ALERT,
    }

    if request.event_type in structural_events:
        allowed, remaining, max_reroutes = db_service.check_reroute_allowed(
            request.user_id
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "daily_reroute_limit_reached",
                    "message": (
                        f"You've used all {max_reroutes} daily reroutes. "
                        "Upgrade to Pro for 50 reroutes/day, or wait until tomorrow."
                    ),
                    "upgrade_url": "/api/v1/user/upgrade",
                    "resets_at": "midnight_local",
                },
            )

    # --- Retrieve Trip State ---
    trip = db_service.get_trip(request.trip_id)
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip {request.trip_id} not found",
        )

    # --- LEVER 2: Semantic Cache (handled inside state machine for light requests) ---
    # --- LEVER 3: Circuit Breaker (handled inside state machine) ---
    # --- LEVER 4: Asymmetric Routing (handled inside router agent) ---
    # --- LEVER 5: Ad-Injection (handled inside hybrid search) ---

    # Process through the state machine
    result = state_machine.process_event(
        trip_state=trip,
        event_type=request.event_type.value,
        message=request.message,
        target_node_id=request.target_node_id,
        preferences=request.preferences,
    )

    # Increment reroute count if structural
    if request.event_type in structural_events and not result["from_cache"]:
        db_service.increment_reroute_count(request.user_id)

    # Save updated trip state
    updated_trip = result["updated_trip_state"]
    db_service.save_trip(updated_trip)

    # Log the event
    db_service.log_event(
        user_id=request.user_id,
        trip_id=request.trip_id,
        event_type=request.event_type.value,
        routing_tier=result["routing_tier_used"],
        from_cache=result["from_cache"],
    )

    # Calculate remaining reroutes
    _, remaining, _ = db_service.check_reroute_allowed(request.user_id)

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

@router.post("/user/{user_id}/upgrade")
async def upgrade_user(user_id: str):
    """Upgrade user to pro tier."""
    user = db_service.upgrade_user(user_id)
    return {
        "user_id": user.user_id,
        "tier": user.tier_status.value,
        "max_daily_reroutes": user.max_daily_reroutes,
        "message": "Upgraded to Pro! You now have 50 daily reroutes.",
    }


@router.get("/venues/search")
async def search_venues(
    query: str,
    lat: float = 25.1972,
    lng: float = 55.2744,
    radius_km: float = 15.0,
    top_k: int = 5,
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
async def get_stats():
    """Get system statistics."""
    return {
        "cache": cache_service.get_stats(),
        "events": db_service.get_event_stats(),
        "venues_loaded": db_service.get_venue_count(),
    }
