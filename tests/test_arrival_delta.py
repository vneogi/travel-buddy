"""Tests for arrival_delta server-side derivation.

Verifies that visited_confirmed signals produce a derived arrival_delta
signal with correct delta_minutes, deterministic signal_id, and that
failure cases (no trip, no node, no trip_id) are handled gracefully.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from services.arrival_delta_service import (
    derive_arrival_delta,
    _compute_delta,
    _deterministic_id,
    _find_node_for_place,
)
from models.schemas import TripNode, TripState
from services.db_provider import db_service


# ---------------------------------------------------------------------------
# Unit tests for pure functions
# ---------------------------------------------------------------------------


class TestComputeDelta:
    """Tests for _compute_delta (pure function, no DB)."""

    def test_on_time(self):
        scheduled = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
        actual = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
        assert _compute_delta(actual, scheduled) == 0.0

    def test_late_15_minutes(self):
        scheduled = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
        actual = datetime(2026, 8, 10, 14, 15, tzinfo=timezone.utc)
        assert _compute_delta(actual, scheduled) == 15.0

    def test_early_10_minutes(self):
        scheduled = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
        actual = datetime(2026, 8, 10, 13, 50, tzinfo=timezone.utc)
        assert _compute_delta(actual, scheduled) == -10.0

    def test_late_fractional(self):
        scheduled = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
        actual = scheduled + timedelta(minutes=7, seconds=30)
        assert _compute_delta(actual, scheduled) == 7.5

    def test_naive_datetimes_treated_as_utc(self):
        scheduled = datetime(2026, 8, 10, 14, 0)
        actual = datetime(2026, 8, 10, 14, 20)
        assert _compute_delta(actual, scheduled) == 20.0


class TestDeterministicId:
    """Tests for _deterministic_id (idempotent derivation)."""

    def test_same_input_same_output(self):
        id1 = _deterministic_id("abc-123")
        id2 = _deterministic_id("abc-123")
        assert id1 == id2

    def test_different_input_different_output(self):
        id1 = _deterministic_id("abc-123")
        id2 = _deterministic_id("xyz-789")
        assert id1 != id2

    def test_uuid_shaped(self):
        result = _deterministic_id("test-signal")
        parts = result.split("-")
        assert len(parts) == 5
        assert [len(p) for p in parts] == [8, 4, 4, 4, 12]


class TestFindNodeForPlace:
    """Tests for _find_node_for_place."""

    def _make_nodes(self):
        return [
            TripNode(
                venue_name="Dubai Museum",
                venue_id="venue-001",
                scheduled_start=datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc),
            ),
            TripNode(
                venue_name="Spice Souk",
                venue_id="venue-002",
                scheduled_start=datetime(2026, 8, 10, 11, 0, tzinfo=timezone.utc),
            ),
        ]

    def test_match_by_venue_id(self):
        nodes = self._make_nodes()
        result = _find_node_for_place(nodes, "venue-001")
        assert result is not None
        assert result.venue_name == "Dubai Museum"

    def test_match_by_name_case_insensitive(self):
        nodes = self._make_nodes()
        result = _find_node_for_place(nodes, "spice souk")
        assert result is not None
        assert result.venue_id == "venue-002"

    def test_no_match(self):
        nodes = self._make_nodes()
        result = _find_node_for_place(nodes, "nonexistent-place")
        assert result is None

    def test_empty_nodes(self):
        result = _find_node_for_place([], "anything")
        assert result is None


# ---------------------------------------------------------------------------
# Integration tests (uses in-memory db_service)
# ---------------------------------------------------------------------------


class TestDeriveArrivalDelta:
    """Integration tests for derive_arrival_delta."""

    def _create_trip_with_node(self, place_ref: str, scheduled_start: datetime) -> str:
        """Create a trip with one node, return trip_id."""
        trip_id = str(uuid.uuid4())
        user_id = "test-user-arrival"
        node = TripNode(
            venue_name=place_ref,
            venue_id=f"vid-{place_ref}",
            scheduled_start=scheduled_start,
        )
        trip = TripState(
            trip_id=trip_id,
            user_id=user_id,
            nodes=[node],
        )
        db_service.save_trip(trip)
        return trip_id

    def test_happy_path_late(self):
        """User arrives 12 minutes late -> delta = +12.0"""
        scheduled = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
        arrived = datetime(2026, 8, 10, 14, 12, tzinfo=timezone.utc)
        trip_id = self._create_trip_with_node("test-cafe", scheduled)

        result = derive_arrival_delta(
            source_signal_id="src-001",
            user_id="test-user-arrival",
            place_ref="vid-test-cafe",
            captured_at=arrived,
            trip_id=trip_id,
        )
        assert result == 12.0

    def test_happy_path_early(self):
        """User arrives 5 minutes early -> delta = -5.0"""
        scheduled = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
        arrived = datetime(2026, 8, 10, 13, 55, tzinfo=timezone.utc)
        trip_id = self._create_trip_with_node("early-venue", scheduled)

        result = derive_arrival_delta(
            source_signal_id="src-002",
            user_id="test-user-arrival",
            place_ref="vid-early-venue",
            captured_at=arrived,
            trip_id=trip_id,
        )
        assert result == -5.0

    def test_no_trip_id_returns_none(self):
        """No trip_id -> cannot derive, returns None gracefully."""
        result = derive_arrival_delta(
            source_signal_id="src-003",
            user_id="test-user",
            place_ref="some-place",
            captured_at=datetime.now(tz=timezone.utc),
            trip_id=None,
        )
        assert result is None

    def test_trip_not_found_returns_none(self):
        """Trip doesn't exist -> returns None gracefully."""
        result = derive_arrival_delta(
            source_signal_id="src-004",
            user_id="test-user",
            place_ref="some-place",
            captured_at=datetime.now(tz=timezone.utc),
            trip_id="nonexistent-trip-id",
        )
        assert result is None

    def test_node_not_found_returns_none(self):
        """Trip exists but no node matches place_ref -> returns None."""
        scheduled = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
        trip_id = self._create_trip_with_node("real-venue", scheduled)

        result = derive_arrival_delta(
            source_signal_id="src-005",
            user_id="test-user-arrival",
            place_ref="wrong-venue-name",
            captured_at=datetime.now(tz=timezone.utc),
            trip_id=trip_id,
        )
        assert result is None

    def test_idempotent_derivation(self):
        """Same source signal_id always produces same derived signal_id."""
        scheduled = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
        arrived = datetime(2026, 8, 10, 14, 10, tzinfo=timezone.utc)
        trip_id = self._create_trip_with_node("idem-venue", scheduled)

        result1 = derive_arrival_delta(
            source_signal_id="src-idem",
            user_id="test-user-arrival",
            place_ref="vid-idem-venue",
            captured_at=arrived,
            trip_id=trip_id,
        )
        # Second call should not fail (idempotent insert)
        result2 = derive_arrival_delta(
            source_signal_id="src-idem",
            user_id="test-user-arrival",
            place_ref="vid-idem-venue",
            captured_at=arrived,
            trip_id=trip_id,
        )
        assert result1 == result2 == 10.0
