"""SPEC-43 Gap 8: expired in-memory cache entries are deleted, not skipped.

check_cache and store_response both purge expired rows first. Private
service with a known HMAC key; expires_at set explicitly. No widgets, no
live Postgres.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services.cache_service import SemanticCacheService

KEY = b"g8-purge-test-key"
USER = "user-g8-purge"
OTHER = "user-g8-purge-other"
REGION = "luang_prabang_laos"
VENUE = "Wat Xieng Thong"
QUERY = "What time is the boat?"
PROSE = "The boat leaves at 09:30 from the pier."
PAST = datetime(2000, 1, 1, tzinfo=timezone.utc)


@pytest.fixture()
def svc() -> SemanticCacheService:
    return SemanticCacheService(hmac_key=KEY)


def _store(svc, query=QUERY, response=PROSE, identity=USER, needles=()):
    svc.store_response(
        query,
        response,
        identity_scope=identity,
        geo_region=REGION,
        venue_name=VENUE,
        restricted_needles=needles,
    )


def _check(svc, query=QUERY, identity=USER):
    return svc.check_cache(query, identity_scope=identity, geo_region=REGION, venue_name=VENUE)


def _dump(svc) -> str:
    return "\n".join(f"{e!r} {vars(e)!r}" for e in svc._cache)


def test_cache_deletes_expired_entries_on_check(svc):
    _store(svc)
    assert len(svc._cache) == 1
    svc._cache[0].expires_at = PAST

    assert _check(svc) is None
    assert svc._cache == []
    assert PROSE not in _dump(svc)


def test_cache_deletes_expired_entries_on_store(svc):
    q1, q2, q3 = QUERY, "Where is the night market?", "Is the museum open on Monday?"
    _store(svc, query=q1, response="first answer")
    _store(svc, query=q2, response="second answer")
    assert len(svc._cache) == 2
    expired, fresh = svc._cache
    expired.expires_at = PAST

    _store(svc, query=q3, response="third answer")
    responses = [e.response_text for e in svc._cache]
    assert "first answer" not in responses
    assert expired not in svc._cache
    assert fresh in svc._cache
    assert responses == ["second answer", "third answer"]
    assert _check(svc, query=q1) is None


def test_unexpired_entry_survives_check(svc):
    _store(svc)
    svc._cache[0].expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    assert _check(svc)[0] == PROSE
    assert len(svc._cache) == 1


def test_identity_isolation_still_holds(svc):
    _store(svc, identity=USER)
    assert _check(svc, identity=OTHER) is None
    assert _check(svc, identity=USER)[0] == PROSE


@pytest.mark.parametrize("identity", ["", "   ", "anonymous", None])
def test_unusable_identity_stores_nothing_but_still_purges(svc, identity):
    _store(svc, identity=OTHER)
    svc._cache[0].expires_at = PAST
    _store(svc, identity=identity)
    assert svc._cache == []

    _store(svc, identity=OTHER)
    svc._cache[0].expires_at = PAST
    assert _check(svc, identity=identity) is None
    assert svc._cache == []


def test_restricted_response_refusal_still_holds(svc):
    canary = "CANARY-g8-restricted-BK-XYZ"
    _store(svc, response=f"Show {canary} at the pier.", needles=[canary])
    _store(svc, response="Use sk-g8purgeRESTRICTED77 to sign in.")
    assert svc._cache == []


def test_purge_does_not_change_ttl_setting():
    from config.settings import settings

    svc = SemanticCacheService(hmac_key=KEY)
    _store(svc)
    entry = svc._cache[0]
    assert entry.expires_at - entry.created_at == timedelta(hours=settings.cache_ttl_hours)
