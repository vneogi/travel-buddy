"""SPEC-30 slice 2: trip-edge observed-duration writer tests."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from main import app
from models.schemas import TripNode, TripState
from services.db_provider import db_service
from services.observed_duration_service import derive_observed_duration
from services.supabase_service import SupabaseService

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


def _edge_between(trip_id: str, from_venue: str, to_venue: str) -> dict:
    nodes = db_service.get_trip_nodes(trip_id)
    node_ids = {node["venue_ref"]: node["node_id"] for node in nodes}
    return next(
        edge
        for edge in db_service.get_trip_edges(trip_id)
        if edge["from_node_id"] == node_ids[from_venue]
        and edge["to_node_id"] == node_ids[to_venue]
    )


class TestObservedDuration:
    """Integration tests for observed_duration_minutes derivation."""

    def test_consecutive_pair_writes_duration(self):
        """Two confirmed arrivals write their span on the connecting edge."""
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

        # Confirm arrival at node B at 12:15 -> edge A->B = 130 minutes
        arrived_b = datetime(2026, 8, 25, 12, 15, tzinfo=timezone.utc)
        _confirm_visit(trip_id, "vid-b", arrived_b)

        edge = _edge_between(trip_id, "vid-a", "vid-b")
        assert edge["observed_duration_minutes"] == 130

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

        edge = _edge_between(trip_id, "vid-solo-a", "vid-solo-b")
        assert edge["observed_duration_minutes"] is None

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

        first_value = _edge_between(
            trip_id, "vid-idem-a", "vid-idem-b"
        )["observed_duration_minutes"]
        assert first_value == 130

        # Re-derive with same data -> same value
        derive_observed_duration(
            source_signal_id=sig_id,
            user_id="test-user-observed-dur",
            place_ref="vid-idem-b",
            captured_at=arrived_b,
            trip_id=trip_id,
        )
        assert (
            _edge_between(
                trip_id, "vid-idem-a", "vid-idem-b"
            )["observed_duration_minutes"]
            == first_value
        )

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

        edge = _edge_between(trip_id, "vid-skew-a", "vid-skew-b")
        assert edge["observed_duration_minutes"] is None

    def test_later_trip_save_preserves_observed_duration(self):
        """Dual-writing a changed trip cannot erase collected edge evidence."""
        t0 = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
        trip_id = _make_trip(
            [
                ("Durable A", "vid-durable-a", t0),
                ("Durable B", "vid-durable-b", t1),
            ]
        )
        _confirm_visit(
            trip_id,
            "vid-durable-a",
            datetime(2026, 8, 25, 10, 5, tzinfo=timezone.utc),
        )
        _confirm_visit(
            trip_id,
            "vid-durable-b",
            datetime(2026, 8, 25, 12, 15, tzinfo=timezone.utc),
        )
        assert (
            _edge_between(
                trip_id, "vid-durable-a", "vid-durable-b"
            )["observed_duration_minutes"]
            == 130
        )

        trip = db_service.get_trip(trip_id)
        assert trip is not None
        db_service.save_trip(trip)

        assert (
            _edge_between(
                trip_id, "vid-durable-a", "vid-durable-b"
            )["observed_duration_minutes"]
            == 130
        )

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

    def test_supabase_writer_targets_trip_edge(self):
        """Production backend must write the real SPEC-16 edge column."""

        class RecordingQuery:
            def __init__(self):
                self.payload = None
                self.filters = []

            def update(self, payload):
                self.payload = payload
                return self

            def eq(self, key, value):
                self.filters.append((key, value))
                return self

            def execute(self):
                return None

        class RecordingClient:
            def __init__(self):
                self.table_name = None
                self.query = RecordingQuery()

            def table(self, name):
                self.table_name = name
                return self.query

        service = object.__new__(SupabaseService)
        # client is a read-only property over _client; do not assign .client.
        service._client = RecordingClient()

        assert service.update_edge_observed_duration(
            trip_id="trip-1",
            from_node_id="node-a",
            to_node_id="node-b",
            duration_minutes=130,
        )
        assert service.client.table_name == "trip_edge"
        assert service.client.query.payload == {
            "observed_duration_minutes": 130
        }
        assert service.client.query.filters == [
            ("trip_id", "trip-1"),
            ("from_node_id", "node-a"),
            ("to_node_id", "node-b"),
        ]

    def test_supabase_edge_regeneration_preserves_observation(self):
        existing = [
            {
                "from_node_id": "node-a",
                "to_node_id": "node-b",
                "observed_duration_minutes": 130,
            }
        ]
        regenerated = [
            {
                "edge_id": "new-edge-id",
                "from_node_id": "node-a",
                "to_node_id": "node-b",
                "observed_duration_minutes": None,
            }
        ]

        merged = SupabaseService._preserve_observed_edge_durations(
            existing, regenerated
        )

        assert merged[0]["observed_duration_minutes"] == 130
