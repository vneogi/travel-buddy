"""SPEC-29 D3: Synthetic transit cannot reach user-visible copy.

Forces maps_service to return an extreme transit duration, then processes
a structural event and asserts the user response has no synthetic minutes,
traffic claims, or "unreachable" factual claims.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from agents.state_machine import state_machine
from models.schemas import EventType, NodeStatus, TripNode, TripState


def _node(name, hour, duration=60, node_id=None, is_locked=False, lat=25.2, lng=55.3):
    return TripNode(
        node_id=node_id or f"n-{name.lower().replace(' ', '-')}",
        venue_name=name,
        venue_id=f"vid-{name.lower()}",
        scheduled_start=datetime(2026, 10, 5, hour, 0, tzinfo=timezone.utc),
        duration_minutes=duration,
        is_locked=is_locked,
        status=NodeStatus.PENDING,
        lat=lat,
        lng=lng,
    )


def _trip(nodes):
    return TripState(
        trip_id="trip-transit-test",
        user_id="u1",
        geo_region="dubai_uae",
        nodes=nodes,
    )


def test_extreme_transit_does_not_surface_in_cancel_response():
    """Cancel with extreme transit never surfaces transit claim."""
    trip = _trip(
        [
            _node("Museum", hour=9, node_id="n-museum", is_locked=True),
            _node("Desert Safari", hour=10, node_id="n-safari"),
            _node("Mall", hour=12, node_id="n-mall"),
        ]
    )

    # Force maps to return extreme transit (999 min). If cancel path
    # accidentally calls maps or scheduler surfaces it, the user message
    # would contain "999" or "unreachable".
    with patch(
        "services.maps_service.maps_service.get_transit_time",
        return_value={"duration_minutes": 999, "distance_km": 50.0},
    ):
        result = asyncio.run(
            state_machine.process_event(
                trip_state=trip,
                event_type=EventType.CANCEL_ACTIVITY.value,
                message="Cancel Desert Safari",
                target_node_id="n-safari",
            )
        )

    response = result["response"]
    # D3: No synthetic transit minutes in user response
    assert "999" not in response
    assert "500" not in response
    assert "unreachable" not in response.lower()
    assert "transit" not in response.lower()
    assert "traffic" not in response.lower()
    # Cancel is deterministic
    assert "Canceled Desert Safari" in response


def test_scheduler_warnings_no_synthetic_transit_claims():
    """Scheduler warnings after cancel do not contain transit minutes."""
    trip = _trip(
        [
            _node("Locked Brunch", hour=9, node_id="n-brunch", is_locked=True),
            _node("Activity", hour=10, node_id="n-act"),
            _node("Dinner", hour=18, node_id="n-dinner", is_locked=True),
        ]
    )

    with patch(
        "services.maps_service.maps_service.get_transit_time",
        return_value={"duration_minutes": 500, "distance_km": 30.0},
    ):
        result = asyncio.run(
            state_machine.process_event(
                trip_state=trip,
                event_type=EventType.CANCEL_ACTIVITY.value,
                message="Cancel Activity",
                target_node_id="n-act",
            )
        )

    response = result["response"]
    # D3: Scheduler warnings must not surface synthetic transit claims
    assert "500" not in response
    assert "unreachable" not in response.lower()
    assert "min transit" not in response.lower()
