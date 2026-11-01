"""SPEC-43 Gap 11: in-process per-identity and per-IP request rate.

Counts POST/PUT/PATCH/DELETE in a sliding window. GETs and payment
webhooks are not counted. Coordinates and tokens are never logged.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Awaitable, Callable, Optional

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

RATE_WINDOW_S = 60
MAX_REQUESTS_PER_IDENTITY = 30
MAX_REQUESTS_PER_IP = 60

RATE_LIMITED = "rate_limited"

_COUNTED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_EXEMPT_PATHS = frozenset(
    {
        "/api/v1/payment/webhook/stripe",
        "/api/v1/payment/webhook/revenuecat",
    }
)


def _header(scope: Scope, name: bytes) -> Optional[bytes]:
    for key, value in scope.get("headers") or []:
        if key.lower() == name:
            return value
    return None


def identity_key(scope: Scope) -> str:
    """Bucket key for the caller. Does not verify JWT. Never logs the header."""
    debug = _header(scope, b"x-debug-user-id")
    if debug:
        return debug.decode("latin-1").strip().lower()
    auth = _header(scope, b"authorization")
    if auth:
        return hashlib.sha256(auth).hexdigest()[:16]
    return "anonymous"


def ip_key(scope: Scope) -> str:
    client = scope.get("client")
    if client and client[0]:
        return str(client[0])
    return "unknown"


class RateLimitMiddleware:
    """Reject when identity or IP exceeds the sliding-window cap (429)."""

    def __init__(
        self,
        app: ASGIApp,
        max_identity: int = MAX_REQUESTS_PER_IDENTITY,
        max_ip: int = MAX_REQUESTS_PER_IP,
        window_s: float = RATE_WINDOW_S,
    ):
        self.app = app
        self.max_identity = max_identity
        self.max_ip = max_ip
        self.window_s = window_s
        self._hits: dict[str, list[float]] = {}

    def _over_cap(self, key: str, max_n: int, now: float) -> bool:
        cutoff = now - self.window_s
        kept = [t for t in self._hits.get(key, []) if t > cutoff]
        if len(kept) >= max_n:
            self._hits[key] = kept
            return True
        kept.append(now)
        self._hits[key] = kept
        return False

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        request_id = (scope.get("state") or {}).get("request_id")
        content = {"detail": RATE_LIMITED}
        if request_id:
            content["request_id"] = request_id
        payload = json.dumps(content).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method") or ""
        if method not in _COUNTED_METHODS:
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        if path.rstrip("/") in {p.rstrip("/") for p in _EXEMPT_PATHS}:
            await self.app(scope, receive, send)
            return

        now = time.monotonic()
        ident = identity_key(scope)
        ip = ip_key(scope)
        identity_over = self._over_cap(f"id:{ident}", self.max_identity, now)
        ip_over = self._over_cap(f"ip:{ip}", self.max_ip, now)
        if identity_over or ip_over:
            await self._reject(scope, receive, send)
            return

        await self.app(scope, receive, send)
