"""SPEC-43 Gap 11: per-identity and per-IP request rate in middleware.

Small-cap tests use a private RateLimitMiddleware so the shared app
TestClient is not poisoned.
"""

from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient

from main import app
from monitoring.rate_limit import RATE_LIMITED, RateLimitMiddleware

client = TestClient(app)


def _scope(
    *,
    path: str = "/api/v1/trip/event",
    method: str = "POST",
    ip: str = "1.1.1.1",
    debug_user: str | None = "user-rate",
    authorization: str | None = None,
    request_id: str | None = "rid-g11-rate",
) -> dict:
    headers: list[tuple[bytes, bytes]] = []
    if debug_user is not None:
        headers.append((b"x-debug-user-id", debug_user.encode()))
    if authorization is not None:
        headers.append((b"authorization", authorization.encode()))
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers,
        "client": (ip, 0),
        "state": {"request_id": request_id} if request_id else {},
    }


async def _empty_receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def _drive(mw: RateLimitMiddleware, n: int, **scope_kw) -> tuple[list[bool], list[dict]]:
    called: list[bool] = []

    async def inner(scope, receive, send):
        called.append(True)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    mw.app = inner
    sent_bodies: list[dict] = []

    async def run() -> None:
        for _ in range(n):
            sent: list[dict] = []

            async def send(message):
                sent.append(message)

            await mw(_scope(**scope_kw), _empty_receive, send)
            if sent and sent[0].get("status") == 429:
                body = json.loads(
                    b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
                )
                sent_bodies.append({"status": 429, "body": body, "headers": sent[0].get("headers")})
            else:
                sent_bodies.append({"status": sent[0]["status"] if sent else None, "body": None})

    asyncio.run(run())
    return called, sent_bodies


def test_excess_requests_from_one_identity_are_rate_limited():
    mw = RateLimitMiddleware(lambda s, r, t: None, max_identity=3, max_ip=100, window_s=60)
    called, sent = _drive(mw, 4, ip="1.1.1.1", debug_user="user-rate")
    assert called == [True, True, True]
    assert [s["status"] for s in sent] == [200, 200, 200, 429]
    assert sent[3]["body"]["detail"] == RATE_LIMITED
    assert sent[3]["body"]["request_id"] == "rid-g11-rate"


def test_rate_limit_is_not_bypassed_by_new_debug_identity():
    mw = RateLimitMiddleware(lambda s, r, t: None, max_identity=100, max_ip=3, window_s=60)
    called: list[bool] = []

    async def inner(scope, receive, send):
        called.append(True)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    mw.app = inner
    statuses: list[int] = []

    async def run() -> None:
        for i in range(4):
            sent: list[dict] = []

            async def send(message):
                sent.append(message)

            await mw(
                _scope(ip="2.2.2.2", debug_user=f"rot-{i}"),
                _empty_receive,
                send,
            )
            statuses.append(sent[0]["status"])

    asyncio.run(run())
    assert called == [True, True, True]
    assert statuses == [200, 200, 200, 429]


def test_health_get_still_200_after_several_gets():
    for _ in range(8):
        r = client.get("/api/v1/health")
        assert r.status_code == 200


def test_stripe_webhook_path_is_not_counted():
    mw = RateLimitMiddleware(lambda s, r, t: None, max_identity=1, max_ip=3, window_s=60)
    called, sent = _drive(
        mw,
        5,
        path="/api/v1/payment/webhook/stripe",
        ip="3.3.3.3",
        debug_user=None,
    )
    assert len(called) == 5
    assert all(s["status"] == 200 for s in sent)


def test_429_does_not_echo_secrets_and_includes_request_id():
    mw = RateLimitMiddleware(lambda s, r, t: None, max_identity=1, max_ip=100, window_s=60)
    called, sent = _drive(
        mw,
        2,
        ip="4.4.4.4",
        debug_user="secret-user-xyz",
        authorization="Bearer super-secret-token",
    )
    assert called == [True]
    assert sent[1]["status"] == 429
    dumped = json.dumps(sent[1]["body"])
    assert "secret-user-xyz" not in dumped
    assert "super-secret-token" not in dumped
    assert "Bearer" not in dumped
    assert sent[1]["body"]["detail"] == RATE_LIMITED
    assert sent[1]["body"]["request_id"] == "rid-g11-rate"
    assert set(sent[1]["body"]) <= {"detail", "request_id"}