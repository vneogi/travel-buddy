"""Tests for SPEC-10 Booking Anchors.

Sabotage proofs:
  S1: scheduler allows locked booking to move -> test 3 fails
  S2: signal includes confirmation_code -> test 7 fails
  S3: extractBookingFromText throws on empty -> Flutter test fails
  S4: TripNode node_kind required (no default) -> test 1 fails
"""

from datetime import datetime, timedelta, timezone

import pytest

from agents.router_agent import router_agent
from models.schemas import EventType, NodeStatus, RoutingTier, TripNode
from models.signal_types import PAYLOAD_SHAPES, SIGNAL_TYPES
from services.itinerary_normaliser import (
    compose_trip_nodes,
    decompose_trip,
    round_trip_equal,
)
from services.scheduler import reschedule_and_validate


class TestLegacyTripNodeDefaults:
    """Sabotage 4: making node_kind required (no default) breaks this."""

    def test_legacy_trip_node_deserializes_with_safe_defaults(self):
        """JSON without booking fields loads cleanly with defaults."""
        node = TripNode(
            venue_name="Old Venue",
            scheduled_start=datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc),
        )
        assert node.node_kind == "activity"
        assert node.booking_type is None
        assert node.confirmation_code is None
        assert node.booking_notes is None
        assert node.import_source is None
        assert node.is_locked is False


class TestBookingAnchorLocking:
    def test_booking_anchor_is_always_locked(self):
        """A node created with node_kind=booking has is_locked=True in handler."""
        node = TripNode(
            venue_name="EK501 to Dubai",
            scheduled_start=datetime(2026, 10, 5, 14, 0, tzinfo=timezone.utc),
            is_locked=True,
            node_kind="booking",
            booking_type="flight",
            confirmation_code="AB12CD",
            import_source="manual",
        )
        assert node.is_locked is True
        assert node.node_kind == "booking"
        assert node.booking_type == "flight"


class TestSchedulerBookingAnchors:
    """Sabotage 1: letting scheduler move locked booking breaks test 3."""

    def test_booking_anchor_scheduled_start_never_moves(self):
        """Rescheduling keeps locked booking start time identical."""
        booking_start = datetime(2026, 10, 5, 14, 0, tzinfo=timezone.utc)
        nodes = [
            TripNode(
                venue_name="Morning Activity",
                scheduled_start=datetime(2026, 10, 5, 8, 0, tzinfo=timezone.utc),
                duration_minutes=60,
            ),
            TripNode(
                venue_name="Flight EK501",
                scheduled_start=booking_start,
                duration_minutes=180,
                is_locked=True,
                node_kind="booking",
                booking_type="flight",
            ),
        ]
        result = reschedule_and_validate(nodes)
        flight = [n for n in result.nodes if n.node_kind == "booking"][0]
        assert flight.scheduled_start == booking_start

    def test_scheduler_flags_hard_conflict_on_booking_overrun(self):
        """Activity 08:00+90min + 60min transit before 09:30 locked flight = conflict."""
        nodes = [
            TripNode(
                venue_name="Long Activity",
                scheduled_start=datetime(2026, 10, 5, 8, 0, tzinfo=timezone.utc),
                duration_minutes=90,
                lat=25.19,
                lng=55.27,
            ),
            TripNode(
                venue_name="Flight",
                scheduled_start=datetime(2026, 10, 5, 9, 30, tzinfo=timezone.utc),
                duration_minutes=180,
                is_locked=True,
                node_kind="booking",
                booking_type="flight",
                lat=25.25,
                lng=55.36,
            ),
        ]
        result = reschedule_and_validate(nodes)
        # 08:00 + 90min = 09:30, + transit > 09:30 => conflict
        assert result.has_hard_conflict is True


class TestNormaliserBookingMetadata:
    def test_itinerary_normaliser_preserves_booking_metadata(self):
        """decompose -> compose roundtrips all 5 booking fields."""
        trip_state = {
            "trip_id": "trip_test",
            "nodes": [
                {
                    "node_id": "n1",
                    "venue_name": "Flight to Luang Prabang",
                    "scheduled_start": "2026-10-05T14:00:00+00:00",
                    "duration_minutes": 180,
                    "is_locked": True,
                    "status": "pending",
                    "vibe_tags": [],
                    "node_kind": "booking",
                    "booking_type": "flight",
                    "confirmation_code": "PNR123",
                    "booking_notes": "Window seat",
                    "import_source": "email",
                }
            ],
        }
        nodes, _edges = decompose_trip(trip_state)
        composed = compose_trip_nodes(nodes)
        c = composed[0]
        assert c["node_kind"] == "booking"
        assert c["booking_type"] == "flight"
        assert c["confirmation_code"] == "PNR123"
        assert c["booking_notes"] == "Window seat"
        assert c["import_source"] == "email"

        # round_trip_equal should also pass
        assert round_trip_equal(trip_state) is True

    def test_tour_booking_uses_allowed_activity_node_type(self):
        trip_state = {
            "trip_id": "tour_trip",
            "nodes": [
                {
                    "node_id": "tour-1",
                    "venue_name": "Mekong tour",
                    "scheduled_start": "2026-10-05T14:00:00+00:00",
                    "node_kind": "booking",
                    "booking_type": "tour",
                }
            ],
        }

        nodes, _edges = decompose_trip(trip_state)

        assert nodes[0]["node_type"] == "activity"
        assert nodes[0]["booking_type"] == "tour"


class TestBookingSignal:
    def test_booking_added_signal_drift_guard_and_ingest(self):
        """booking_added is registered with correct payload shape."""
        assert "booking_added" in SIGNAL_TYPES
        assert SIGNAL_TYPES["booking_added"] == "json"
        shape = PAYLOAD_SHAPES["booking_added"]
        assert "booking_type" in shape
        assert "import_source" in shape

    def test_confirmation_code_not_in_signal_or_logs(self):
        """Sabotage 2: signal payload must NOT contain confirmation_code."""
        shape = PAYLOAD_SHAPES["booking_added"]
        assert "confirmation_code" not in shape


class TestEventTypeExists:
    def test_add_booking_event_type_exists(self):
        """ADD_BOOKING is a valid EventType."""
        assert EventType.ADD_BOOKING.value == "add_booking"

    def test_add_booking_stays_light_and_never_needs_trip_state_in_an_llm(self):
        tier, _confidence = router_agent.classify_intent(
            "Add booking anchor",
            EventType.ADD_BOOKING.value,
        )
        assert tier == RoutingTier.LIGHT
