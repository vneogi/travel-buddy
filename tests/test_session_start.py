"""SPEC-30: session_start signal tests.

Tests that session_start:
  - Is accepted by POST /api/v1/signals
  - Gets trip_day stamped from captured_at (not wall-clock)
  - Ingests fine without trip_id (no trip_day)
  - Passes the drift guard (test_signal_types.py covers this)
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from main import app
from models.schemas import TripState
from services.db_provider import db_service

client = TestClient(app)
HEADERS = {"X-Debug-User-Id": "test-user-session-start"}


def test_session_start_accepted():
    """session_start is accepted by ingest (not in SERVER_DERIVED_TYPES)."""
    signal_id = str(uuid.uuid4())
    payload = {
        "signals": [
            {
                "signal_id": signal_id,
                "signal_type": "session_start",
                "place_ref": "session",
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "value_json": {"cold_start": True},
            }
        ]
    }
    resp = client.post("/api/v1/signals", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] == 1
    assert data["duplicates"] == 0
    assert len(data["rejected"]) == 0


def test_session_start_trip_day_from_captured_at():
    """trip_day is computed from captured_at relative to trip.created_at,
    NOT from datetime.now(). An old captured_at proves this.

    Sabotage proof S2: using datetime.now() instead of captured_at
    would produce today-relative days, not the asserted value of 3.
    The dates (Aug 20 start, Aug 23 captured_at) are within the
    30-day skew tolerance but far enough from now to prove the
    computation uses captured_at, not wall-clock.
    """
    trip_id = f"trip-session-{uuid.uuid4().hex[:8]}"
    trip_created = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    trip = TripState(
        trip_id=trip_id,
        user_id="test-user-session-start",
        nodes=[],
        created_at=trip_created,
    )
    db_service.save_trip(trip)

    # captured_at is Aug 23 -> trip_day should be 3
    captured_at = datetime(2026, 8, 23, 15, 0, tzinfo=timezone.utc)
    signal_id = str(uuid.uuid4())
    payload = {
        "signals": [
            {
                "signal_id": signal_id,
                "signal_type": "session_start",
                "place_ref": "session",
                "trip_id": trip_id,
                "captured_at": captured_at.isoformat(),
                "value_json": {"cold_start": True},
            }
        ]
    }
    resp = client.post("/api/v1/signals", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 1

    # Verify trip_day was stamped
    stored = db_service.get_signal(signal_id)
    assert stored is not None
    assert stored["value_json"]["trip_day"] == 3


def test_session_start_no_trip_id_ok():
    """session_start without trip_id ingests fine and carries no trip_day."""
    signal_id = str(uuid.uuid4())
    payload = {
        "signals": [
            {
                "signal_id": signal_id,
                "signal_type": "session_start",
                "place_ref": "session",
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "value_json": {"cold_start": False, "minutes_since_last_open": 42},
            }
        ]
    }
    resp = client.post("/api/v1/signals", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 1

    stored = db_service.get_signal(signal_id)
    assert stored is not None
    assert "trip_day" not in stored["value_json"]
    assert stored["value_json"]["minutes_since_last_open"] == 42
