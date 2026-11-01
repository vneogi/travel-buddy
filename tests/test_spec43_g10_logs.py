"""SPEC-43 Gap 10: redact secrets in the error ring; refuse debug on Cloud Run.

In-process only: no widgets, no live Postgres.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

import main
from config.settings import settings
from main import app, assert_production_debug_off
from monitoring.error_log import error_log
from monitoring.redact import REDACTED, redact_secrets

KEY_CANARY = "sk-test-CANARY-KEY-9f3a"
URL_CANARY = "https://maps.googleapis.com/maps/api/foo?key=AIzaSyCanaryKey"

_router = APIRouter()


@_router.get("/api/v1/_test/g10_crash")
async def _g10_crash():
    raise RuntimeError(URL_CANARY)


app.include_router(_router)


@pytest.fixture(autouse=True)
def _clear_ring():
    error_log.clear()
    yield
    error_log.clear()


def test_error_ring_redacts_secret_canary():
    error_log.record(
        request_id="req-g10",
        method="GET",
        path="/api/v1/x",
        status=500,
        exc_type="RuntimeError",
        message=f"provider call failed key={KEY_CANARY} url={URL_CANARY}",
        traceback_str=(
            "Traceback (most recent call last):\n"
            f'  File "x.py", line 1, in call\n    api_key = "{KEY_CANARY}"\n'
            f"RuntimeError: GET {URL_CANARY} -> 403\n"
        ),
    )
    dumped = json.dumps(error_log.recent())
    assert KEY_CANARY not in dumped
    assert URL_CANARY not in dumped
    assert "AIzaSyCanaryKey" not in dumped
    assert REDACTED in dumped
    # Non-secret fields are kept for diagnosis.
    entry = error_log.recent()[0]
    assert entry["exc_type"] == "RuntimeError"
    assert entry["path"] == "/api/v1/x" and entry["request_id"] == "req-g10"


def test_unhandled_crash_with_maps_url_canary_is_redacted(caplog):
    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="travelbuddy"):
        r = client.get("/api/v1/_test/g10_crash")
    assert r.status_code == 500
    body = r.json()
    assert body["detail"] == "Internal server error"
    assert "request_id" in body
    assert URL_CANARY not in r.text and "AIzaSyCanaryKey" not in r.text

    dumped = json.dumps(error_log.recent())
    assert error_log.count() == 1
    assert URL_CANARY not in dumped and "AIzaSyCanaryKey" not in dumped
    assert REDACTED in dumped

    logged = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "Unhandled RuntimeError" in logged
    assert "AIzaSyCanaryKey" not in logged


def test_settings_literal_secret_is_redacted(monkeypatch):
    literal = "plain-literal-secret-value-7781"
    monkeypatch.setattr(settings, "stripe_secret_key", literal)
    error_log.record(
        request_id="r",
        method="POST",
        path="/p",
        status=500,
        exc_type="ValueError",
        message=f"stripe rejected {literal}",
        traceback_str=f"ValueError: {literal}",
    )
    assert literal not in json.dumps(error_log.recent())


@pytest.mark.parametrize(
    "raw, leaked",
    [
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig", "eyJhbGciOiJIUzI1NiJ9"),
        ("GET /x?api_key=abc123SECRET&q=1", "abc123SECRET"),
        ("GET /x?key=AIzaSyRealLookingKey000&y=2", "AIzaSyRealLookingKey000"),
        ("using sk-live-0123456789abcdef for llm", "sk-live-0123456789abcdef"),
    ],
)
def test_redact_patterns(raw, leaked):
    out = redact_secrets(raw)
    assert leaked not in out
    assert REDACTED in out


def test_benign_text_is_unchanged():
    assert redact_secrets("Deliberate test crash") == "Deliberate test crash"
    assert redact_secrets("") == ""


def test_cloud_run_with_debug_refuses_to_start(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "travel-buddy")
    monkeypatch.setattr(settings, "debug", True)
    with pytest.raises(RuntimeError, match="Cloud Run"):
        assert_production_debug_off()


def test_cloud_run_with_debug_off_starts(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "travel-buddy")
    monkeypatch.setattr(settings, "debug", False)
    assert_production_debug_off()


def test_no_k_service_allows_debug(monkeypatch):
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.setattr(settings, "debug", True)
    assert_production_debug_off()


def test_lifespan_calls_debug_guard_before_seeding(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(main, "assert_production_debug_off", lambda: calls.append("guard"))
    monkeypatch.setattr(main, "seed_venues", lambda: (calls.append("seed"), (0, "test"))[1])

    async def run():
        async with main._lifespan(app):
            pass

    import asyncio

    asyncio.run(run())
    assert calls[:2] == ["guard", "seed"]
