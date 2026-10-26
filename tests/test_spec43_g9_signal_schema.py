"""SPEC-43 Gap 9: closed signal value_json schemas on POST /api/v1/signals.

Client value_json must be a closed map (known keys only) and bounded in size.
Unknown keys, client-sent party_context, and oversized JSON are per-item
rejected before party_context merge and record_signal, and are not stored.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from main import app
from models.signal_types import (
    PAYLOAD_SHAPES,
    VALUE_JSON_ALLOWED_KEYS,
    VALUE_JSON_MAX_BYTES,
    client_emittable_types,
    value_json_schema_error,
)
from services.database_service import db_service

client = TestClient(app)

USER = "cccccccc-9999-4000-8000-00000000000c"
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


def _signal(signal_type: str, **extra) -> dict:
    return {
        "signal_id": str(uuid.uuid4()),
        "signal_type": signal_type,
        "place_ref": "test-venue",
        "captured_at": _now_iso(),
        **extra,
    }


def _post(signals: list[dict]) -> dict:
    resp = client.post("/api/v1/signals", json={"signals": signals}, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_trip() -> str:
    resp = client.post(
        "/api/v1/trip/create",
        json={"start_date": _now_iso()},
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["trip_id"]


def _assert_rejected(body: dict, sig: dict, *needles: str) -> None:
    assert body["accepted"] == 0
    rejected = {r["signal_id"]: r["reason"] for r in body["rejected"]}
    assert set(rejected) == {sig["signal_id"]}
    reason = rejected[sig["signal_id"]]
    assert any(n in reason for n in needles), reason
    assert db_service.get_signal(sig["signal_id"]) is None


def test_unknown_value_json_field_is_rejected():
    sig = _signal("user_loved", value_text="loved", value_json={"original_field": "x"})
    body = _post([sig])
    _assert_rejected(body, sig, "schema", "unknown")
    assert "original_field" in body["rejected"][0]["reason"]


def test_user_loved_without_value_json_accepts():
    sig = _signal("user_loved", value_text="loved")
    body = _post([sig])
    assert body["accepted"] == 1 and body["rejected"] == []
    assert db_service.get_signal(sig["signal_id"]) is not None


def test_empty_value_json_accepts():
    sig = _signal("user_loved", value_text="loved", value_json={})
    body = _post([sig])
    assert body["accepted"] == 1 and body["rejected"] == []


def test_client_party_context_is_rejected():
    trip_id = _create_trip()
    node = db_service.get_trip(trip_id).nodes[0]
    sig = _signal(
        "user_loved",
        trip_id=trip_id,
        place_ref=node.venue_id or node.venue_name,
        value_json={"party_context": {"party_type": "family_young_kids", "size": 9}},
    )
    body = _post([sig])
    _assert_rejected(body, sig, "schema", "unknown")
    assert "party_context" in body["rejected"][0]["reason"]


def test_oversize_value_json_is_rejected():
    # Allowlisted key so only size can fail.
    big = "x" * (VALUE_JSON_MAX_BYTES + 1)
    sig = _signal("reroute_accepted", value_json={"replacement_ref": big})
    body = _post([sig])
    _assert_rejected(body, sig, "size")


def test_value_json_at_size_limit_accepts():
    overhead = len('{"replacement_ref": ""}'.encode("utf-8"))
    ok = "x" * (VALUE_JSON_MAX_BYTES - overhead)
    assert value_json_schema_error("reroute_accepted", {"replacement_ref": ok}) is None
    assert value_json_schema_error("reroute_accepted", {"replacement_ref": ok + "x"})


def test_oversize_counts_utf8_bytes_not_characters():
    # 2000 Lao characters = 6000 UTF-8 bytes (each is 3 bytes).
    lao = "\u0ea7" * 2000
    err = value_json_schema_error("name_confirmed", {"shown_value": lao})
    assert err and "size" in err


def test_node_skipped_valid_reason_accepts():
    sig = _signal("node_skipped", value_json={"reason": "too_tired"})
    body = _post([sig])
    assert body["accepted"] == 1 and body["rejected"] == []
    assert db_service.get_signal(sig["signal_id"])["value_json"] == {"reason": "too_tired"}


def test_node_skipped_extra_key_is_rejected():
    sig = _signal("node_skipped", value_json={"reason": "too_tired", "note": "free text"})
    body = _post([sig])
    _assert_rejected(body, sig, "schema", "unknown")


def test_owned_trip_user_loved_accepts_with_server_party_context():
    trip_id = _create_trip()
    node = db_service.get_trip(trip_id).nodes[0]
    sig = _signal("user_loved", value_text="loved", trip_id=trip_id)
    # SPEC-43 Gap 9 trip-place: a trip-linked signal must name a node.
    sig["place_ref"] = node.venue_id or node.venue_name
    body = _post([sig])
    assert body["accepted"] == 1 and body["rejected"] == []
    stored = db_service.get_signal(sig["signal_id"])
    assert stored is not None
    vj = stored["value_json"] or {}
    # Only server-stamped keys may appear for a no-key type.
    assert set(vj) <= {"party_context"}


def test_dish_signal_with_dish_name_accepts():
    sig = _signal(
        "dish_loved",
        value_text="loved",
        entity_type="dish",
        entity_id="dish-laap",
        value_json={"dish_name": "Laap"},
    )
    body = _post([sig])
    assert body["accepted"] == 1 and body["rejected"] == []


def test_session_start_client_keys_accept():
    sig = _signal(
        "session_start",
        value_json={"cold_start": True, "minutes_since_last_open": 30, "trip_day": 1},
    )
    body = _post([sig])
    assert body["accepted"] == 1 and body["rejected"] == []


def test_mixed_batch_rejects_only_bad_item():
    good = _signal("user_loved", value_text="loved")
    bad = _signal("user_loved", value_text="loved", value_json={"evil": 1})
    body = _post([good, bad])
    assert body["accepted"] == 1
    assert [r["signal_id"] for r in body["rejected"]] == [bad["signal_id"]]
    assert db_service.get_signal(good["signal_id"]) is not None
    assert db_service.get_signal(bad["signal_id"]) is None


def test_allowlist_covers_every_client_emittable_type():
    assert set(VALUE_JSON_ALLOWED_KEYS) == set(client_emittable_types())
    assert set(VALUE_JSON_ALLOWED_KEYS) <= set(PAYLOAD_SHAPES)
    for keys in VALUE_JSON_ALLOWED_KEYS.values():
        assert "party_context" not in keys


def test_unknown_type_fails_closed_in_helper():
    assert value_json_schema_error("not_a_type", {"a": 1})
    assert value_json_schema_error("not_a_type", None) is None
