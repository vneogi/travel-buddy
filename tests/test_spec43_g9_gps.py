"""SPEC-43 Gap 9: GPS plausibility on signal ingest.

Optional lat/lng must be a finite, in-range pair. Trip-linked presence
claims (visited_confirmed, node_skipped) must be near the matched node.
In-memory db_service only.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from main import app
from services.database_service import db_service
from services.gps_plausibility import (
    MAX_ACCURACY_M,
    MAX_GPS_OFFSET_M,
    gps_range_error,
    haversine_m,
)

client = TestClient(app)

USER = "abcdabcd-9999-4000-8000-0000000009a5"
HEADERS = {"X-Debug-User-Id": USER}

NODE_LAT, NODE_LNG = 17.97, 102.6  # Vientiane
DUBAI_LAT, DUBAI_LNG = 25.2, 55.27


@pytest.fixture(autouse=True)
def reset_db():
    db_service._trips.clear()
    db_service._users.clear()
    db_service._signals.clear()
    db_service._parties.clear()
    yield


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _create_trip() -> str:
    resp = client.post(
        "/api/v1/trip/create", json={"start_date": _now().isoformat()}, headers=HEADERS
    )
    assert resp.status_code == 200, resp.text
    trip_id = resp.json()["trip_id"]
    assert db_service.get_trip(trip_id).nodes
    return trip_id


def _place_ref(node) -> str:
    return node.venue_id or node.venue_name


def _pin_first_node(
    trip_id: str, lat: float | None = NODE_LAT, lng: float | None = NODE_LNG
) -> str:
    """Give the first node known coords (patch if catalog left them empty)."""
    trip = db_service.get_trip(trip_id)
    node = trip.nodes[0]
    node.lat, node.lng = lat, lng
    db_service.save_trip(trip)
    stored = db_service.get_trip(trip_id).nodes[0]
    assert (stored.lat, stored.lng) == (lat, lng)
    return _place_ref(stored)


def _signal(signal_type: str, place_ref: str, trip_id: str | None = None, **extra) -> dict:
    body = {
        "signal_id": str(uuid.uuid4()),
        "signal_type": signal_type,
        "place_ref": place_ref,
        "captured_at": _now().isoformat(),
        **extra,
    }
    if trip_id is not None:
        body["trip_id"] = trip_id
    return body


def _post(signals: list[dict]) -> dict:
    resp = client.post("/api/v1/signals", json={"signals": signals}, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _arrival_rows() -> list[dict]:
    return [s for s in db_service._signals.values() if s["signal_type"] == "arrival_delta"]


def _assert_gps_rejected(body: dict, sig: dict) -> None:
    assert body["accepted"] == 0
    rejected = {r["signal_id"]: r["reason"] for r in body["rejected"]}
    assert set(rejected) == {sig["signal_id"]}
    assert "gps" in rejected[sig["signal_id"]]
    assert db_service.get_signal(sig["signal_id"]) is None


def test_impossible_gps_coords_are_rejected():
    trip_id = _create_trip()
    place = _pin_first_node(trip_id)
    sig = _signal("visited_confirmed", place, trip_id, value_json={"lat": 999, "lng": 0})
    body = _post([sig])
    _assert_gps_rejected(body, sig)
    assert _arrival_rows() == []
    assert db_service._signals == {}


def test_gps_too_far_from_trip_node_is_rejected():
    trip_id = _create_trip()
    place = _pin_first_node(trip_id)
    assert haversine_m(DUBAI_LAT, DUBAI_LNG, NODE_LAT, NODE_LNG) > 1_000_000
    edges_before = list(db_service.get_trip_edges(trip_id))
    sig = _signal(
        "visited_confirmed",
        place,
        trip_id,
        value_json={"lat": DUBAI_LAT, "lng": DUBAI_LNG, "accuracy_m": 15},
    )
    body = _post([sig])
    _assert_gps_rejected(body, sig)
    assert "too far" in body["rejected"][0]["reason"]
    assert db_service._signals == {}
    assert _arrival_rows() == []
    assert list(db_service.get_trip_edges(trip_id)) == edges_before


def test_node_skipped_far_gps_is_rejected():
    trip_id = _create_trip()
    place = _pin_first_node(trip_id)
    sig = _signal(
        "node_skipped",
        place,
        trip_id,
        value_json={"reason": "too_tired", "lat": DUBAI_LAT, "lng": DUBAI_LNG},
    )
    _assert_gps_rejected(_post([sig]), sig)


def test_gps_within_1km_accepts():
    trip_id = _create_trip()
    place = _pin_first_node(trip_id)
    near_lat = NODE_LAT + 0.005  # ~555 m north
    assert haversine_m(near_lat, NODE_LNG, NODE_LAT, NODE_LNG) < 1000
    sig = _signal(
        "visited_confirmed",
        place,
        trip_id,
        value_json={"lat": near_lat, "lng": NODE_LNG, "accuracy_m": 20},
    )
    body = _post([sig])
    assert body["accepted"] == 1 and body["rejected"] == []
    assert db_service.get_signal(sig["signal_id"]) is not None


def test_no_gps_still_accepts():
    trip_id = _create_trip()
    place = _pin_first_node(trip_id)
    body = _post([_signal("visited_confirmed", place, trip_id)])
    assert body["accepted"] == 1 and body["rejected"] == []


def test_node_without_coords_skips_distance_but_keeps_range():
    trip_id = _create_trip()
    place = _pin_first_node(trip_id, lat=None, lng=None)
    far = _signal(
        "visited_confirmed", place, trip_id, value_json={"lat": DUBAI_LAT, "lng": DUBAI_LNG}
    )
    assert _post([far])["accepted"] == 1
    bad = _signal("visited_confirmed", place, trip_id, value_json={"lat": 999, "lng": 0})
    _assert_gps_rejected(_post([bad]), bad)


def test_only_lat_rejects():
    trip_id = _create_trip()
    place = _pin_first_node(trip_id)
    sig = _signal("visited_confirmed", place, trip_id, value_json={"lat": NODE_LAT})
    _assert_gps_rejected(_post([sig]), sig)


def test_user_loved_with_far_coords_still_accepts():
    trip_id = _create_trip()
    place = _pin_first_node(trip_id)
    sig = _signal(
        "user_loved",
        place,
        trip_id,
        value_text="loved",
        value_json={"lat": DUBAI_LAT, "lng": DUBAI_LNG},
    )
    body = _post([sig])
    assert body["accepted"] == 1 and body["rejected"] == []


def test_user_loved_impossible_coords_rejects_without_trip():
    sig = _signal(
        "user_loved", "free-floating", value_text="loved", value_json={"lat": 0, "lng": 999}
    )
    _assert_gps_rejected(_post([sig]), sig)


def test_stored_signal_id_retry_with_bad_gps_is_duplicate():
    trip_id = _create_trip()
    place = _pin_first_node(trip_id)
    sig = _signal(
        "visited_confirmed", place, trip_id, value_json={"lat": NODE_LAT, "lng": NODE_LNG}
    )
    assert _post([sig])["accepted"] == 1
    retry = dict(sig, value_json={"lat": 999, "lng": 0})
    body = _post([retry])
    assert body["duplicates"] == 1 and body["rejected"] == []


def test_session_start_lat_is_schema_reject_not_gps():
    sig = _signal(
        "session_start", "app", value_json={"cold_start": True, "lat": NODE_LAT, "lng": NODE_LNG}
    )
    body = _post([sig])
    assert body["accepted"] == 0
    reason = body["rejected"][0]["reason"]
    assert "schema" in reason and "unknown" in reason
    assert not reason.startswith("gps")


@pytest.mark.parametrize(
    "vj",
    [
        {"lat": True, "lng": 0},
        {"lat": "17.9", "lng": 102.6},
        {"lat": float("nan"), "lng": 0},
        {"lat": 0, "lng": float("inf")},
        {"lat": -90.0001, "lng": 0},
        {"lat": 0, "lng": 180.5},
        {"lng": 0},
        {"lat": 0, "lng": 0, "accuracy_m": 0},
        {"lat": 0, "lng": 0, "accuracy_m": MAX_ACCURACY_M + 1},
        {"lat": 0, "lng": 0, "accuracy_m": True},
    ],
)
def test_gps_range_helper_rejects(vj):
    err = gps_range_error(vj)
    assert err and err.startswith("gps")


@pytest.mark.parametrize(
    "vj",
    [
        None,
        {},
        {"lat": 90, "lng": -180},
        {"lat": -90, "lng": 180},
        {"lat": 1, "lng": 2, "accuracy_m": MAX_ACCURACY_M},
    ],
)
def test_gps_range_helper_accepts(vj):
    assert gps_range_error(vj) is None


def test_haversine_and_constants():
    assert MAX_GPS_OFFSET_M == 50000 and MAX_ACCURACY_M == 10000
    assert haversine_m(0, 0, 0, 0) == 0
    one_degree = haversine_m(0, 0, 1, 0)
    assert math.isclose(one_degree, 111195, rel_tol=0.01)
