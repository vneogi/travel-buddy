"""SPEC-43 Gap 9: trip-linked signal ownership on POST /api/v1/signals.

User B must not attach signals, party_context, or derived facts
(arrival_delta, observed_duration) to user A's trip.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from main import app
from services.arrival_delta_service import derive_arrival_delta
from services.database_service import db_service
from services.observed_duration_service import derive_observed_duration
from services.trip_ownership import get_owned_trip, is_trip_owned_by

client = TestClient(app)

USER_A = "aaaaaaaa-9999-4000-8000-00000000000a"
USER_B = "bbbbbbbb-9999-4000-8000-00000000000b"
HEADERS_A = {"X-Debug-User-Id": USER_A}
HEADERS_B = {"X-Debug-User-Id": USER_B}


@pytest.fixture(autouse=True)
def reset_db():
    db_service._trips.clear()
    db_service._users.clear()
    db_service._signals.clear()
    db_service._parties.clear()
    yield


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _create_trip_as_a() -> str:
    resp = client.post(
        "/api/v1/trip/create",
        json={
            "start_date": _now().isoformat(),
            "party": {
                "party_type": "couple",
                "size": 2,
                "members": [
                    {"role": "self", "age_band": "adult", "needs": []},
                    {"role": "partner", "age_band": "adult", "needs": []},
                ],
            },
        },
        headers=HEADERS_A,
    )
    assert resp.status_code == 200, resp.text
    trip_id = resp.json()["trip_id"]
    trip = db_service.get_trip(trip_id)
    assert trip is not None and str(trip.user_id) == USER_A
    assert len(trip.nodes) >= 2, "need two nodes for an observed_duration edge"
    assert db_service.get_trip_party(trip_id) is not None
    return trip_id


def _place_ref(node) -> str:
    return node.venue_id or node.venue_name


def _signal(signal_type: str, place_ref: str, trip_id: str | None, **extra) -> dict:
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


def _post(signals: list[dict], headers: dict) -> dict:
    resp = client.post("/api/v1/signals", json={"signals": signals}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _rows_for_trip(trip_id: str) -> list[dict]:
    return [s for s in db_service._signals.values() if s.get("trip_id") == trip_id]


def _edge_durations(trip_id: str) -> list:
    return [e.get("observed_duration_minutes") for e in db_service.get_trip_edges(trip_id)]


def test_foreign_trip_id_is_rejected_and_writes_nothing():
    trip_id = _create_trip_as_a()
    trip = db_service.get_trip(trip_id)
    first, second = trip.nodes[0], trip.nodes[1]

    # A confirms the first node on A's own trip (sets up a previous arrival,
    # so a foreign confirm on the second node WOULD write an edge duration).
    a_confirm = _signal("visited_confirmed", _place_ref(first), trip_id)
    a_body = _post([a_confirm], HEADERS_A)
    assert a_body["accepted"] == 1 and a_body["rejected"] == []

    rows_before = {k: dict(v) for k, v in db_service._signals.items()}
    edges_before = _edge_durations(trip_id)
    party_before = db_service.get_trip_party(trip_id)

    loved = _signal("user_loved", _place_ref(second), trip_id)
    confirmed = _signal(
        "visited_confirmed",
        _place_ref(second),
        trip_id,
        captured_at=(_now() + timedelta(minutes=1)).isoformat(),
    )
    body = _post([loved, confirmed], HEADERS_B)

    assert body["accepted"] == 0
    assert body["duplicates"] == 0
    rejected = {r["signal_id"]: r["reason"] for r in body["rejected"]}
    assert set(rejected) == {loved["signal_id"], confirmed["signal_id"]}
    for reason in rejected.values():
        assert "trip" in reason and ("owner" in reason or "ownership" in reason)

    # No signal row for either of B's signals.
    assert db_service.get_signal(loved["signal_id"]) is None
    assert db_service.get_signal(confirmed["signal_id"]) is None
    assert db_service._signals == rows_before
    assert not [s for s in db_service._signals.values() if s.get("user_id") == USER_B]

    # No party_context write: party unchanged, no B row carrying party_context.
    assert db_service.get_trip_party(trip_id) == party_before

    # No derived rows for A's trip from B's confirm.
    assert not [
        s
        for s in _rows_for_trip(trip_id)
        if s["signal_type"] == "arrival_delta"
        and (s.get("value_json") or {}).get("source_signal_id") == confirmed["signal_id"]
    ]
    assert _edge_durations(trip_id) == edges_before


def test_derive_services_are_not_called_for_foreign_trip(monkeypatch):
    trip_id = _create_trip_as_a()
    node = db_service.get_trip(trip_id).nodes[0]
    calls: list[str] = []
    monkeypatch.setattr(
        "services.arrival_delta_service.derive_arrival_delta",
        lambda **kw: calls.append("arrival_delta"),
    )
    monkeypatch.setattr(
        "services.observed_duration_service.derive_observed_duration",
        lambda **kw: calls.append("observed_duration"),
    )
    body = _post([_signal("visited_confirmed", _place_ref(node), trip_id)], HEADERS_B)
    assert body["accepted"] == 0 and len(body["rejected"]) == 1
    assert calls == []


def test_owner_posting_to_own_trip_is_accepted_with_party_context():
    trip_id = _create_trip_as_a()
    node = db_service.get_trip(trip_id).nodes[0]
    loved = _signal("user_loved", _place_ref(node), trip_id)
    confirmed = _signal("visited_confirmed", _place_ref(node), trip_id)
    body = _post([loved, confirmed], HEADERS_A)
    assert body["accepted"] == 2 and body["rejected"] == []
    stored = db_service.get_signal(loved["signal_id"])
    assert stored is not None and stored["user_id"] == USER_A
    assert "party_context" in (stored["value_json"] or {})
    arrival = [
        s
        for s in _rows_for_trip(trip_id)
        if s["signal_type"] == "arrival_delta"
        and (s.get("value_json") or {}).get("source_signal_id") == confirmed["signal_id"]
    ]
    assert len(arrival) == 1


def test_owned_trip_without_party_accepts_and_omits_party_context():
    trip_id = _create_trip_as_a()
    db_service._parties.clear()
    assert db_service.get_trip_party(trip_id) is None
    node = db_service.get_trip(trip_id).nodes[0]
    sig = _signal("user_loved", _place_ref(node), trip_id)
    body = _post([sig], HEADERS_A)
    assert body["accepted"] == 1 and body["rejected"] == []
    vj = db_service.get_signal(sig["signal_id"])["value_json"] or {}
    assert "party_context" not in vj


def test_omitted_trip_id_still_accepts():
    sig = _signal("user_loved", "some-venue", None)
    body = _post([sig], HEADERS_B)
    assert body["accepted"] == 1 and body["rejected"] == []
    assert db_service.get_signal(sig["signal_id"]) is not None


def test_unknown_trip_id_is_rejected():
    sig = _signal("user_loved", "some-venue", "nonexistent-trip-id")
    body = _post([sig], HEADERS_A)
    assert body["accepted"] == 0
    assert [r["signal_id"] for r in body["rejected"]] == [sig["signal_id"]]
    assert db_service.get_signal(sig["signal_id"]) is None


def test_mixed_batch_rejects_only_foreign_item():
    trip_id = _create_trip_as_a()
    node = db_service.get_trip(trip_id).nodes[0]
    foreign = _signal("user_loved", _place_ref(node), trip_id)
    tripless = _signal("user_loved", "some-venue", None)
    body = _post([foreign, tripless], HEADERS_B)
    assert body["accepted"] == 1
    assert [r["signal_id"] for r in body["rejected"]] == [foreign["signal_id"]]


def test_derive_arrival_delta_rechecks_ownership():
    trip_id = _create_trip_as_a()
    node = db_service.get_trip(trip_id).nodes[0]
    before = dict(db_service._signals)
    result = derive_arrival_delta(
        source_signal_id="src-foreign",
        user_id=USER_B,
        place_ref=_place_ref(node),
        captured_at=_now(),
        trip_id=trip_id,
    )
    assert result is None
    assert db_service._signals == before


def test_derive_observed_duration_rechecks_ownership():
    trip_id = _create_trip_as_a()
    first, second = db_service.get_trip(trip_id).nodes[:2]
    _post([_signal("visited_confirmed", _place_ref(first), trip_id)], HEADERS_A)
    edges_before = _edge_durations(trip_id)
    result = derive_observed_duration(
        source_signal_id="src-foreign-od",
        user_id=USER_B,
        place_ref=_place_ref(second),
        captured_at=_now() + timedelta(minutes=30),
        trip_id=trip_id,
    )
    assert result is None
    assert _edge_durations(trip_id) == edges_before


def test_shared_helper_contract():
    trip_id = _create_trip_as_a()
    assert is_trip_owned_by(trip_id, USER_A)
    assert get_owned_trip(trip_id, USER_A) is not None
    assert not is_trip_owned_by(trip_id, USER_B)
    assert not is_trip_owned_by("nonexistent-trip-id", USER_A)
    assert not is_trip_owned_by(None, USER_A)
    assert not is_trip_owned_by("", USER_A)
