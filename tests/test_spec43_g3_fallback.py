"""SPEC-43 Gap 3: a provider failure never routes the prompt to another vendor.

Completions are pinned to the tier's configured model (settings.heavy_model /
settings.light_model). LiteLLM is a capture double; no network.
"""

import asyncio
from types import SimpleNamespace

import litellm
import pytest

from monitoring.spend_circuit import SpendCircuit
from services.llm_service import LLMService, UnapprovedModelError

UNAPPROVED = ("claude-3-5-sonnet-20241022", "gemini/gemini-1.5-pro")
MESSAGES = [{"role": "user", "content": "hello"}]


def _response(content="ok"):
    usage = SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2)
    return SimpleNamespace(
        usage=usage, choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _svc():
    return LLMService(circuit=SpendCircuit(max_process_usd=1e9, max_identity_usd=1e9))


@pytest.fixture
def first_call_fails(monkeypatch):
    models = []

    async def flaky(**kwargs):
        models.append(kwargs["model"])
        if len(models) == 1:
            raise RuntimeError("provider down")
        return _response(f"from {kwargs['model']}")

    monkeypatch.setattr(litellm, "acompletion", flaky)
    return models


@pytest.fixture
def always_ok(monkeypatch):
    models = []

    async def ok(**kwargs):
        models.append(kwargs["model"])
        return _response()

    monkeypatch.setattr(litellm, "acompletion", ok)
    return models


def test_heavy_complete_does_not_fallback_to_unapproved_provider(first_call_fails):
    svc = _svc()
    result = None
    with pytest.raises(RuntimeError):
        result = asyncio.run(svc.complete(MESSAGES, routing_tier="heavy", user_id="u"))
    assert result is None
    assert len(first_call_fails) <= 1
    assert first_call_fails == [svc.heavy_model]
    for name in UNAPPROVED:
        assert name not in first_call_fails


def test_light_complete_does_not_fallback(first_call_fails):
    svc = _svc()
    with pytest.raises(RuntimeError):
        asyncio.run(svc.complete(MESSAGES, routing_tier="light", user_id="u"))
    assert first_call_fails == [svc.light_model]


@pytest.mark.parametrize("model", UNAPPROVED)
def test_explicit_unapproved_heavy_model_does_not_call_litellm(always_ok, model):
    with pytest.raises(UnapprovedModelError):
        asyncio.run(_svc().complete(MESSAGES, model=model, routing_tier="heavy", user_id="u"))
    assert always_ok == []


def test_explicit_unapproved_light_model_does_not_call_litellm(always_ok):
    svc = _svc()
    # The heavy model is not approved on the light tier, and vice versa.
    with pytest.raises(UnapprovedModelError):
        asyncio.run(svc.complete(MESSAGES, model=svc.heavy_model, routing_tier="light"))
    with pytest.raises(UnapprovedModelError):
        asyncio.run(svc.complete(MESSAGES, model=svc.light_model, routing_tier="heavy"))
    assert always_ok == []


def test_unapproved_model_error_is_a_value_error():
    assert issubclass(UnapprovedModelError, ValueError)


def test_approved_models_follow_settings(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "heavy_model", "gpt-4o")
    monkeypatch.setattr(settings, "light_model", "gpt-4o-mini")
    svc = LLMService()
    assert svc.approved_models("heavy") == ("gpt-4o",)
    assert svc.approved_models("light") == ("gpt-4o-mini",)
    assert not hasattr(LLMService, "HEAVY_FALLBACK")
    assert not hasattr(LLMService, "LIGHT_FALLBACK")


def test_approved_model_success_still_returns(always_ok):
    svc = _svc()
    out = asyncio.run(svc.complete(MESSAGES, routing_tier="heavy", user_id="u"))
    assert out["model_used"] == svc.heavy_model
    assert out["content"] == "ok"
    assert always_ok == [svc.heavy_model]
