"""SPEC-29 D4: Cancel correctness tests.

All tests invoke `process_event` through the real state machine.
Venue search and LLM are monkeypatched to raise if called -- proving
cancel uses neither.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from agents.state_machine import (
    VENUE_REQUIRED_EVENTS,
    state_machine,
)
from models.schemas import EventType, NodeStatus, TripNode, TripState


def _node(name, hour, duration=90, node_id=None, is_locked=False, status=NodeStatus.PENDING):
    return TripNode(
        node_id=node_id or f"n-{name.lower().replace(' ', '-')}",
        venue_name=name,
        venue_id=f"vid-{name.lower().replace(' ', '-')}",
        scheduled_start=datetime(2026, 10, 5, hour, 0, tzinfo=timezone.utc),
        duration_minutes=duration,
        is_locked=is_locked,
        status=status,
        lat=25.2,
        lng=55.3,
    )


def _trip(nodes):
    return TripState(
        trip_id="trip-cancel-test",
        user_id="u1",
        geo_region="dubai_uae",
        nodes=nodes,
    )


def _monkeypatch_no_llm_no_venue():
    """Return patches that raise if venue search or LLM is called."""
    venue_patch = patch(
        "services.db_provider.db_service.hybrid_venue_search",
        side_effect=AssertionError("Venue search must not be called for cancel"),
    )
    llm_patch = patch(
        "services.llm_service.llm_service.classify_intent",
        side_effect=AssertionError("LLM classify must not be called for cancel"),
    )
    llm_gen_patch = patch(
        "services.llm_service.llm_service.generate_itinerary_response",
        side_effect=AssertionError("LLM gen must not be called for cancel"),
    )
    return venue_patch, llm_patch, llm_gen_patch


# =========================================================================
# Test 1: Unlocked cancel succeeds with no search/LLM
# =========================================================================


def test_cancel_unlocked_no_search_no_llm():
    """Cancel an unlocked node: no venue search, no LLM call."""
    trip = _trip(
        [
            _node("Museum", hour=9, node_id="n-museum"),
            _node("Desert Safari", hour=11, node_id="n-safari"),
            _node("Dinner", hour=14, node_id="n-dinner"),
        ]
    )

    venue_p, llm_p, llm_gen_p = _monkeypatch_no_llm_no_venue()
    with venue_p, llm_p, llm_gen_p:
        result = asyncio.run(
            state_machine.process_event(
                trip_state=trip,
                event_type=EventType.CANCEL_ACTIVITY.value,
                message="Cancel Desert Safari",
                target_node_id="n-safari",
            )
        )

    # Succeeded without triggering any monkeypatched raises.
    assert "Canceled Desert Safari" in result["response"]
    updated = result["updated_trip_state"]
    canceled = next(n for n in updated.nodes if n.node_id == "n-safari")
    assert canceled.status == NodeStatus.SKIPPED


# =========================================================================
# Test 2: Canceled node remains at original index
# =========================================================================


def test_cancel_preserves_original_index():
    """Canceled node stays at index 1 in [A, B, C]."""
    trip = _trip(
        [
            _node("A", hour=9, node_id="n-a"),
            _node("B", hour=11, node_id="n-b"),
            _node("C", hour=14, node_id="n-c"),
        ]
    )

    venue_p, llm_p, llm_gen_p = _monkeypatch_no_llm_no_venue()
    with venue_p, llm_p, llm_gen_p:
        result = asyncio.run(
            state_machine.process_event(
                trip_state=trip,
                event_type=EventType.CANCEL_ACTIVITY.value,
                message="Cancel B",
                target_node_id="n-b",
            )
        )

    nodes = result["updated_trip_state"].nodes
    assert [n.node_id for n in nodes] == ["n-a", "n-b", "n-c"]
    assert nodes[1].status == NodeStatus.SKIPPED
    assert nodes[1].venue_name == "B"
    assert nodes[1].venue_id == "vid-b"


# =========================================================================
# Test 3: Locked cancel refuses and is unchanged
# =========================================================================


def test_cancel_locked_refuses_unchanged():
    """Locked booking cancellation refused with deterministic copy."""
    trip = _trip(
        [
            _node("Activity", hour=9, node_id="n-act"),
            _node("Locked Hotel", hour=12, node_id="n-hotel", is_locked=True),
            _node("Dinner", hour=18, node_id="n-dinner"),
        ]
    )

    venue_p, llm_p, llm_gen_p = _monkeypatch_no_llm_no_venue()
    with venue_p, llm_p, llm_gen_p:
        result = asyncio.run(
            state_machine.process_event(
                trip_state=trip,
                event_type=EventType.CANCEL_ACTIVITY.value,
                message="Cancel Locked Hotel",
                target_node_id="n-hotel",
            )
        )

    # Response is a calm refusal
    assert "locked" in result["response"].lower()
    assert "cannot be canceled" in result["response"].lower()

    # Node is unchanged
    hotel = next(n for n in result["updated_trip_state"].nodes if n.node_id == "n-hotel")
    assert hotel.status == NodeStatus.PENDING
    assert hotel.is_locked is True
    assert hotel.venue_name == "Locked Hotel"


# =========================================================================
# Test 4: Response is deterministic (no LLM variance)
# =========================================================================


def test_cancel_response_is_deterministic():
    """Same cancel produces identical response text."""

    def run_cancel():
        trip = _trip([_node("Spa", hour=10, node_id="n-spa")])
        venue_p, llm_p, llm_gen_p = _monkeypatch_no_llm_no_venue()
        with venue_p, llm_p, llm_gen_p:
            return asyncio.run(
                state_machine.process_event(
                    trip_state=trip,
                    event_type=EventType.CANCEL_ACTIVITY.value,
                    message="Cancel Spa",
                    target_node_id="n-spa",
                )
            )

    r1 = run_cancel()
    r2 = run_cancel()
    assert r1["response"] == r2["response"]
    assert r1["response"] == "Canceled Spa."


# =========================================================================
# Test 5: Repeated cancel is idempotent
# =========================================================================


def test_cancel_idempotent():
    """Canceling an already-skipped node is a no-op (still deterministic)."""
    trip = _trip(
        [
            _node("Beach", hour=10, node_id="n-beach", status=NodeStatus.SKIPPED),
        ]
    )

    venue_p, llm_p, llm_gen_p = _monkeypatch_no_llm_no_venue()
    with venue_p, llm_p, llm_gen_p:
        result = asyncio.run(
            state_machine.process_event(
                trip_state=trip,
                event_type=EventType.CANCEL_ACTIVITY.value,
                message="Cancel Beach",
                target_node_id="n-beach",
            )
        )

    # Node stays skipped, response is still valid
    assert result["updated_trip_state"].nodes[0].status == NodeStatus.SKIPPED
    assert "Canceled Beach" in result["response"] or "Beach" in result["response"]
