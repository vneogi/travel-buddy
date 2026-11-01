"""SPEC-43 Gap 8: identity-scoped semantic cache.

Two travellers asking a similar question must not share a cached private
response. In-memory cache_service only; no live Postgres.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agents.state_machine import RoutingTier, state_machine
from models.schemas import TripNode, TripState
from services.cache_service import cache_service

QUERY = "What temples should I visit near here?"
PROSE = "Private answer for traveller A: Wat Xieng Thong at 9am."
REGION = "luang_prabang_laos"
VENUE = "Wat Xieng Thong"
USER_A = "user-a-g8"
USER_B = "user-b-g8"


@pytest.fixture(autouse=True)
def clean_cache():
    cache_service.clear_all()
    yield
    cache_service.clear_all()


def _store(identity: str, response: str = PROSE) -> None:
    cache_service.store_response(
        QUERY, response, identity_scope=identity, geo_region=REGION, venue_name=VENUE
    )


def _check(identity: str, region: str = REGION, venue: str = VENUE):
    return cache_service.check_cache(
        QUERY, identity_scope=identity, geo_region=region, venue_name=venue
    )


def test_semantic_cache_does_not_share_private_response_across_users():
    _store(USER_A)

    assert _check(USER_B) is None

    hit = _check(USER_A)
    assert hit is not None
    assert hit[0] == PROSE


def test_each_user_gets_only_their_own_entry():
    _store(USER_A, "answer A")
    _store(USER_B, "answer B")
    assert _check(USER_A)[0] == "answer A"
    assert _check(USER_B)[0] == "answer B"


@pytest.mark.parametrize("identity", ["", "   ", "anonymous", " anonymous ", None])
def test_unusable_identity_stores_nothing_and_never_hits(identity):
    before = cache_service.get_stats()["total_entries"]
    _store(identity)
    assert cache_service.get_stats()["total_entries"] == before
    assert _check(identity) is None


def test_unusable_identity_cannot_read_a_real_users_entry():
    _store(USER_A)
    for identity in ("", "anonymous"):
        assert _check(identity) is None


def test_identity_match_is_exact_after_strip():
    _store(f"  {USER_A}  ")
    assert _check(USER_A)[0] == PROSE
    assert _check(USER_A.upper()) is None


def test_geo_and_venue_isolation_hold_for_same_identity():
    _store(USER_A)
    assert _check(USER_A, region="vientiane_laos") is None
    assert _check(USER_A, venue="Mount Phousi") is None
    assert _check(USER_A)[0] == PROSE


def test_identity_scope_is_required_keyword():
    with pytest.raises(TypeError):
        cache_service.check_cache(QUERY, geo_region=REGION, venue_name=VENUE)
    with pytest.raises(TypeError):
        cache_service.store_response(QUERY, PROSE, geo_region=REGION, venue_name=VENUE)


def _light_state(user_id: str) -> dict:
    now = datetime.now(timezone.utc)
    node = TripNode(
        venue_name=VENUE, venue_id="wat_xieng_thong", scheduled_start=now + timedelta(hours=1)
    )
    trip = TripState(trip_id="trip-g8", user_id=user_id, geo_region=REGION, nodes=[node])
    return {
        "trip_state": trip,
        "event_type": "change_mood",
        "message": QUERY,
        "now_utc": now,
        "routing_tier": RoutingTier.LIGHT,
        "from_cache": False,
        "user_id": user_id,
        "response": "",
    }


def test_orchestrator_cache_node_scopes_by_state_user_id():
    state_a = _light_state(USER_A)
    node = state_a["trip_state"].nodes[0]
    geo = getattr(node, "geo_region", None) or REGION
    cache_service.store_response(
        QUERY, PROSE, identity_scope=USER_A, geo_region=geo, venue_name=VENUE
    )

    out_b = state_machine._node_check_cache(_light_state(USER_B))
    assert out_b["from_cache"] is False
    assert out_b["response"] != PROSE

    out_a = state_machine._node_check_cache(_light_state(USER_A))
    assert out_a["from_cache"] is True
    assert out_a["response"] == PROSE


def test_orchestrator_anonymous_user_never_hits():
    cache_service.store_response(
        QUERY, PROSE, identity_scope=USER_A, geo_region=REGION, venue_name=VENUE
    )
    out = state_machine._node_check_cache(_light_state("anonymous"))
    assert out["from_cache"] is False
