"""SPEC-43 Gap 11: bound request body size and JSON depth.

Pure ASGI middleware. Oversized or deeply nested bodies are rejected before
route handlers, auth dependencies, Pydantic, venue search, or the
orchestrator run. The payload is never logged or echoed.
"""

from __future__ import annotations

from typing import Optional

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BODY_BYTES = 262144  # 256 KiB
MAX_JSON_DEPTH = 8

PAYLOAD_TOO_LARGE = "payload_too_large"
PAYLOAD_TOO_DEEP = "payload_too_deep"

_OPEN = frozenset(b"{[")
_CLOSE = frozenset(b"}]")
_QUOTE = ord('"')
_BACKSLASH = ord("\\")


def json_depth(value: object) -> int:
    """Depth of a decoded JSON value: dict/list nest one level; scalars are 0."""
    depth = 0
    frontier = [(value, 0)]
    while frontier:
        node, level = frontier.pop()
        if isinstance(node, dict):
            children = node.values()
        elif isinstance(node, list):
            children = node
        else:
            depth = max(depth, level)
            continue
        level += 1
        depth = max(depth, level)
        frontier.extend((child, level) for child in children)
    return depth


def raw_json_depth_exceeds(body: bytes, limit: int = MAX_JSON_DEPTH) -> bool:
    """True if the bracket nesting of *body* goes beyond *limit*.

    Scans bytes (ignoring string contents) instead of decoding, so a
    thousand-deep blob is refused without recursion or a full parse. For
    valid JSON this equals json_depth(json.loads(body)) > limit.
    """
    depth = 0
    in_string = False
    escaped = False
    for byte in body:
        if in_string:
            if escaped:
                escaped = False
            elif byte == _BACKSLASH:
                escaped = True
            elif byte == _QUOTE:
                in_string = False
            continue
        if byte == _QUOTE:
            in_string = True
        elif byte in _OPEN:
            depth += 1
            if depth > limit:
                return True
        elif byte in _CLOSE:
            depth -= 1
    return False


def _header(scope: Scope, name: bytes) -> Optional[bytes]:
    for key, value in scope.get("headers") or []:
        if key.lower() == name:
            return value
    return None


class PayloadLimitMiddleware:
    """Reject bodies over MAX_BODY_BYTES (413) or JSON deeper than MAX_JSON_DEPTH (400)."""

    def __init__(
        self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES, max_depth: int = MAX_JSON_DEPTH
    ):
        self.app = app
        self.max_bytes = max_bytes
        self.max_depth = max_depth

    async def _reject(
        self, scope: Scope, receive: Receive, send: Send, status: int, code: str
    ) -> None:
        request_id = (scope.get("state") or {}).get("request_id")
        content = {"detail": code}
        if request_id:
            content["request_id"] = request_id
        await JSONResponse(status_code=status, content=content)(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = _header(scope, b"content-length")
        if declared is not None:
            try:
                declared_len = int(declared)
            except ValueError:
                declared_len = None
            if declared_len is not None and declared_len > self.max_bytes:
                await self._reject(scope, receive, send, 413, PAYLOAD_TOO_LARGE)
                return

        body = bytearray()
        pending: list[Message] = []
        while True:
            message = await receive()
            if message["type"] != "http.request":
                pending.append(message)  # e.g. http.disconnect: replay as-is
                break
            body.extend(message.get("body", b""))
            if len(body) > self.max_bytes:
                await self._reject(scope, receive, send, 413, PAYLOAD_TOO_LARGE)
                return
            if not message.get("more_body", False):
                break

        content_type = (_header(scope, b"content-type") or b"").decode("latin-1").lower()
        if body and content_type.startswith("application/json"):
            if raw_json_depth_exceeds(bytes(body), self.max_depth):
                await self._reject(scope, receive, send, 400, PAYLOAD_TOO_DEEP)
                return

        replay: list[Message] = [{"type": "http.request", "body": bytes(body), "more_body": False}]
        replay.extend(pending)

        async def replay_receive() -> Message:
            if replay:
                return replay.pop(0)
            return await receive()

        await self.app(scope, replay_receive, send)
