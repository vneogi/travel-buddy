"""SPEC-43 Gap 3: an embedding provider failure writes no provider text.

Provider exceptions can echo the request input. The safety net logs the
exception class name only and still returns the synthetic vector. No network:
litellm.embedding is a double that raises.
"""

import logging

import litellm
import pytest

from config.settings import settings
from monitoring.spend_circuit import SpendCircuit
from services.embedding_service import EmbeddingService

CANARY = "EMBED-CANARY-g3-print"


@pytest.fixture
def failing_provider(monkeypatch):
    import importlib

    calls = []

    def boom(**kwargs):
        calls.append(kwargs)
        raise RuntimeError(f"{CANARY} echo of input")

    monkeypatch.setattr(litellm, "embedding", boom)
    # importlib: the services package attribute may shadow the submodule.
    emb_module = importlib.import_module("services.embedding_service")
    monkeypatch.setattr(emb_module, "configure_provider_keys", lambda: None)
    return calls


def _svc():
    return EmbeddingService(
        use_synthetic=False,
        circuit=SpendCircuit(max_process_usd=1e9, max_identity_usd=1e9),
    )


def _all_log_text(caplog):
    parts = [caplog.text]
    for record in caplog.records:
        parts.append(record.getMessage())
        parts.append(str(record.msg))
        parts.append(repr(record.args))
        if record.exc_info:
            parts.append(repr(record.exc_info))
        if record.exc_text:
            parts.append(record.exc_text)
    return "\n".join(parts)


def test_api_embedding_failure_does_not_leak_exception_text(failing_provider, capsys, caplog):
    caplog.set_level(logging.WARNING)
    svc = _svc()
    capsys.readouterr()

    vec = svc.generate_embedding("hello", user_id="u")

    out = capsys.readouterr()
    assert failing_provider, "provider double was not called"
    assert isinstance(vec, list)
    assert len(vec) == settings.embedding_dimensions
    assert vec == svc._synthetic_embedding("hello")
    assert CANARY not in out.out
    assert CANARY not in out.err
    assert out.out == ""
    assert CANARY not in _all_log_text(caplog)


def test_api_embedding_failure_logs_class_name_warning(failing_provider, caplog):
    caplog.set_level(logging.WARNING, logger="travelbuddy")
    _svc().generate_embedding("hello", user_id="u")
    warnings = [
        r for r in caplog.records if r.name == "travelbuddy" and r.levelno == logging.WARNING
    ]
    assert warnings
    assert any("RuntimeError" in r.getMessage() for r in warnings)
    assert all(CANARY not in r.getMessage() for r in warnings)
