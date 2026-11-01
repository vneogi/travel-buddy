"""SPEC-43 Gap 9: derived facts keep method version and sample size.

arrival_delta must carry explicit server_derived provenance with
method_version and sample_size (mirrored in value_json) so a later
aggregator can refuse n=1 poisoning. In-memory db_service only.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app
from services.arrival_delta_service import (
    ARRIVAL_DELTA_METHOD_VERSION,
    _deterministic_id,
    derive_arrival_delta,
)
from services.database_service import db_service

client = TestClient(app)

USER_A = "a1a1a1a1-9999-4000-8000-0000000000d1"
USER_B = "b2b2b2b2-9999-4000-8000-0000000000d2"
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
        "/api/v1/trip/create", json={"start_date": _now().isoformat()}, headers=HEADERS_A
    )
    assert resp.status_code == 200, resp.text
    trip_id = resp.json()["trip_id"]
    assert db_service.get_trip(trip_id).nodes
    return trip_id


def _node_place(trip_id: str) -> str:
    node = db_service.get_trip(trip_id).nodes[0]
    return node.venue_id or node.venue_name


def _confirm(trip_id: str, headers: dict) -> dict:
    sig = {
        "signal_id": str(uuid.uuid4()),
        "signal_type": "visited_confirmed",
        "place_ref": _node_place(trip_id),
        "trip_id": trip_id,
        "captured_at": (_now() - timedelta(minutes=1)).isoformat(),
    }
    resp = client.post("/api/v1/signals", json={"signals": [sig]}, headers=headers)
    assert resp.status_code == 200, resp.text
    return {"sig": sig, "body": resp.json()}


def _derived_rows() -> list[dict]:
    return [s for s in db_service._signals.values() if s["signal_type"] == "arrival_delta"]


def _derived_for(source_id: str) -> dict:
    rows = [
        r
        for r in _derived_rows()
        if (r.get("value_json") or {}).get("source_signal_id") == source_id
    ]
    assert len(rows) == 1, rows
    return rows[0]


def test_derived_arrival_delta_retains_method_version_and_sample_size():
    trip_id = _create_trip_as_a()
    out = _confirm(trip_id, HEADERS_A)
    assert out["body"]["accepted"] == 1
    source_id = out["sig"]["signal_id"]

    row = _derived_for(source_id)
    assert row["signal_id"] == _deterministic_id(source_id)
    prov = row["provenance"]
    assert prov["method"] == "server_derived"
    assert prov["method_version"] == 1
    assert prov["sample_size"] == 1
    assert prov["source_signal_id"] == source_id
    assert prov["method"] != "client_emit"

    vj = row["value_json"]
    assert vj["method_version"] == 1
    assert vj["sample_size"] == 1
    assert vj["method"] == "server_derived"
    assert vj["source_signal_id"] == source_id
    assert "scheduled_start" in vj
    assert isinstance(row["value_numeric"], float)
    assert ARRIVAL_DELTA_METHOD_VERSION == 1


def test_derived_arrival_delta_is_not_client_emit():
    trip_id = _create_trip_as_a()
    out = _confirm(trip_id, HEADERS_A)
    source_id = out["sig"]["signal_id"]

    derived = _derived_for(source_id)
    assert derived["provenance"]["method"] == "server_derived"

    source_row = db_service.get_signal(source_id)
    assert source_row is not None
    # The client visit itself is still a client emit.
    assert source_row["provenance"]["method"] == "client_emit"


def test_rederivation_is_idempotent_and_keeps_stamp():
    trip_id = _create_trip_as_a()
    out = _confirm(trip_id, HEADERS_A)
    source = out["sig"]
    captured = datetime.fromisoformat(source["captured_at"])
    derive_arrival_delta(source["signal_id"], USER_A, source["place_ref"], captured, trip_id)
    assert len(_derived_rows()) == 1
    assert _derived_for(source["signal_id"])["provenance"]["method_version"] == 1


def test_foreign_trip_writes_no_derived_row():
    trip_id = _create_trip_as_a()
    out = _confirm(trip_id, HEADERS_B)
    assert out["body"]["accepted"] == 0
    assert _derived_rows() == []

    result = derive_arrival_delta(
        source_signal_id="src-foreign-derived",
        user_id=USER_B,
        place_ref=_node_place(trip_id),
        captured_at=_now(),
        trip_id=trip_id,
    )
    assert result is None
    assert _derived_rows() == []


def test_ranking_code_still_does_not_read_signals():
    source = (
        Path(__file__).resolve().parent.parent / "services" / "catalog_itinerary.py"
    ).read_text()
    for needle in ("arrival_delta", "get_signal", "_signals", "db_service"):
        assert needle not in source, needle
