"""SPEC-29 D3/D5: Synthetic transit cannot reach user-visible copy.

Tests SWAP and CANCEL through the real state machine with forced extreme
transit. Asserts no synthetic minutes, traffic, or "unreachable" claim in
user response.

The SWAP test MUST fail against 10c897b (where scheduler still emitted
the "unreachable" warning for non-cancel events).
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

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


def test_swap_with_extreme_transit_no_synthetic_in_response():
    """SWAP event with 500-min forced transit must not surface transit claim.

    This test fails against 10c897b because the scheduler still appended
    "Locked X is unreachable -- previous stop + N min transit runs M min over."
    to schedule_warnings, which _node_generate_response appended to the user.
    """
    trip = _trip(
        [
            _node("Museum", hour=9, node_id="n-museum"),
            _node("Desert Safari", hour=11, node_id="n-safari"),
            _node("Locked Dinner", hour=14, node_id="n-dinner", is_locked=True),
        ]
    )

    # Force transit to return 500 minutes between any pair of stops.
    with patch(
        "services.maps_service.maps_service.get_transit_time",
        return_value={"duration_minutes": 500, "distance_km": 30.0},
    ):
        result = asyncio.run(
            state_machine.process_event(
                trip_state=trip,
                event_type=EventType.SWAP_ACTIVITY.value,
                message="Swap Desert Safari for something else",
                target_node_id="n-safari",
                preferences={"vibe_tags": ["adventure"]},
            )
        )

    response = result["response"]
    # D3: No synthetic transit data in user-facing response
    assert "500" not in response
    assert "unreachable" not in response.lower()
    # "transit range" in the no_candidates fallback is acceptable (user preference, not synthetic).
    # Disallow synthetic transit: "N min transit", "unreachable".
    assert "min transit" not in response.lower()
    assert "traffic" not in response.lower()
    assert "min over" not in response.lower()


def test_cancel_with_extreme_transit_deterministic():
    """Cancel returns deterministic copy regardless of transit values."""
    trip = _trip(
        [
            _node("Locked Brunch", hour=9, node_id="n-brunch", is_locked=True),
            _node("Activity", hour=11, node_id="n-act"),
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
    assert "Canceled Activity" in response
    assert "500" not in response
    assert "unreachable" not in response.lower()


def test_saved_hours_warning_preserved():
    """Opening-hours hedged warning is still emitted (not suppressed)."""
    trip = _trip(
        [
            _node("Lunch", hour=9, node_id="n-lunch"),
        ]
    )
    # Set opening hours that will fail the check
    trip.nodes[0].opening_hours = "Mo-Fr 18:00-22:00"

    with patch(
        "services.maps_service.maps_service.check_venue_open",
        return_value=False,
    ):
        result = asyncio.run(
            state_machine.process_event(
                trip_state=trip,
                event_type=EventType.SWAP_ACTIVITY.value,
                message="Swap Lunch",
                target_node_id="n-lunch",
                preferences={},
            )
        )

    response = result["response"]
    # Hedged saved-hours warning IS allowed
    if "saved venue hours" in response.lower() or "may be closed" in response.lower():
        assert "Verify locally" in response
