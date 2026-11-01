"""SPEC-43 Gap 11: in-process provider-spend circuit.

Private SpendCircuit instances only; the installed default is untouched.
LiteLLM is stubbed (no network). Costs are deterministic via
LLMService._calculate_cost.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import litellm
import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from monitoring import spend_circuit as spend_module
from monitoring.spend_circuit import (
    MAX_IDENTITY_USD,
    MAX_PROCESS_USD,
    SPEND_CAPPED,
    SPEND_WINDOW_S,
    SpendCapped,
    SpendCircuit,
    estimate_messages_tokens,
    normalize_identity,
)
from services.embedding_service import EmbeddingService
from services.llm_service import LLMService

PROMPT = "PROMPT-CANARY-g11 what temples are near me"
MESSAGES = [{"role": "user", "content": PROMPT}]
LIGHT = "gpt-4o-mini"
USAGE_IN, USAGE_OUT = 1000, 1000
MAX_TOKENS = 100


def _response(content: str = "ok"):
    usage = SimpleNamespace(
        prompt_tokens=USAGE_IN, completion_tokens=USAGE_OUT, total_tokens=USAGE_IN + USAGE_OUT
    )
    return SimpleNamespace(
        usage=usage, choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


@pytest.fixture()
def acompletion_calls(monkeypatch):
    calls: list[str] = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs["model"])
        return _response()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    return calls


def _complete(svc: LLMService, user_id, model: str = LIGHT, tier: str = "light"):
    return asyncio.run(
        svc.complete(
            MESSAGES, model=model, routing_tier=tier, max_tokens=MAX_TOKENS, user_id=user_id
        )
    )


def _cost(svc: LLMService, model: str = LIGHT) -> float:
    return svc._calculate_cost(model, {"input": USAGE_IN, "output": USAGE_OUT})


def _reserved(svc: LLMService, model: str = LIGHT) -> float:
    return svc._calculate_cost(
        model, {"input": estimate_messages_tokens(MESSAGES), "output": MAX_TOKENS}
    )


def test_excess_spend_from_one_identity_is_capped(acompletion_calls):
    probe = LLMService()
    n = 3
    # Exactly n successes fit: n-1 actuals + reserve < cap <= n actuals + reserve.
    cap = n * _cost(probe) + _reserved(probe)
    circuit = SpendCircuit(max_process_usd=1e9, max_identity_usd=cap, window_s=SPEND_WINDOW_S)
    svc = LLMService(circuit=circuit)

    for _ in range(n):
        assert _complete(svc, "User-A ")["content"] == "ok"
    assert len(acompletion_calls) == n
    assert circuit.spent("user-a") == pytest.approx(n * _cost(probe))

    with pytest.raises(SpendCapped):
        _complete(svc, "user-a")
    assert len(acompletion_calls) == n  # N, not N+1

    # Another identity still has budget (process cap is huge).
    _complete(svc, "user-b")
    assert len(acompletion_calls) == n + 1


def test_spend_circuit_is_not_bypassed_by_new_identity(acompletion_calls):
    probe = LLMService()
    n = 3
    cap = n * _cost(probe) + _reserved(probe)
    circuit = SpendCircuit(max_process_usd=cap, max_identity_usd=1e9, window_s=SPEND_WINDOW_S)
    svc = LLMService(circuit=circuit)

    for i in range(n):
        _complete(svc, f"rotating-user-{i}")
    assert len(acompletion_calls) == n
    assert circuit.spent() == pytest.approx(n * _cost(probe))

    for fresh in ("brand-new-uuid-1", "brand-new-uuid-2", "", None):
        with pytest.raises(SpendCapped):
            _complete(svc, fresh)
    assert len(acompletion_calls) == n


def test_fallback_chain_does_not_retry_next_model_on_spend_cap(acompletion_calls):
    probe = LLMService()
    first, second, third = LLMService.HEAVY_FALLBACK
    r_first, r_third = _reserved(probe, first), _reserved(probe, third)
    assert r_third < r_first
    spent_first = _cost(probe, first)
    # After one first-model success: the first model's reserve no longer fits,
    # but a cheaper later model's reserve WOULD fit if the reject were swallowed.
    cap = spent_first + (r_first + r_third) / 2
    circuit = SpendCircuit(max_process_usd=1e9, max_identity_usd=cap)
    svc = LLMService(circuit=circuit)

    _complete(svc, "u", model=first, tier="heavy")
    assert acompletion_calls == [first]

    with pytest.raises(SpendCapped):
        _complete(svc, "u", model=first, tier="heavy")
    assert acompletion_calls == [first]
    assert second not in acompletion_calls and third not in acompletion_calls


def test_provider_error_still_falls_back(monkeypatch):
    first, second, _ = LLMService.HEAVY_FALLBACK
    calls: list[str] = []

    async def flaky(**kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"] == first:
            raise RuntimeError("provider down")
        return _response()

    monkeypatch.setattr(litellm, "acompletion", flaky)
    svc = LLMService(circuit=SpendCircuit(max_process_usd=1e9, max_identity_usd=1e9))
    out = _complete(svc, "u", model=first, tier="heavy")
    assert out["model_used"] == second
    assert calls == [first, second]


def test_reserved_cost_blocks_a_large_completion_before_any_spend(acompletion_calls):
    svc = LLMService(circuit=SpendCircuit(max_process_usd=1e9, max_identity_usd=1e-6))
    with pytest.raises(SpendCapped):
        _complete(svc, "fresh-user")
    assert acompletion_calls == []


def test_allow_is_read_only_and_record_counts_actual_only():
    circuit = SpendCircuit(max_process_usd=1.0, max_identity_usd=1.0)
    assert circuit.allow("x", 0.5)
    assert circuit.allow("x", 0.5)
    assert circuit.spent("x") == 0 and circuit.spent() == 0
    circuit.record("X ", 0.25)
    assert circuit.spent("x") == pytest.approx(0.25)
    assert circuit.spent() == pytest.approx(0.25)
    assert not circuit.allow("x", 0.75)
    assert circuit.allow("x", 0.74)


def test_window_expires_old_spend():
    now = [1000.0]
    circuit = SpendCircuit(
        max_process_usd=1.0, max_identity_usd=1.0, window_s=60, clock=lambda: now[0]
    )
    circuit.record("x", 0.99)
    assert not circuit.allow("x", 0.02)
    now[0] += 61
    assert circuit.allow("x", 0.02)
    assert circuit.spent("x") == 0


def test_synthetic_embedding_does_not_call_litellm_or_record(monkeypatch):
    called: list[bool] = []
    monkeypatch.setattr(litellm, "embedding", lambda **kw: called.append(True))
    circuit = SpendCircuit(max_process_usd=1e-12, max_identity_usd=1e-12)
    svc = EmbeddingService(use_synthetic=True, circuit=circuit)
    vec = svc.generate_embedding("hello", user_id="u")
    assert len(vec) == svc.dimensions
    assert called == []
    assert circuit.spent() == 0


def test_api_embedding_spend_cap_raises_without_synthetic_fallback(monkeypatch):
    called: list[bool] = []

    def fake_embedding(**kw):
        called.append(True)
        return SimpleNamespace(data=[{"embedding": [0.1] * 4}])

    monkeypatch.setattr(litellm, "embedding", fake_embedding)
    circuit = SpendCircuit(max_process_usd=1e-12, max_identity_usd=1e9)
    svc = EmbeddingService(use_synthetic=False, circuit=circuit)
    monkeypatch.setattr(
        svc, "_synthetic_embedding", lambda text: pytest.fail("must not fall back to synthetic")
    )
    with pytest.raises(SpendCapped):
        svc.generate_embedding("hello", user_id="u")
    assert called == []


def test_api_embedding_under_cap_calls_and_records(monkeypatch):
    monkeypatch.setattr(
        litellm, "embedding", lambda **kw: SimpleNamespace(data=[{"embedding": [0.1] * 4}])
    )
    circuit = SpendCircuit(max_process_usd=1.0, max_identity_usd=1.0)
    svc = EmbeddingService(use_synthetic=False, circuit=circuit)
    assert svc.generate_embedding("hello there", user_id="U") == [0.1] * 4
    assert circuit.spent("u") > 0 and circuit.spent() > 0


def test_batch_embeddings_and_stream_are_gated(monkeypatch):
    called: list[str] = []

    async def fake_aembedding(**kw):
        called.append("aembedding")
        return SimpleNamespace(data=[{"embedding": [0.0]}])

    async def fake_acompletion(**kw):
        called.append("stream")
        raise AssertionError("must not be called")

    monkeypatch.setattr(litellm, "aembedding", fake_aembedding)
    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    svc = LLMService(circuit=SpendCircuit(max_process_usd=1e-12, max_identity_usd=1e9))

    with pytest.raises(SpendCapped):
        asyncio.run(svc.batch_embeddings(["a", "b"], user_id="u"))

    async def drain():
        async for _ in svc.stream_response(MESSAGES, user_id="u"):
            pass

    with pytest.raises(SpendCapped):
        asyncio.run(drain())
    assert called == []


def test_reject_detail_has_no_prompt_key_or_usd(acompletion_calls, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "litellm_api_key", "sk-test-SPEND-KEY-0001")
    svc = LLMService(circuit=SpendCircuit(max_process_usd=1e-12, max_identity_usd=1e9))
    with pytest.raises(SpendCapped) as exc:
        _complete(svc, "u")
    text = f"{exc.value} {exc.value!r} {exc.value.args}"
    assert str(exc.value) == SPEND_CAPPED and exc.value.detail == SPEND_CAPPED
    for leaked in (PROMPT, "PROMPT-CANARY", "sk-test-SPEND-KEY-0001", "$", "usd", LIGHT):
        assert leaked.lower() not in text.lower()


def test_spend_capped_http_response_is_stable_code():
    from main import app

    router = APIRouter()

    @router.get("/api/v1/_test/g11_spend")
    async def _capped():
        raise SpendCapped()

    app.include_router(router)
    r = TestClient(app, raise_server_exceptions=False).get("/api/v1/_test/g11_spend")
    assert r.status_code == 503
    assert set(r.json()) == {"detail", "request_id"}
    assert r.json()["detail"] == SPEND_CAPPED


def test_defaults_and_identity_normalization():
    assert (SPEND_WINDOW_S, MAX_PROCESS_USD, MAX_IDENTITY_USD) == (86400, 5.0, 1.0)
    default = spend_module.default_spend_circuit
    assert (default.max_process_usd, default.max_identity_usd, default.window_s) == (
        5.0,
        1.0,
        86400,
    )
    assert LLMService()._circuit is default
    assert normalize_identity("  User-A ") == "user-a"
    assert normalize_identity("") == "anonymous"
    assert normalize_identity(None) == "anonymous"
