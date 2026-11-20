"""Shared no-network guard for tests.

Blocks DNS lookups, create_connection and every outbound socket connect to a
non-loopback address. Loopback connects stay allowed on purpose: on Windows,
asyncio's event loop builds its internal wake-up pipe by connecting to
127.0.0.1, so a guard that blocks loopback makes every test that starts an
event loop fail on Windows. Linux and macOS use a real socketpair and never
hit this path, which is why CI does not show it.

ASCII only.
"""

import socket

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_real_connect = socket.socket.connect


def _blocked(*args, **kwargs):
    raise AssertionError("real network access attempted in a test")


def _is_loopback(address) -> bool:
    return isinstance(address, tuple) and len(address) > 0 and address[0] in LOOPBACK_HOSTS


def _guarded_connect(sock, address):
    if _is_loopback(address):
        return _real_connect(sock, address)
    raise AssertionError("real network access attempted in a test")


def block_external_sockets(monkeypatch) -> None:
    """Patch the module-level guards for one test. Use from an autouse fixture."""
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
