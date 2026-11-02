"""SPEC-43 Gap 8: the semantic cache refuses restricted responses.

A response containing a Gap 10 token pattern, or a trip node's
confirmation_code / booking_notes, is never stored. Private service with a
known HMAC key; the orchestrator path is exercised against the singleton.
No widgets, no live Postgres.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

from agents.state_machine import RoutingTier, state_machine
from models.schemas import TripNode, TripState
from services.cache_service import SemanticCacheService, cache_service, response_is_restricted

KEY = b"g8-canary-test-key"
USER = "user-g8-canary"
OTHER = "user-g8-canary-other"
REGION = "luang_prabang_laos"
VENUE = "Wat Xieng Thong"
QUERY = "What time is the boat?"
CONF_CANARY = "CANARY-g8-restricted-BK-XYZ"
SK_RESPONSE = "Use sk-g8canaryRESTRICTED99 to sign in."
PROSE = "Temple opens at 08:00 by the river."


@pytest.fixture()
def svc() -> SemanticCacheService:
    return SemanticCacheService(hmac_key=KEY)


def _store(svc, response, identity=USER, needles=()):
    svc.store_response(
        QUERY,
        response,
        identity_scope=identity,
        geo_region=REGION,
        venue_name=VENUE,
        restricted_needles=needles,
    )


def _check(svc, identity=USER):
    return svc.check_cache(QUERY, identity_scope=identity, geo_region=REGION, venue_name=VENUE)


def test_cache_refuses_restricted_response_canary(svc):
    _store(svc, f"Your boat ticket reference is {CONF_CANARY}.", needles=[CONF_CANARY])
    assert svc._cache == []
    assert _check(svc) is None

    _store(svc, SK_RESPONSE)
    assert svc._cache == []
    assert _check(svc) is None
    assert all(SK_RESPONSE not in e.response_text for e in svc._cache)


def test_cache_stores_ordinary_prose_without_restricted_markers(svc):
    _store(svc, PROSE, needles=[CONF_CANARY])
    assert len(svc._cache) == 1
    entry = svc._cache[0]
    assert _check(svc)[0] == PROSE
    assert re.fullmatch(r"[0-9a-f]{64}", entry.query_hmac)
    assert not hasattr(entry, "query_text")


def test_booking_prose_and_short_needles_still_store(svc):
    _store(svc, "Your booking is at the front desk.", needles=["", None, "  ", "AB12"])
    assert len(svc._cache) == 1
    assert not response_is_restricted("Your booking is at the front desk.", ["AB12"])
    assert response_is_restricted(f"ref {CONF_CANARY}", [f"  {CONF_CANARY}  "])


def test_identity_isolation_still_holds(svc):
    _store(svc, PROSE, identity=USER)
    assert _check(svc, identity=OTHER) is None
    assert _check(svc, identity=USER)[0] == PROSE


@pytest.mark.parametrize("identity", ["", "   ", "anonymous", None])
def test_unusable_identity_still_stores_nothing(svc, identity):
    _store(svc, PROSE, identity=identity)
    assert svc._cache == []
    assert _check(svc, identity=identity) is None


@pytest.fixture()
def clean_singleton():
    cache_service.clear_all()
    yield
    cache_service.clear_all()


def _light_state(response: str, **node_fields) -> dict:
    now = datetime.now(timezone.utc)
    node = TripNode(
        venue_name=VENUE,
        venue_id="wat_xieng_thong",
        scheduled_start=now + timedelta(hours=1),
        **node_fields,
    )
    trip = TripState(trip_id="trip-g8-canary", user_id=USER, geo_region=REGION, nodes=[node])
    return {
        "trip_state": trip,
        "event_type": "change_mood",
        "message": QUERY,
        "now_utc": now,
        "routing_tier": RoutingTier.LIGHT,
        "from_cache": False,
        "user_id": USER,
        "response": response,
    }


def test_orchestrator_store_passes_node_confirmation_code(clean_singleton):
    state = _light_state(f"Show {CONF_CANARY} at the pier.", confirmation_code=CONF_CANARY)
    before = len(cache_service._cache)
    state_machine._store_light_response(state)
    assert len(cache_service._cache) == before


def test_orchestrator_store_passes_node_booking_notes(clean_singleton):
    notes = "Pier 3, seat 14C, pay cash"
    state = _light_state(f"Remember: {notes}.", booking_notes=notes)
    state_machine._store_light_response(state)
    assert cache_service._cache == []


def test_orchestrator_store_still_caches_ordinary_prose(clean_singleton):
    state = _light_state(PROSE, confirmation_code=CONF_CANARY)
    state_machine._store_light_response(state)
    assert len(cache_service._cache) == 1
    assert cache_service._cache[0].response_text == PROSE
