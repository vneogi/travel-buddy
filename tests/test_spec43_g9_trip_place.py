"""SPEC-43 Gap 9: a trip-linked venue signal must name a place on that trip.

Owning a trip is not a write primitive for an arbitrary place_ref. With a
trip_id, place_ref must equal a node venue_id or venue_name
(case-insensitive, stripped). session_start and booking_added are exempt.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from main import app
from models.schemas import TripNode, TripState
from services.database_service import db_service
from services.trip_ownership import trip_has_place

client = TestClient(app)

USER = "ffffffff-9999-4000-8000-00000000000f"
HEADERS = {"X-Debug-User-Id": USER}
OFF_TRIP = "not-on-this-trip"


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
        "/api/v1/trip/create",
        json={"start_date": _now().isoformat()},
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    trip_id = resp.json()["trip_id"]
    trip = db_service.get_trip(trip_id)
    assert trip is not None and len(trip.nodes) >= 2
    return trip_id


def _place_ref(node) -> str:
    return node.venue_id or node.venue_name


def _node_place(trip_id: str, index: int = 0) -> str:
    return _place_ref(db_service.get_trip(trip_id).nodes[index])


def _all_trip_places(trip_id: str) -> set[str]:
    out: set[str] = set()
    for n in db_service.get_trip(trip_id).nodes:
        out.update(x.strip().casefold() for x in (n.venue_id, n.venue_name) if x)
    return out


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


def _derived_rows() -> list[dict]:
    return [s for s in db_service._signals.values() if s.get("signal_type") == "arrival_delta"]


def test_trip_linked_signal_for_unknown_place_is_rejected():
    trip_id = _create_trip()
    assert OFF_TRIP not in _all_trip_places(trip_id)
    edges_before = list(db_service.get_trip_edges(trip_id))

    sig = _signal("user_loved", OFF_TRIP, trip_id, value_text="loved")
    body = _post([sig])

    assert body["accepted"] == 0
    rejected = {r["signal_id"]: r["reason"] for r in body["rejected"]}
    assert set(rejected) == {sig["signal_id"]}
    assert "place" in rejected[sig["signal_id"]]
    assert db_service.get_signal(sig["signal_id"]) is None
    assert db_service._signals == {}
    assert _derived_rows() == []
    assert list(db_service.get_trip_edges(trip_id)) == edges_before


def test_off_trip_visited_confirmed_is_rejected_and_derives_nothing():
    trip_id = _create_trip()
    # Prior on-trip confirm so a derive WOULD have something to pair with.
    first = _signal(
        "visited_confirmed",
        _node_place(trip_id, 0),
        trip_id,
        captured_at=(_now() - timedelta(minutes=30)).isoformat(),
    )
    assert _post([first])["accepted"] == 1
    rows_before = {k: dict(v) for k, v in db_service._signals.items()}
    edges_before = list(db_service.get_trip_edges(trip_id))

    off = _signal("visited_confirmed", OFF_TRIP, trip_id)
    body = _post([off])
    assert body["accepted"] == 0 and "place" in body["rejected"][0]["reason"]
    assert db_service._signals == rows_before
    assert list(db_service.get_trip_edges(trip_id)) == edges_before


def test_user_loved_on_real_node_accepts():
    trip_id = _create_trip()
    sig = _signal("user_loved", _node_place(trip_id), trip_id, value_text="loved")
    body = _post([sig])
    assert body["accepted"] == 1 and body["rejected"] == []
    assert db_service.get_signal(sig["signal_id"]) is not None


def test_match_is_case_insensitive_after_strip():
    trip_id = _create_trip()
    place = f"  {_node_place(trip_id).upper()}  "
    body = _post([_signal("user_loved", place, trip_id, value_text="loved")])
    assert body["accepted"] == 1 and body["rejected"] == []


def test_venue_name_matches_uncatalogued_node():
    trip = TripState(
        trip_id=f"trip-tp-{uuid.uuid4().hex[:8]}",
        user_id=USER,
        nodes=[TripNode(venue_name="Morning Market", scheduled_start=_now())],
    )
    db_service.save_trip(trip)
    assert trip.nodes[0].venue_id in (None, "")
    body = _post([_signal("user_loved", "morning market", trip.trip_id, value_text="loved")])
    assert body["accepted"] == 1 and body["rejected"] == []


def test_node_skipped_on_real_node_accepts():
    trip_id = _create_trip()
    sig = _signal("node_skipped", _node_place(trip_id), trip_id, value_json={"reason": "too_tired"})
    body = _post([sig])
    assert body["accepted"] == 1 and body["rejected"] == []


def test_node_skipped_off_trip_is_rejected():
    trip_id = _create_trip()
    sig = _signal("node_skipped", OFF_TRIP, trip_id, value_json={"reason": "too_tired"})
    body = _post([sig])
    assert body["accepted"] == 0 and "place" in body["rejected"][0]["reason"]


def test_session_start_with_trip_and_app_place_accepts():
    trip_id = _create_trip()
    sig = _signal("session_start", "app", trip_id, value_json={"cold_start": True})
    body = _post([sig])
    assert body["accepted"] == 1 and body["rejected"] == []


def test_booking_added_with_trip_is_exempt():
    trip_id = _create_trip()
    sig = _signal(
        "booking_added",
        "booking",
        trip_id,
        value_json={"booking_type": "hotel", "import_source": "manual"},
    )
    body = _post([sig])
    assert body["accepted"] == 1 and body["rejected"] == []


def test_no_trip_id_unknown_place_still_accepts():
    sig = _signal("user_loved", OFF_TRIP, value_text="loved")
    body = _post([sig])
    assert body["accepted"] == 1 and body["rejected"] == []


def test_mixed_batch_on_trip_accepts_unknown_place_rejects():
    trip_id = _create_trip()
    good = _signal("user_loved", _node_place(trip_id), trip_id, value_text="loved")
    bad = _signal("user_loved", OFF_TRIP, trip_id, value_text="loved")
    body = _post([good, bad])
    assert body["accepted"] == 1
    assert [r["signal_id"] for r in body["rejected"]] == [bad["signal_id"]]
    assert "place" in body["rejected"][0]["reason"]
    assert db_service.get_signal(good["signal_id"]) is not None
    assert db_service.get_signal(bad["signal_id"]) is None


def test_retry_of_stored_signal_id_is_duplicate():
    trip_id = _create_trip()
    sig = _signal("user_loved", _node_place(trip_id), trip_id, value_text="loved")
    assert _post([sig])["accepted"] == 1
    body = _post([sig])
    assert body["duplicates"] == 1 and body["rejected"] == []


def test_trip_has_place_helper():
    assert trip_has_place(None, "x") is False
    trip = TripState(
        trip_id="t",
        user_id=USER,
        nodes=[
            TripNode(
                venue_name="Wat Xieng Thong", venue_id="wat_xieng_thong", scheduled_start=_now()
            )
        ],
    )
    assert trip_has_place(trip, "wat_xieng_thong")
    assert trip_has_place(trip, " Wat Xieng Thong ")
    assert not trip_has_place(trip, OFF_TRIP)
    assert not trip_has_place(trip, "")
