"""SPEC-43 Gap 8: trip, local date, and source version in the cache key.

Exact-match trip_id, destination-local date, and source_version
(trip.version + catalog version) on top of identity / region / venue,
HMAC of the query, cosine, and restricted refusal. Explicit now_utc and
local_date only. No widgets, no live Postgres.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agents.state_machine import RoutingTier, state_machine
from models.schemas import TripNode, TripState
from services.ask_service import _CATALOG_VERSION
from services.booking_constraints import _local_date_of
from services.cache_service import SemanticCacheService, cache_service

KEY = b"g8-context-test-key"
USER = "user-g8-context"
OTHER = "user-g8-context-other"
REGION = "luang_prabang_laos"
VENUE = "Wat Xieng Thong"
QUERY = "What time is the boat?"
DATE = "2026-10-06"
VERSION = "1:test-cat"
TRIP_A, TRIP_B = "trip-g8-a", "trip-g8-b"
PROSE = "The boat leaves at 09:30 from the pier."
CONF_CANARY = "CANARY-g8-restricted-BK-XYZ"


@pytest.fixture()
def svc() -> SemanticCacheService:
    return SemanticCacheService(hmac_key=KEY)


def _ctx(**over) -> dict:
    ctx = {
        "geo_region": REGION,
        "venue_name": VENUE,
        "trip_id": TRIP_A,
        "local_date": DATE,
        "source_version": VERSION,
    }
    ctx.update(over)
    return ctx


def _store(svc, response=PROSE, identity=USER, needles=(), **over):
    svc.store_response(
        QUERY, response, identity_scope=identity, restricted_needles=needles, **_ctx(**over)
    )


def _check(svc, identity=USER, **over):
    return svc.check_cache(QUERY, identity_scope=identity, **_ctx(**over))


def test_cache_misses_when_trip_id_changes(svc):
    _store(svc, trip_id=TRIP_A)
    assert _check(svc, trip_id=TRIP_B) is None
    hit = _check(svc, trip_id=TRIP_A)
    assert hit is not None and hit[0] == PROSE


def test_cache_misses_when_local_date_or_source_version_changes(svc):
    _store(svc, trip_id=TRIP_A)
    assert _check(svc, local_date="2026-10-07") is None
    assert _check(svc, source_version="2:test-cat") is None
    assert _check(svc, source_version="1:other-cat") is None
    assert _check(svc)[0] == PROSE


def test_empty_context_matches_only_empty_context(svc):
    _store(svc, trip_id="", local_date="", source_version="")
    assert _check(svc) is None
    assert _check(svc, trip_id="", local_date="", source_version="")[0] == PROSE


def test_identity_isolation_still_holds(svc):
    _store(svc, identity=USER)
    assert _check(svc, identity=OTHER) is None
    assert _check(svc, identity=USER)[0] == PROSE


@pytest.mark.parametrize("identity", ["", "   ", "anonymous", None])
def test_unusable_identity_still_stores_nothing(svc, identity):
    _store(svc, identity=identity)
    assert svc._cache == []
    assert _check(svc, identity=identity) is None


def test_restricted_response_refusal_still_holds(svc):
    _store(svc, response=f"Show {CONF_CANARY} at the pier.", needles=[CONF_CANARY])
    _store(svc, response="Use sk-g8contextRESTRICTED42 to sign in.")
    assert svc._cache == []
    assert _check(svc) is None


def test_context_is_not_hashed_into_query_hmac(svc):
    _store(svc, trip_id=TRIP_A)
    _store(svc, trip_id=TRIP_B, local_date="2026-10-07", source_version="9:x")
    assert svc._cache[0].query_hmac == svc._cache[1].query_hmac


# --- production check/store paths -------------------------------------------

NOW_DAY1 = datetime(2026, 10, 6, 3, 0, tzinfo=timezone.utc)  # 10:00 ICT Oct 6
NOW_DAY2 = NOW_DAY1 + timedelta(days=1)


@pytest.fixture()
def clean_singleton():
    cache_service.clear_all()
    yield
    cache_service.clear_all()


def _trip(trip_id: str, version: int = 1) -> TripState:
    node = TripNode(
        venue_name=VENUE,
        venue_id="wat_xieng_thong",
        scheduled_start=NOW_DAY2 + timedelta(days=2),
    )
    return TripState(
        trip_id=trip_id, user_id=USER, geo_region=REGION, nodes=[node], version=version
    )


def _state(trip: TripState, now_utc: datetime, response: str = PROSE) -> dict:
    return {
        "trip_state": trip,
        "event_type": "change_mood",
        "message": QUERY,
        "now_utc": now_utc,
        "routing_tier": RoutingTier.LIGHT,
        "from_cache": False,
        "user_id": USER,
        "response": response,
    }


def test_cache_scope_uses_trip_local_date_and_source_version():
    trip = _trip(TRIP_A, version=3)
    scope = state_machine._cache_scope(_state(trip, NOW_DAY1))
    assert scope["trip_id"] == TRIP_A
    assert scope["local_date"] == _local_date_of(NOW_DAY1, scope["geo_region"]).isoformat()
    assert scope["local_date"] == "2026-10-06"
    assert scope["source_version"] == f"3:{_CATALOG_VERSION}"
    assert scope["venue_name"] == VENUE
    assert scope["geo_region"] == REGION


def test_production_paths_hit_same_context_and_miss_on_trip_date_version(clean_singleton):
    state_machine._store_light_response(_state(_trip(TRIP_A), NOW_DAY1))
    assert len(cache_service._cache) == 1

    same = state_machine._node_check_cache(_state(_trip(TRIP_A), NOW_DAY1, response=""))
    assert same["from_cache"] is True and same["response"] == PROSE

    other_trip = state_machine._node_check_cache(_state(_trip(TRIP_B), NOW_DAY1, response=""))
    assert other_trip["from_cache"] is False

    next_day = state_machine._node_check_cache(_state(_trip(TRIP_A), NOW_DAY2, response=""))
    assert next_day["from_cache"] is False

    bumped = state_machine._node_check_cache(
        _state(_trip(TRIP_A, version=2), NOW_DAY1, response="")
    )
    assert bumped["from_cache"] is False
