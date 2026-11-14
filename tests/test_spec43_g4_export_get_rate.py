"""SPEC-43 Gap 4 slice 16: the limiter counts GET /api/v1/me/export.

Every other GET stays uncounted (Gap 11 design). Limiter tests use a private
RateLimitMiddleware with a stub inner app so the shared app TestClient is not
poisoned. _scope and _drive are copied from tests/test_spec43_g11_rate.py (not
imported across test files).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import monitoring.rate_limit as rate_limit
from monitoring.rate_limit import RATE_LIMITED, RateLimitMiddleware, _is_counted

EXPORT_PATH = "/api/v1/me/export"


def _scope(
    *,
    path: str = EXPORT_PATH,
    method: str = "GET",
    ip: str = "1.1.1.1",
    debug_user: str | None = "user-export-rate",
    authorization: str | None = None,
    request_id: str | None = "rid-g4-export-rate",
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


def _mw(max_identity=3, max_ip=100):
    return RateLimitMiddleware(
        lambda s, r, t: None, max_identity=max_identity, max_ip=max_ip, window_s=60
    )


def test_export_get_is_counted_per_identity():
    called, sent = _drive(_mw(max_identity=3, max_ip=100), 4, ip="5.5.5.1", debug_user="exp-a")
    assert called == [True, True, True]
    assert [s["status"] for s in sent] == [200, 200, 200, 429]
    assert sent[3]["body"]["detail"] == RATE_LIMITED


def test_export_get_is_counted_per_ip():
    mw = _mw(max_identity=100, max_ip=3)
    called: list[bool] = []

    async def inner(scope, receive, send):
        called.append(True)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    mw.app = inner
    statuses: list[int] = []
    bodies: list[bytes] = []

    async def run() -> None:
        for i in range(4):
            sent: list[dict] = []

            async def send(message):
                sent.append(message)

            await mw(_scope(ip="5.5.5.2", debug_user=f"exp-rot-{i}"), _empty_receive, send)
            statuses.append(sent[0]["status"])
            bodies.append(
                b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
            )

    asyncio.run(run())
    assert called == [True, True, True]
    assert statuses == [200, 200, 200, 429]
    assert json.loads(bodies[3])["detail"] == RATE_LIMITED


def test_export_get_429_includes_request_id():
    called, sent = _drive(
        _mw(max_identity=1, max_ip=100),
        2,
        ip="5.5.5.3",
        debug_user="exp-rid",
        authorization="Bearer export-secret-token",
    )
    assert called == [True]
    assert sent[1]["status"] == 429
    body = sent[1]["body"]
    assert body == {"detail": RATE_LIMITED, "request_id": "rid-g4-export-rate"}
    dumped = json.dumps(body)
    assert "export-secret-token" not in dumped and "exp-rid" not in dumped


def test_other_gets_are_still_not_counted():
    # /api/v1/me/status does not exist on main; /api/v1/trips is an existing
    # trip read. /api/v1/me/exportx proves the export match is not a prefix.
    for i, path in enumerate(("/api/v1/health", "/api/v1/trips", "/api/v1/me/exportx")):
        called, sent = _drive(
            _mw(max_identity=3, max_ip=3), 6, path=path, ip=f"5.5.6.{i}", debug_user="exp-other"
        )
        assert len(called) == 6, path
        assert [s["status"] for s in sent] == [200] * 6, path


def test_export_path_with_trailing_slash_is_counted():
    called, sent = _drive(
        _mw(max_identity=3, max_ip=100), 4, path=EXPORT_PATH + "/", ip="5.5.5.4", debug_user="exp-s"
    )
    assert called == [True, True, True]
    assert [s["status"] for s in sent] == [200, 200, 200, 429]


def test_export_get_is_not_exempt():
    exempt = {p.rstrip("/") for p in rate_limit._EXEMPT_PATHS}
    assert EXPORT_PATH.rstrip("/") not in exempt


def test_stripe_webhook_still_not_counted():
    called, sent = _drive(
        RateLimitMiddleware(lambda s, r, t: None, max_identity=1, max_ip=3, window_s=60),
        5,
        path="/api/v1/payment/webhook/stripe",
        method="POST",
        ip="5.5.5.5",
        debug_user=None,
    )
    assert len(called) == 5
    assert all(s["status"] == 200 for s in sent)


def test_is_counted_rule_table():
    assert _is_counted("POST", "/api/v1/x") is True
    assert _is_counted("PUT", "/api/v1/x") is True
    assert _is_counted("PATCH", "/api/v1/x") is True
    assert _is_counted("DELETE", "/api/v1/x") is True
    assert _is_counted("GET", "/api/v1/me/export") is True
    assert _is_counted("GET", "/api/v1/me/export/") is True
    assert _is_counted("GET", "/api/v1/health") is False
    assert _is_counted("GET", "/api/v1/me/exportx") is False
    # HEAD is not counted by design: only GET on the export path is added.
    assert _is_counted("HEAD", "/api/v1/me/export") is False


def test_rate_limit_module_changes_are_ascii():
    source = Path(rate_limit.__file__).read_text(encoding="utf-8")
    assert source.isascii()
