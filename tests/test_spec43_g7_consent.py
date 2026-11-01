"""SPEC-43 Gap 7: fail-closed optional ingest.

Optional personalization / analytics signals are not stored without a
purpose grant. Necessary trip-operation signals still ingest. These tests
run the production ``has_consent`` (no suite grant).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import services.consent as consent
from main import app
from models.signal_types import SIGNAL_TYPES
from services.database_service import db_service

pytestmark = pytest.mark.real_consent

client = TestClient(app)

USER = "abababab-9999-4000-8000-0000000000a7"
HEADERS = {"X-Debug-User-Id": USER}


@pytest.fixture(autouse=True)
def reset_db():
    db_service._trips.clear()
    db_service._users.clear()
    db_service._signals.clear()
    db_service._parties.clear()
    yield


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _signal(signal_type: str, place_ref: str, **extra) -> dict:
    return {
        "signal_id": str(uuid.uuid4()),
        "signal_type": signal_type,
        "place_ref": place_ref,
        "captured_at": _now_iso(),
        **extra,
    }


def _post(signals: list[dict]) -> dict:
    resp = client.post("/api/v1/signals", json={"signals": signals}, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_trip() -> str:
    resp = client.post("/api/v1/trip/create", json={"start_date": _now_iso()}, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    trip_id = resp.json()["trip_id"]
    assert db_service.get_trip(trip_id).nodes
    return trip_id


def _node_place(trip_id: str) -> str:
    node = db_service.get_trip(trip_id).nodes[0]
    return node.venue_id or node.venue_name


def test_optional_personalization_signal_without_consent_is_rejected():
    sig = _signal("user_loved", "some-venue", value_text="loved")
    body = _post([sig])
    assert body["accepted"] == 0
    rejected = {r["signal_id"]: r["reason"] for r in body["rejected"]}
    assert set(rejected) == {sig["signal_id"]}
    assert "consent_required" in rejected[sig["signal_id"]]
    assert "personalization" in rejected[sig["signal_id"]]
    assert sig["signal_id"] not in db_service._signals


def test_necessary_operation_signal_without_consent_is_accepted():
    sig = _signal("session_start", "app", value_json={"cold_start": True})
    body = _post([sig])
    assert body["accepted"] == 1
    assert not [r for r in body["rejected"] if "consent_required" in r["reason"]]
    assert sig["signal_id"] in db_service._signals


def test_mixed_batch_love_rejected_session_accepted():
    love = _signal("user_loved", "some-venue", value_text="loved")
    session = _signal("session_start", "app", value_json={"cold_start": True})
    body = _post([love, session])
    assert body["accepted"] == 1
    assert [r["signal_id"] for r in body["rejected"]] == [love["signal_id"]]
    assert "consent_required" in body["rejected"][0]["reason"]
    assert love["signal_id"] not in db_service._signals
    assert session["signal_id"] in db_service._signals


def test_visited_confirmed_accepts_without_arrival_delta():
    trip_id = _create_trip()
    sig = _signal("visited_confirmed", _node_place(trip_id), trip_id=trip_id)
    body = _post([sig])
    assert body["accepted"] == 1 and body["rejected"] == []
    assert sig["signal_id"] in db_service._signals
    assert not [s for s in db_service._signals.values() if s["signal_type"] == "arrival_delta"]


def test_every_personalization_type_is_rejected_without_consent():
    trip_id = _create_trip()
    place = _node_place(trip_id)
    sigs = [
        _signal("user_loved", place, trip_id=trip_id, value_text="loved"),
        _signal("reroute_accepted", place, trip_id=trip_id, value_json={"replacement_ref": "x"}),
        _signal("reroute_rejected", place, trip_id=trip_id, value_json={"rejected_refs": ["x"]}),
        _signal(
            "dish_loved",
            place,
            value_text="loved",
            entity_type="dish",
            entity_id="dish-laap",
            value_json={"dish_name": "Laap"},
        ),
    ]
    body = _post(sigs)
    assert body["accepted"] == 0
    assert {r["signal_id"] for r in body["rejected"]} == {s["signal_id"] for s in sigs}
    assert all("consent_required" in r["reason"] for r in body["rejected"])
    assert db_service._signals == {}


def test_necessary_types_accept_without_consent():
    trip_id = _create_trip()
    place = _node_place(trip_id)
    sigs = [
        _signal("node_skipped", place, trip_id=trip_id, value_json={"reason": "too_tired"}),
        _signal(
            "booking_added",
            "booking",
            trip_id=trip_id,
            value_json={"booking_type": "hotel", "import_source": "manual"},
        ),
        _signal("prompt_dismissed", place, value_json={"kind": "k", "attribute": "a"}),
    ]
    body = _post(sigs)
    assert body["accepted"] == 3 and body["rejected"] == []


def test_production_has_consent_fails_closed():
    assert consent.has_consent(USER, consent.PURPOSE_NECESSARY) is True
    for purpose in (
        consent.PURPOSE_ANALYTICS,
        consent.PURPOSE_PERSONALIZATION,
        consent.PURPOSE_LOCATION,
        consent.PURPOSE_MARKETING,
        "unknown_purpose",
    ):
        assert consent.has_consent(USER, purpose) is False


def test_purpose_map_covers_every_signal_type():
    assert set(consent.SIGNAL_PURPOSE) == set(SIGNAL_TYPES)
    assert consent.purpose_for_signal("not_a_type") == consent.PURPOSE_ANALYTICS
    assert consent.SIGNAL_PURPOSE["arrival_delta"] == consent.PURPOSE_ANALYTICS


def test_require_consent_reason_names_purpose():
    with pytest.raises(consent.ConsentRequired) as exc:
        consent.require_consent_for_signal("user_loved", USER)
    assert exc.value.reason.startswith("consent_required")
    assert "personalization" in exc.value.reason
    consent.require_consent_for_signal("session_start", USER)  # no raise
