"""SPEC-43 Gap 8: the in-memory semantic cache stores an HMAC, not the question.

Private SemanticCacheService with a known key; the singleton's random key
is irrelevant here. No widgets, no live Postgres.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re

import pytest

from services.cache_service import SemanticCacheService, hmac_query

KEY = b"g8-hmac-test-key"
CANARY = "CANARY-g8-hmac-what-is-my-booking-code-XYZ"
USER = "user-g8-hmac"
OTHER = "user-g8-hmac-other"
REGION = "luang_prabang_laos"
VENUE = "Wat Xieng Thong"
PROSE = "Your booking is at the front desk."


@pytest.fixture()
def svc() -> SemanticCacheService:
    return SemanticCacheService(hmac_key=KEY)


def _store(svc: SemanticCacheService, query: str = CANARY, identity: str = USER) -> None:
    svc.store_response(query, PROSE, identity_scope=identity, geo_region=REGION, venue_name=VENUE)


def _check(svc: SemanticCacheService, query: str = CANARY, identity: str = USER):
    return svc.check_cache(query, identity_scope=identity, geo_region=REGION, venue_name=VENUE)


def _dump(svc: SemanticCacheService) -> str:
    parts = []
    for entry in svc._cache:
        parts.append(repr(entry))
        parts.append(repr(vars(entry)))
        parts.append(json.dumps(vars(entry), default=str))
        parts.extend(str(v) for v in vars(entry).values())
    return "\n".join(parts)


def test_cache_does_not_store_raw_query_text(svc):
    _store(svc)
    assert len(svc._cache) == 1
    entry = svc._cache[0]

    dumped = _dump(svc)
    assert CANARY not in dumped
    assert "booking-code" not in dumped
    assert not hasattr(entry, "query_text")
    assert re.fullmatch(r"[0-9a-f]{64}", entry.query_hmac)
    assert entry.query_hmac == hmac.new(KEY, CANARY.encode("utf-8"), hashlib.sha256).hexdigest()

    # Matching still works from the request-time embedding.
    assert _check(svc)[0] == PROSE


def test_cache_hmac_is_stable_for_the_same_query(svc):
    _store(svc)
    _store(svc)
    first, second = (e.query_hmac for e in svc._cache)
    assert first == second
    assert hmac_query(CANARY, KEY) == hmac_query(CANARY, KEY) == first
    assert hmac_query(CANARY + "?", KEY) != first
    assert hmac_query(CANARY, b"another-key") != first


def test_identity_isolation_still_holds(svc):
    _store(svc, identity=USER)
    assert _check(svc, identity=OTHER) is None
    assert _check(svc, identity=USER)[0] == PROSE


@pytest.mark.parametrize("identity", ["", "   ", "anonymous", None])
def test_unusable_identity_still_stores_nothing(svc, identity):
    _store(svc, identity=identity)
    assert svc._cache == []
    assert _check(svc, identity=identity) is None


def test_default_service_mints_a_process_key():
    a, b = SemanticCacheService(), SemanticCacheService()
    assert isinstance(a._hmac_key, bytes) and len(a._hmac_key) == 32
    assert a._hmac_key != b._hmac_key
    a.store_response(CANARY, PROSE, identity_scope=USER, geo_region=REGION, venue_name=VENUE)
    assert CANARY not in _dump(a)
