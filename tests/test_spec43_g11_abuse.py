"""SPEC-43 Gap 11: bound request body size and JSON depth in middleware.

Oversized and deeply nested payloads must fail before route handlers,
auth dependencies, Pydantic, venue search, or the orchestrator.
"""

from __future__ import annotations

import importlib
import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from agents.state_machine import TripStateMachine
from main import app
from monitoring.payload_limits import (
    MAX_BODY_BYTES,
    MAX_JSON_DEPTH,
    json_depth,
    raw_json_depth_exceeds,
)

client = TestClient(app)
HEADERS = {"X-Debug-User-Id": "user-g11", "Content-Type": "application/json"}


@pytest.fixture()
def calls(monkeypatch):
    """Record whether the trip-event handler, its auth dependency, the
    orchestrator, or signal ingest ran."""
    seen: list[str] = []
    trip_router_module = importlib.import_module("routers.trip_router")
    signal_router_module = importlib.import_module("routers.signal_router")
    original_owner = trip_router_module.require_trip_owner
    original_identity = trip_router_module.resolve_identity

    def owner_spy(*args, **kwargs):
        seen.append("trip_handler")
        return original_owner(*args, **kwargs)

    async def process_spy(self, *args, **kwargs):
        seen.append("process_event")
        raise AssertionError("orchestrator must not run in these tests")

    original_types = signal_router_module.db_service.get_valid_signal_types

    def types_spy(*args, **kwargs):
        seen.append("signal_ingest")
        return original_types(*args, **kwargs)

    def identity_spy():
        # Records that auth ran; a rejected body must never get here.
        seen.append("auth_dependency")
        raise HTTPException(status_code=401, detail="spy")

    monkeypatch.setattr(trip_router_module, "require_trip_owner", owner_spy)
    monkeypatch.setattr(TripStateMachine, "process_event", process_spy)
    monkeypatch.setattr(signal_router_module.db_service, "get_valid_signal_types", types_spy)
    app.dependency_overrides[original_identity] = identity_spy
    yield seen
    app.dependency_overrides.pop(original_identity, None)


def _nested(depth: int) -> object:
    value: object = 1
    for _ in range(depth):
        value = {"a": value}
    return value


def _event_body(padding: int = 0) -> bytes:
    body = {
        "trip_id": "trip-g11",
        "event_type": "ask_info",
        "message": "x" * padding,
    }
    return json.dumps(body).encode("utf-8")


def test_oversized_request_body_is_rejected_before_handler(calls):
    raw = _event_body(padding=MAX_BODY_BYTES + 10)
    assert len(raw) > MAX_BODY_BYTES
    r = client.post("/api/v1/trip/event", content=raw, headers=HEADERS)
    assert r.status_code == 413
    assert r.json()["detail"] == "payload_too_large"
    assert calls == []


def test_oversized_signal_batch_is_rejected_before_ingest(calls):
    raw = json.dumps({"signals": [], "pad": "y" * (MAX_BODY_BYTES + 1)}).encode()
    r = client.post("/api/v1/signals", content=raw, headers=HEADERS)
    assert r.status_code == 413
    assert r.json()["detail"] == "payload_too_large"
    assert calls == []


def test_declared_content_length_over_cap_is_rejected():
    from monitoring.payload_limits import PayloadLimitMiddleware

    called: list[bool] = []

    async def inner(scope, receive, send):
        called.append(True)

    sent: list[dict] = []
    received: list[bool] = []

    async def receive():
        received.append(True)
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/trip/event",
        "headers": [(b"content-length", str(MAX_BODY_BYTES + 1).encode())],
        "state": {"request_id": "rid-g11"},
    }
    import asyncio

    asyncio.run(PayloadLimitMiddleware(inner)(scope, receive, send))
    assert called == []
    assert received == []  # body not read
    assert sent[0]["status"] == 413
    body = json.loads(
        b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    )
    assert body == {"detail": "payload_too_large", "request_id": "rid-g11"}


def test_deeply_nested_json_is_rejected(calls):
    raw = json.dumps(
        {"trip_id": "trip-g11", "event_type": "ask_info", "preferences": _nested(MAX_JSON_DEPTH)}
    ).encode()
    assert json_depth(json.loads(raw)) == MAX_JSON_DEPTH + 1
    assert len(raw) < MAX_BODY_BYTES // 100
    r = client.post("/api/v1/trip/event", content=raw, headers=HEADERS)
    assert r.status_code == 400
    assert r.json()["detail"] == "payload_too_deep"
    assert calls == []


def test_thousand_deep_json_is_rejected_without_recursion(calls):
    raw = ("[" * 5000 + "]" * 5000).encode()
    r = client.post("/api/v1/signals", content=raw, headers=HEADERS)
    assert r.status_code == 400
    assert r.json()["detail"] == "payload_too_deep"
    assert calls == []


def test_depth_exactly_limit_is_allowed():
    value = _nested(MAX_JSON_DEPTH)
    assert json_depth(value) == MAX_JSON_DEPTH
    assert not raw_json_depth_exceeds(json.dumps(value).encode())
    assert raw_json_depth_exceeds(json.dumps({"x": value}).encode())


def test_depth_scan_ignores_brackets_inside_strings():
    raw = json.dumps({"q": '[[[[[[[[[[[[{{{{{{{{{{ \\" ]]]'}).encode()
    assert not raw_json_depth_exceeds(raw)


def test_json_depth_definition():
    assert json_depth(1) == 0
    assert json_depth({"a": {"b": 1}}) == 2
    assert json_depth([[], {}]) == 2


def test_depth_limit_accepted_by_route():
    raw = json.dumps({"signals": [], "extra": _nested(MAX_JSON_DEPTH - 1)}).encode()
    r = client.post("/api/v1/signals", content=raw, headers=HEADERS)
    assert r.status_code not in (400, 413)


def test_health_get_still_200():
    r = client.get("/api/v1/health")
    assert r.status_code == 200


def test_small_valid_post_reaches_handler(calls):
    sig = {
        "signal_id": "g11-small",
        "signal_type": "session_start",
        "place_ref": "app",
        "captured_at": "2026-11-01T00:00:00+00:00",
        "value_json": {"cold_start": True},
    }
    r = client.post("/api/v1/signals", content=json.dumps({"signals": [sig]}), headers=HEADERS)
    assert r.status_code == 401  # reached the route's auth dependency
    assert "auth_dependency" in calls  # the spy fires when the body is allowed


def test_reject_bodies_do_not_echo_payload(calls):
    marker = "ECHO-MARKER-g11"
    big = json.dumps({"m": marker * (MAX_BODY_BYTES // len(marker) + 2)}).encode()
    deep = json.dumps({"m": marker, "d": _nested(MAX_JSON_DEPTH + 2)}).encode()
    for raw in (big, deep):
        r = client.post("/api/v1/signals", content=raw, headers=HEADERS)
        assert r.status_code in (400, 413)
        dumped = json.dumps(r.json())
        assert marker not in dumped
        assert len(dumped) < 200
        assert set(r.json()) <= {"detail", "request_id"}
        assert "X-Request-ID" in r.headers
