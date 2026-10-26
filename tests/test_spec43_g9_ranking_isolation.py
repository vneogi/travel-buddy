"""SPEC-43 Gap 9: ranking isolation and per-place rate cap.

One user must not flood ranking-corpus signals for one venue, and those
signals must not change SPEC-41 pack_day order. pack_day stays
catalog-only; ingest caps (user, type, place_ref) at
RANKING_CORPUS_PER_PLACE_CAP.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from main import app
from models.signal_types import (
    RANKING_CORPUS_PER_PLACE_CAP,
    RANKING_CORPUS_SIGNAL_TYPES,
)
from services.catalog_itinerary import pack_day
from services.database_service import db_service
from tests.test_spec41_named_slots import GEO, _venue

client = TestClient(app)

USER = "dddddddd-9999-4000-8000-00000000000d"
OTHER = "eeeeeeee-9999-4000-8000-00000000000e"
HEADERS = {"X-Debug-User-Id": USER}

# Same as TestSlotHelpers._DAY_START in test_spec41_named_slots (09:00 ICT).
_DAY_START = datetime(2026, 9, 14, 2, 0, tzinfo=timezone.utc)


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


def _loved(place_ref: str) -> dict:
    return _signal("user_loved", place_ref, value_text="loved")


def _post(signals: list[dict], headers: dict = HEADERS) -> dict:
    resp = client.post("/api/v1/signals", json={"signals": signals}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _pack_ids(candidates: list[dict]) -> list[str]:
    nodes, _ = pack_day(
        candidates=candidates,
        target_count=4,
        day_start_utc=_DAY_START,
        geo_region=GEO,
        used_ids=set(),
        interest_ids=(),
    )
    return [n.venue_id for n in nodes]


def test_one_user_cannot_materially_move_venue_score():
    # Two same-category venues at the same point: scores tie, name/id wins.
    candidates = [_venue("Alpha Temple"), _venue("Beta Temple")]
    baseline = _pack_ids(candidates)
    assert len(baseline) == 2
    trailing = baseline[-1]

    body = _post([_loved(trailing) for _ in range(RANKING_CORPUS_PER_PLACE_CAP)])
    assert body["accepted"] == RANKING_CORPUS_PER_PLACE_CAP
    assert body["rejected"] == []
    assert db_service.count_signals_for_user_place(USER, "user_loved", trailing) == (
        RANKING_CORPUS_PER_PLACE_CAP
    )

    assert _pack_ids(candidates) == baseline


def test_fourth_user_loved_for_same_place_is_rate_rejected():
    place = "venue-rate-1"
    for _ in range(RANKING_CORPUS_PER_PLACE_CAP):
        body = _post([_loved(place)])
        assert body["accepted"] == 1 and body["rejected"] == []

    fourth = _loved(place)
    body = _post([fourth])
    assert body["accepted"] == 0
    assert [r["signal_id"] for r in body["rejected"]] == [fourth["signal_id"]]
    assert "rate" in body["rejected"][0]["reason"]
    assert db_service.get_signal(fourth["signal_id"]) is None
    assert db_service.count_signals_for_user_place(USER, "user_loved", place) == 3


def test_mixed_batch_of_four_accepts_three_rejects_one_for_rate():
    place = "venue-rate-batch"
    sigs = [_loved(place) for _ in range(4)]
    body = _post(sigs)
    assert body["accepted"] == 3
    assert len(body["rejected"]) == 1
    assert body["rejected"][0]["signal_id"] == sigs[3]["signal_id"]
    assert "rate" in body["rejected"][0]["reason"]
    assert db_service.get_signal(sigs[3]["signal_id"]) is None


def test_retry_of_stored_signal_id_is_duplicate_not_rate_reject():
    place = "venue-rate-dup"
    sigs = [_loved(place) for _ in range(RANKING_CORPUS_PER_PLACE_CAP)]
    assert _post(sigs)["accepted"] == RANKING_CORPUS_PER_PLACE_CAP

    body = _post([sigs[0]])
    assert body["accepted"] == 0
    assert body["duplicates"] == 1
    assert body["rejected"] == []

    # Same signal_id twice in one batch with the cap full: still duplicates.
    body = _post([sigs[1], sigs[1]])
    assert body["duplicates"] == 2 and body["rejected"] == []


def test_cap_is_per_user_type_and_place():
    place = "venue-rate-scope"
    assert _post([_loved(place) for _ in range(3)])["accepted"] == 3
    # Other place, other type, other user: each has its own budget.
    assert _post([_loved("venue-rate-other")])["accepted"] == 1
    assert _post([_signal("visited_confirmed", place)])["accepted"] == 1
    other = _post([_loved(place)], headers={"X-Debug-User-Id": OTHER})
    assert other["accepted"] == 1 and other["rejected"] == []


def test_session_start_is_not_capped():
    sigs = [_signal("session_start", "app", value_json={"cold_start": True}) for _ in range(4)]
    body = _post(sigs)
    assert body["accepted"] == 4 and body["rejected"] == []


def test_node_skipped_too_tired_still_accepts():
    sigs = [
        _signal("node_skipped", "venue-skip", value_json={"reason": "too_tired"}) for _ in range(4)
    ]
    body = _post(sigs)
    assert body["accepted"] == 4 and body["rejected"] == []


def test_ranking_corpus_set_is_exact():
    assert RANKING_CORPUS_SIGNAL_TYPES == frozenset(
        {
            "user_loved",
            "visited_confirmed",
            "reroute_accepted",
            "reroute_rejected",
            "dish_loved",
            "dish_ordered",
        }
    )
    assert RANKING_CORPUS_PER_PLACE_CAP == 3


# --- R4: Supabase backend helper (fake client, no live Postgres) -----------


class _FakeQuery:
    def __init__(self, recorder: dict, count: int | None, fail: bool):
        self._rec, self._count, self._fail = recorder, count, fail

    def select(self, *args, **kwargs):
        self._rec["select"] = (args, kwargs)
        return self

    def eq(self, col, val):
        self._rec.setdefault("eq", {})[col] = val
        return self

    def execute(self):
        if self._fail:
            raise RuntimeError("boom")
        return type("R", (), {"count": self._count, "data": []})()


class _FakeClient:
    def __init__(self, count: int | None = 2, fail: bool = False):
        self.rec: dict = {}
        self._count, self._fail = count, fail

    def table(self, name):
        self.rec["table"] = name
        return _FakeQuery(self.rec, self._count, self._fail)


def _supabase_with(fake: _FakeClient):
    from services.supabase_service import SupabaseService

    svc = object.__new__(SupabaseService)
    svc._client = fake
    svc._signal_type_cache = {"user_loved": 7}
    return svc


def test_supabase_count_filters_user_place_and_type_id():
    fake = _FakeClient(count=2)
    svc = _supabase_with(fake)
    assert svc.count_signals_for_user_place(USER, "user_loved", "venue-x") == 2
    assert fake.rec["table"] == "signal"
    assert fake.rec["eq"] == {"user_id": USER, "place_ref": "venue-x", "signal_type_id": 7}
    assert fake.rec["select"][1].get("count") == "exact"


def test_supabase_count_fails_closed_on_error():
    svc = _supabase_with(_FakeClient(fail=True))
    assert svc.count_signals_for_user_place(USER, "user_loved", "venue-x") >= (
        RANKING_CORPUS_PER_PLACE_CAP
    )
