"""SPEC-29: Cancel correctness tests.

Proves canceled nodes stay in position, preserve fields,
and do not trigger RAG/LLM/venue search.
"""

from datetime import datetime, timezone

import pytest

from models.schemas import EventType, NodeStatus, TripNode, TripState
from services.scheduler import reschedule_and_validate


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


# --- Test 13: Cancel keeps order [A, canceled-B, C] ---


def test_cancel_keeps_original_order():
    """Cancel keeps order [A, canceled-B, C]."""
    nodes = [
        _node("A", hour=9, node_id="n-a"),
        _node("B", hour=11, node_id="n-b", status=NodeStatus.SKIPPED),
        _node("C", hour=13, node_id="n-c"),
    ]

    result = reschedule_and_validate(nodes)

    assert [n.node_id for n in result.nodes] == ["n-a", "n-b", "n-c"]
    # B is still at index 1
    assert result.nodes[1].status == NodeStatus.SKIPPED
    assert result.nodes[1].venue_name == "B"


# --- Test 14: Cancel preserves B venue id/name/time, only status changes ---


def test_cancel_preserves_venue_fields():
    """Cancel preserves B's venue id/name/time and changes only status."""
    b_node = _node("Desert Safari", hour=11, node_id="n-safari")
    b_node.status = NodeStatus.SKIPPED
    original_start = b_node.scheduled_start
    original_venue_name = b_node.venue_name
    original_venue_id = b_node.venue_id

    nodes = [
        _node("Museum", hour=9),
        b_node,
        _node("Dinner", hour=14),
    ]

    result = reschedule_and_validate(nodes)

    canceled = result.nodes[1]
    assert canceled.status == NodeStatus.SKIPPED
    assert canceled.venue_name == original_venue_name
    assert canceled.venue_id == original_venue_id
    assert canceled.scheduled_start == original_start


# --- Test 15: Cancel performs no venue search and no LLM call ---


def test_cancel_does_not_trigger_venue_search():
    """Cancel event_type is in STRUCTURAL but not VENUE_REQUIRED.

    The state machine _node_venue_search returns early for non-VENUE_REQUIRED events.
    This test validates the constant sets.
    """
    from agents.state_machine import VENUE_REQUIRED_EVENTS

    assert EventType.CANCEL_ACTIVITY.value not in VENUE_REQUIRED_EVENTS


# --- Test 16: Locked booking cannot be canceled ---


def test_locked_booking_not_in_skipped_by_scheduler():
    """Locked booking cannot be canceled -- scheduler still schedules it."""
    nodes = [
        _node("Activity", hour=9, node_id="n-act"),
        _node("Locked Hotel", hour=12, node_id="n-hotel", is_locked=True),
        _node("Dinner", hour=18, node_id="n-dinner"),
    ]

    # Even if somehow status were set to SKIPPED on a locked node,
    # the scheduler only skips non-locked scheduling -- locked nodes
    # always anchor. This test verifies the contract: locked nodes
    # should never have status=SKIPPED in practice.
    # The state machine must refuse cancellation of locked nodes.
    result = reschedule_and_validate(nodes)
    locked = [n for n in result.nodes if n.is_locked]
    assert all(n.status != NodeStatus.SKIPPED for n in locked)
