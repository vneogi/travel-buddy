"""SPEC-43 Gap 4 slice 9: in-process cache purge units. No network."""

import ast
import importlib
from pathlib import Path

import pytest

from monitoring.cost_tracker import CostTracker
from services import data_rights_cache_purge as purge_module
from services.cache_service import CacheEntry, SemanticCacheService
from services.data_rights_cache_purge import purge_identity_caches

USER_A = "user-g4-purge-A-71c3"
USER_B = "user-g4-purge-B-0d9e"
KEY = b"g4-purge-test-hmac-key-0123456789"


def _entry(scope, n=0):
    return CacheEntry(
        query_hmac=f"h-{scope}-{n}",
        response_text=f"answer {n}",
        embedding=[0.0, 1.0],
        identity_scope=scope,
    )


def _semantic(**counts):
    svc = SemanticCacheService(hmac_key=KEY)
    for scope, n in counts.items():
        for i in range(n):
            svc._cache.append(_entry(scope, i))
    return svc


def _scopes(svc):
    return sorted(e.identity_scope for e in svc._cache)


def test_semantic_cache_clear_identity_removes_only_that_scope():
    svc = _semantic(**{USER_A: 3, USER_B: 2})
    svc.total_hits, svc.total_misses = 7, 5
    assert svc.clear_identity(f"  {USER_A}  ") == 3
    assert _scopes(svc) == [USER_B, USER_B]
    assert (svc.total_hits, svc.total_misses) == (7, 5)
    assert svc.clear_identity(USER_A) == 0


@pytest.mark.parametrize("bad", [None, "", "   ", "anonymous"])
def test_semantic_cache_clear_identity_blank_or_anonymous_is_noop(bad):
    svc = _semantic(**{USER_A: 2, USER_B: 1})
    svc._cache.append(_entry("anonymous"))  # even a stray entry stays
    before = _scopes(svc)
    assert svc.clear_identity(bad) == 0
    assert _scopes(svc) == before


def test_cost_tracker_clear_user_removes_only_that_user():
    costs = CostTracker()
    for _ in range(3):
        costs.record_cache_hit(USER_A)
    costs.record_api_call(USER_A, "places")
    costs.record_cache_hit(USER_B)
    costs.record_api_call(USER_B, "places")
    assert costs.clear_user(USER_A) == 4
    assert sorted(e.user_id for e in costs._events) == [USER_B, USER_B]
    assert costs.clear_user(USER_A) == 0


@pytest.mark.parametrize("bad", [None, "", "   ", 42])
def test_cost_tracker_clear_user_rejects_blank(bad):
    costs = CostTracker()
    costs.record_cache_hit(USER_A)
    with pytest.raises(ValueError):
        costs.clear_user(bad)
    assert len(costs._events) == 1


class _Recorder:
    def __init__(self, calls):
        self.calls = calls

    def clear_identity(self, scope):
        self.calls.append(("semantic_cache", scope))
        return 2

    def clear_user(self, user_id):
        self.calls.append(("cost_events", user_id))
        return 5


def test_purge_identity_caches_calls_all_three_in_order():
    calls = []
    rec = _Recorder(calls)
    out = purge_identity_caches(
        USER_A,
        semantic_cache=rec,
        costs=rec,
        reset_budget=lambda uid: calls.append(("ask_budget", uid)),
    )
    assert out == {"semantic_cache": 2, "cost_events": 5, "ask_budget": True}
    assert calls == [("semantic_cache", USER_A), ("cost_events", USER_A), ("ask_budget", USER_A)]


@pytest.mark.parametrize("bad", [None, "", "   ", 42])
def test_purge_identity_caches_rejects_blank_before_any_call(bad):
    calls = []
    rec = _Recorder(calls)
    with pytest.raises(ValueError):
        purge_identity_caches(
            bad, semantic_cache=rec, costs=rec, reset_budget=lambda u: calls.append(u)
        )
    assert calls == []


def test_purge_identity_caches_does_not_swallow_store_errors():
    class Boom(_Recorder):
        def clear_user(self, user_id):
            raise RuntimeError("store down")

    calls = []
    with pytest.raises(RuntimeError):
        purge_identity_caches(
            USER_A, semantic_cache=Boom(calls), costs=Boom(calls), reset_budget=calls.append
        )
    assert calls == [("semantic_cache", USER_A)]


def test_purge_defaults_use_the_process_singletons(monkeypatch):
    ask = importlib.import_module("services.ask_service")
    cache_mod = importlib.import_module("services.cache_service")
    cost_mod = importlib.import_module("monitoring.cost_tracker")
    entry = _entry(USER_A)
    monkeypatch.setattr(cache_mod.cache_service, "_cache", [entry, _entry(USER_B)])
    monkeypatch.setattr(cost_mod.cost_tracker, "_events", [])
    cost_mod.cost_tracker.record_cache_hit(USER_A)
    ask._shared_budget._counts[USER_A] = 3
    try:
        out = purge_identity_caches(USER_A)
        assert out == {"semantic_cache": 1, "cost_events": 1, "ask_budget": True}
        assert USER_A not in ask._shared_budget._counts
        assert [e.identity_scope for e in cache_mod.cache_service._cache] == [USER_B]
    finally:
        ask._shared_budget._counts.pop(USER_A, None)


def test_purge_module_has_no_supabase_import():
    source = Path(purge_module.__file__).read_text(encoding="utf-8")
    assert source.isascii()
    roots = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            roots.add((node.module or "").split(".")[0])
    assert roots <= {"__future__", "importlib", "typing"}, roots
    assert "supabase" not in source.split('"""', 2)[2]
    assert "print(" not in source and "import logging" not in source
    assert "error_log" not in source.split('"""', 2)[2]


def test_ask_cache_is_not_cleared_by_purge(monkeypatch):
    ask = importlib.import_module("services.ask_service")
    cache_mod = importlib.import_module("services.cache_service")
    cost_mod = importlib.import_module("monitoring.cost_tracker")
    monkeypatch.setattr(cache_mod.cache_service, "_cache", [])
    monkeypatch.setattr(cost_mod.cost_tracker, "_events", [])
    key = "g4-purge-ask-cache-probe"
    ask._shared_cache._store[key] = object()
    try:
        before = ask._shared_cache.size()
        purge_identity_caches(USER_A)
        assert ask._shared_cache.size() == before
        assert key in ask._shared_cache._store
    finally:
        ask._shared_cache._store.pop(key, None)
