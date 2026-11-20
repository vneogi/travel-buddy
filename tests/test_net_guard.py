"""The shared network guard: loopback connects work, external ones fail.

The loopback test is the regression for the Windows failure: the old guard
blocked every connect, which broke asyncio's internal wake-up pipe.
"""

import asyncio
import socket

import pytest

from tests.net_guard import block_external_sockets


@pytest.fixture
def guarded(monkeypatch):
    block_external_sockets(monkeypatch)


def test_loopback_connect_is_allowed(guarded):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            client.connect(listener.getsockname())
        finally:
            client.close()
    finally:
        listener.close()


def test_external_connect_is_blocked(guarded):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # TEST-NET-3 address; the guard raises before any packet is sent.
        with pytest.raises(AssertionError, match="real network access"):
            sock.connect(("203.0.113.10", 443))
    finally:
        sock.close()


def test_dns_and_create_connection_stay_blocked(guarded):
    with pytest.raises(AssertionError, match="real network access"):
        socket.getaddrinfo("example.com", 443)
    with pytest.raises(AssertionError, match="real network access"):
        socket.create_connection(("example.com", 443))


def test_asyncio_loop_starts_under_guard(guarded):
    async def _ping():
        return "ok"

    assert asyncio.run(_ping()) == "ok"
