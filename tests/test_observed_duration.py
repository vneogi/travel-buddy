"""SPEC-30 slice 2: observed_duration_minutes writer tests.

Verifies that derive_observed_duration correctly writes dwell time on the
PREVIOUS node when consecutive visited_confirmed signals are available.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from main import app
from models.schemas import TripNode, TripState
from services.db_provider import db_service
from services.observed_duration_service import derive_observed_duration

client = TestClient(app)
HEADERS = {"X-Debug-User-Id": "test-user-observed-dur"}


def _make_trip(node_defs: list[tuple[str, str, datetime]]) -> str:
    """Create a trip with nodes. Each tuple: (venue_name, venue_id, scheduled_start)."""
    trip_id = f"trip-od-{uuid.uuid4().hex[:8]}"
    nodes = [
        TripNode(
            venue_name=name,
            venue_id=vid,
            scheduled_start=start,
        )
        for name, vid, start in node_defs
    ]
    trip = TripState(
        trip_id=trip_id,
        user_id="test-user-observed-dur",
        nodes=nodes,
    )
    db_service.save_trip(trip)
    return trip_id


def _confirm_visit(trip_id: str, place_ref: str, captured_at: datetime) -> str:
    """Post a visited_confirmed signal. Returns signal_id."""
    signal_id = str(uuid.uuid4())
    payload = {
        "signals": [
            {
                "signal_id": signal_id,
                "signal_type": "visited_confirmed",
                "place_ref": place_ref,
                "trip_id": trip_id,
                "captured_at": captured_at.isoformat(),
            }
        ]
    }
    resp = client.post("/api/v1/signals", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 1
    return signal_id


class TestObservedDuration:
    """Integration tests for observed_duration_minutes derivation."""

    def test_consecutive_pair_writes_duration(self):
        """Two confirmed arrivals on consecutive nodes write the first node's
        observed_duration_minutes as the minute span between them.
        """
        t0 = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
        trip_id = _make_trip(
            [
                ("Cafe A", "vid-a", t0),
                ("Museum B", "vid-b", t1),
            ]
        )

        # Confirm arrival at node A at 10:05
        arrived_a = datetime(2026, 8, 25, 10, 5, tzinfo=timezone.utc)
        _confirm_visit(trip_id, "vid-a", arrived_a)

        # Confirm arrival at node B at 12:15 -> duration on A = 130 minutes
        arrived_b = datetime(2026, 8, 25, 12, 15, tzinfo=timezone.utc)
        _confirm_visit(trip_id, "vid-b", arrived_b)

        # Check: node A should have observed_duration_minutes = 130.0
        trip = db_service.get_trip(trip_id)
        node_a = [n for n in trip.nodes if n.venue_id == "vid-a"][0]
        assert node_a.observed_duration_minutes == 130.0

    def test_single_confirmation_writes_nothing(self):
        """A single confirmation writes nothing (pair incomplete).
        The column stays None, not zero.
        """
        t0 = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
        trip_id = _make_trip(
            [
                ("Solo A", "vid-solo-a", t0),
                ("Solo B", "vid-solo-b", t1),
            ]
        )

        # Only confirm node B (no confirmation for A)
        arrived_b = datetime(2026, 8, 25, 12, 10, tzinfo=timezone.utc)
        _confirm_visit(trip_id, "vid-solo-b", arrived_b)

        # Node A should have NO observed_duration_minutes (None, not 0)
        trip = db_service.get_trip(trip_id)
        node_a = [n for n in trip.nodes if n.venue_id == "vid-solo-a"][0]
        assert node_a.observed_duration_minutes is None

    def test_idempotent_repost(self):
        """Re-posting the same visited_confirmed does not change the value."""
        t0 = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
        trip_id = _make_trip(
            [
                ("Idem A", "vid-idem-a", t0),
                ("Idem B", "vid-idem-b", t1),
            ]
        )

        arrived_a = datetime(2026, 8, 25, 10, 5, tzinfo=timezone.utc)
        _confirm_visit(trip_id, "vid-idem-a", arrived_a)

        arrived_b = datetime(2026, 8, 25, 12, 15, tzinfo=timezone.utc)
        sig_id = _confirm_visit(trip_id, "vid-idem-b", arrived_b)

        trip = db_service.get_trip(trip_id)
        node_a = [n for n in trip.nodes if n.venue_id == "vid-idem-a"][0]
        first_value = node_a.observed_duration_minutes
        assert first_value == 130.0

        # Re-derive with same data -> same value
        derive_observed_duration(
            source_signal_id=sig_id,
            user_id="test-user-observed-dur",
            place_ref="vid-idem-b",
            captured_at=arrived_b,
            trip_id=trip_id,
        )
        trip2 = db_service.get_trip(trip_id)
        node_a2 = [n for n in trip2.nodes if n.venue_id == "vid-idem-a"][0]
        assert node_a2.observed_duration_minutes == first_value

    def test_negative_span_writes_nothing(self):
        """A confirmation whose computed span is negative (clock skew)
        writes nothing.
        """
        t0 = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
        trip_id = _make_trip(
            [
                ("Skew A", "vid-skew-a", t0),
                ("Skew B", "vid-skew-b", t1),
            ]
        )

        # Confirm A at 12:00
        arrived_a = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
        _confirm_visit(trip_id, "vid-skew-a", arrived_a)

        # Confirm B at 11:00 (BEFORE A -> negative span)
        arrived_b = datetime(2026, 8, 25, 11, 0, tzinfo=timezone.utc)
        _confirm_visit(trip_id, "vid-skew-b", arrived_b)

        trip = db_service.get_trip(trip_id)
        node_a = [n for n in trip.nodes if n.venue_id == "vid-skew-a"][0]
        assert node_a.observed_duration_minutes is None

    def test_derivation_failure_does_not_reject_source(self):
        """Derivation failure (unknown trip) never rejects the source
        visited_confirmed -- the batch still reports it accepted.
        """
        signal_id = str(uuid.uuid4())
        payload = {
            "signals": [
                {
                    "signal_id": signal_id,
                    "signal_type": "visited_confirmed",
                    "place_ref": "some-venue",
                    "trip_id": "nonexistent-trip-999",
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                }
            ]
        }
        resp = client.post("/api/v1/signals", json=payload, headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        # Source signal is ACCEPTED, not rejected
        assert data["accepted"] == 1
        assert len(data["rejected"]) == 0
