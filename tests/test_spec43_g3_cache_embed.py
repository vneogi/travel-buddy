"""SPEC-43 Gap 3: the semantic cache never ships a booking canary to the
embedding provider, on check or store.

No network: litellm.embedding is a capture double. The cache module's
embedding_service is swapped for a private API-mode EmbeddingService, and
calls go through SemanticCacheService.check_cache / store_response (R17).
"""

import hashlib
import hmac
import importlib
import json
from types import SimpleNamespace

import pytest

from agents.state_machine import TripStateMachine
from models.schemas import RoutingTier
from monitoring.redact import REDACTED
from services.cache_service import SemanticCacheService, hmac_query
from services.embedding_service import EmbeddingService

PNR = "G3-CANARY-PNR-9f3a"
QUERY = f"What time is {PNR} at the pier?"
KEY = b"g3-cache-embed-test-key-0123456789"
SCOPE = {
    "identity_scope": "user-g3-cache",
    "geo_region": "luang_prabang",
    "venue_name": "Wat Xieng Thong",
}


@pytest.fixture
def sent(monkeypatch):
    import litellm

    calls = []

    def fake_embedding(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(data=[{"embedding": [0.1, 0.2, 0.3]}])

    monkeypatch.setattr(litellm, "embedding", fake_embedding)
    # importlib: the services package attribute shadows the submodule name.
    cache_module = importlib.import_module("services.cache_service")
    monkeypatch.setattr(cache_module, "embedding_service", EmbeddingService(use_synthetic=False))
    return calls


def _cache():
    return SemanticCacheService(hmac_key=KEY)


def test_cache_api_embedding_omits_booking_canary(sent):
    assert _cache().check_cache(QUERY, restricted_needles=[PNR], **SCOPE) is None
    assert len(sent) == 1
    dumped = json.dumps(sent[0]["input"])
    assert PNR not in dumped
    assert REDACTED in dumped
    assert "at the pier" in dumped


def test_cache_store_embedding_omits_booking_canary(sent):
    cache = _cache()
    cache.store_response(QUERY, "The ferry leaves at 09:00.", restricted_needles=[PNR], **SCOPE)
    assert len(sent) == 1
    dumped = json.dumps(sent[0]["input"])
    assert PNR not in dumped
    assert REDACTED in dumped
    # The response text is stored as-is (not redacted).
    assert cache._cache[0].response_text == "The ferry leaves at 09:00."


def test_cache_hmac_uses_original_query(sent):
    cache = _cache()
    cache.store_response(QUERY, "ok", restricted_needles=[PNR], **SCOPE)
    expected = hmac.new(KEY, QUERY.encode("utf-8"), hashlib.sha256).hexdigest()
    assert hmac_query(QUERY, KEY) == expected
    assert cache._cache[0].query_hmac == expected
    redacted_query = QUERY.replace(PNR, REDACTED)
    assert cache._cache[0].query_hmac != hmac_query(redacted_query, KEY)


def test_cache_round_trip_still_hits_with_needles(sent):
    cache = _cache()
    cache.store_response(QUERY, "ok", restricted_needles=[PNR], **SCOPE)
    hit = cache.check_cache(QUERY, restricted_needles=[PNR], **SCOPE)
    assert hit is not None and hit[0] == "ok"
    assert all(PNR not in json.dumps(c["input"]) for c in sent)


def test_synthetic_generate_embedding_ignores_needles():
    svc = EmbeddingService(use_synthetic=True)
    assert svc.generate_embedding(QUERY, restricted_needles=[PNR]) == svc._synthetic_embedding(
        QUERY
    )


def test_api_generate_embedding_forwards_needles(sent):
    EmbeddingService(use_synthetic=False).generate_embedding(QUERY, restricted_needles=[PNR])
    assert PNR not in json.dumps(sent[0]["input"])


def test_orchestrator_check_cache_receives_restricted_needles(monkeypatch):
    sm_module = importlib.import_module("agents.state_machine")
    seen = {}

    def fake_check_cache(query, **kwargs):
        seen["query"] = query
        seen.update(kwargs)
        return None

    monkeypatch.setattr(sm_module.cache_service, "check_cache", fake_check_cache)
    monkeypatch.setattr(TripStateMachine, "_cache_scope", lambda self, state: {})
    node = SimpleNamespace(confirmation_code=PNR, booking_notes="Window seat G3-NOTE")
    state = {
        "trip_state": SimpleNamespace(nodes=[node]),
        "routing_tier": RoutingTier.LIGHT,
        "event_type": "ask_info",
        "message": QUERY,
        "user_id": "user-g3-cache",
    }
    TripStateMachine()._node_check_cache(state)
    assert seen["query"] == QUERY
    assert seen["restricted_needles"] == [PNR, "Window seat G3-NOTE"]
