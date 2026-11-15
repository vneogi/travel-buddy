"""What Now walking filter with optional network reachability.

Reuses the SPEC-46 fixtures from tests/test_spec46_what_now.py. The polygon
only removes candidates Haversine keeps; walk minutes, sort, reason codes and
the answer text are unchanged. No test opens a socket: providers are stubs and
an autouse guard fails any connect or DNS lookup.
"""

import asyncio
import importlib
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import services.reachability_provider as rp
from models.schemas import EventType
from services.ask_service import (
    WhatNowRequest,
    fetch_what_now_reachability,
    handle_what_now,
)
from services.reachability_provider import IsochroneResult, ReachabilityError
from tests.test_spec46_what_now import FakeDb, _make_trip, _v

REPO_ROOT = Path(__file__).resolve().parent.parent
REGION = "vientiane_laos"


def _square(w, s, e, n):
    return [[w, s], [e, s], [e, n], [w, n], [w, s]]


# Context node is at (17.96345, 102.61112). The polygon covers the context,
# the near-in venue and the far venue, but not the near-out venue
# (Forodhani-shaped: a few minutes by Haversine, outside the network area).
POLYGONS = (((tuple(map(tuple, _square(102.6105, 17.9630, 102.6500, 17.9950)))),),)


def _rows():
    return [
        _v("v-in", "Inside Temple", lat=17.9640, lng=102.6120),
        _v("v-out", "Across Water Cafe", lat=17.9620, lng=102.6090),
        _v("v-far", "Far Temple", lat=17.9900, lng=102.6400),
    ]


class StubProvider:
    def __init__(self, polygons=POLYGONS, exc=None):
        self.calls = []
        self.polygons, self.exc = polygons, exc

    async def walk_isochrone(self, lat, lng, minutes, identity):
        self.calls.append((lat, lng, minutes, identity))
        if self.exc is not None:
            raise self.exc
        return IsochroneResult(
            polygons=self.polygons,
            minutes=minutes,
            mode="walk",
            source="network_isochrone",
            observed_at=datetime.now(timezone.utc),
        )


@pytest.fixture
def now_utc():
    # Same value as tests/test_spec46_what_now.py: Friday 11:00 ICT (Vientiane).
    return datetime(2026, 10, 2, 4, 0, tzinfo=timezone.utc)


@pytest.fixture
def ctx_node(now_utc):
    # Same context node as tests/test_spec46_what_now.py.
    return {
        "node_id": "n1",
        "venue_name": "Context Temple",
        "venue_id": "ctx-1",
        "scheduled_start": (now_utc - timedelta(minutes=30)).isoformat(),
        "duration_minutes": 60,
        "geo_region": "vientiane_laos",
        "micro_location": "nam_phou_fountain",
        "lat": 17.96345,
        "lng": 102.61112,
        "vibe_tags": ["quiet", "culture"],
        "is_locked": False,
        "node_kind": "activity",
    }


@pytest.fixture(autouse=True)
def _no_sockets(monkeypatch):
    def _blocked(*args, **kwargs):
        raise AssertionError("real network access attempted in a test")

    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)
    monkeypatch.setattr(socket.socket, "connect", _blocked)
    rp._reset_for_tests()
    yield
    rp._reset_for_tests()


def _req(walking="normal"):
    return WhatNowRequest(available_minutes=90, walking=walking)


def _what_now(ctx_node, now_utc, nodes=None, **kwargs):
    nodes = [ctx_node] if nodes is None else nodes
    return handle_what_now(
        _req(), nodes, now_utc, REGION, FakeDb({REGION: _rows()}), **kwargs
    ).what_now


def _names(result):
    return [c["name"] for c in result["candidates"]]


def test_no_polygons_candidates_identical_to_baseline(ctx_node, now_utc):
    baseline = _what_now(ctx_node, now_utc)
    explicit_none = _what_now(ctx_node, now_utc, reach_polygons=None)
    assert explicit_none["candidates"] == baseline["candidates"]
    assert set(_names(baseline)) == {"Inside Temple", "Across Water Cafe"}
    assert baseline["reachability_source"] == "haversine_estimate"
    assert explicit_none["reachability_source"] == "haversine_estimate"
    assert set(baseline) == {
        "location_source",
        "context_label",
        "candidates",
        "reachability_source",
    }


def test_polygon_drops_haversine_near_venue_outside_network(ctx_node, now_utc):
    result = _what_now(ctx_node, now_utc, reach_polygons=POLYGONS)
    assert "Across Water Cafe" not in _names(result)
    assert "Inside Temple" in _names(result)
    assert result["reachability_source"] == "network_isochrone"


def test_polygon_never_adds_venue_beyond_haversine_cap(ctx_node, now_utc):
    baseline = _what_now(ctx_node, now_utc)
    result = _what_now(ctx_node, now_utc, reach_polygons=POLYGONS)
    assert "Far Temple" not in _names(baseline)
    assert "Far Temple" not in _names(result)  # inside the polygon, beyond the cap
    assert set(_names(result)) <= set(_names(baseline))


def test_polygon_does_not_change_walk_minutes_or_sort_keys(ctx_node, now_utc):
    baseline = _what_now(ctx_node, now_utc)["candidates"]
    result = _what_now(ctx_node, now_utc, reach_polygons=POLYGONS)["candidates"]
    kept_ids = {c["venue_id"] for c in result}
    # Same dicts (scheduled_start = now + Haversine walk), same relative order.
    assert result == [c for c in baseline if c["venue_id"] in kept_ids]
    # A polygon that covers everything changes nothing but the source.
    everything = (((tuple(map(tuple, _square(102.0, 17.0, 103.0, 18.5)))),),)
    covered = _what_now(ctx_node, now_utc, reach_polygons=everything)
    assert covered["candidates"] == baseline
    assert covered["reachability_source"] == "network_isochrone"


def test_provider_error_falls_back_to_haversine(ctx_node, now_utc):
    baseline = _what_now(ctx_node, now_utc)
    errors = [ReachabilityError(code) for code in sorted(rp.ERROR_CODES)] + [RuntimeError("x")]
    for exc in errors:
        stub = StubProvider(exc=exc)
        reach = asyncio.run(
            fetch_what_now_reachability(_req(), [ctx_node], now_utc, REGION, stub, "u-wn")
        )
        assert reach is None, exc
        assert len(stub.calls) == 1
        result = _what_now(ctx_node, now_utc, reach_polygons=reach)
        assert result["candidates"] == baseline["candidates"]
        assert result["reachability_source"] == "haversine_estimate"


def test_region_anchor_never_calls_provider_and_is_not_applicable(ctx_node, now_utc):
    stub = StubProvider()
    reach = asyncio.run(fetch_what_now_reachability(_req(), [], now_utc, REGION, stub, "u-wn"))
    assert reach is None
    assert stub.calls == []
    plain = _what_now(ctx_node, now_utc, nodes=[])
    with_polys = _what_now(ctx_node, now_utc, nodes=[], reach_polygons=POLYGONS)
    assert plain["location_source"] == "region_anchor"
    assert plain["reachability_source"] == "not_applicable"
    assert with_polys["reachability_source"] == "not_applicable"
    assert with_polys["candidates"] == plain["candidates"]
    # A trip node without coordinates also makes no provider call.
    no_coords = dict(ctx_node, lat=None, lng=None)
    assert (
        asyncio.run(fetch_what_now_reachability(_req(), [no_coords], now_utc, REGION, stub, "u-wn"))
        is None
    )
    assert stub.calls == []


def _process(trip, now_utc, monkeypatch, preferences, user_id="u-wn-net"):
    sm = importlib.import_module("agents.state_machine")
    monkeypatch.setattr(sm.db_service, "list_venues_for_region", lambda region: _rows())
    return asyncio.run(
        sm.state_machine.process_event(
            trip_state=trip,
            event_type=EventType.ASK_INFO.value,
            message="What now?",
            preferences=preferences,
            now_utc=now_utc,
            user_id=user_id,
        )
    )


def test_origin_is_context_node_coords_not_preferences(ctx_node, now_utc, monkeypatch):
    stub = StubProvider()
    monkeypatch.setattr(rp, "get_reachability_provider", lambda: stub)
    prefs = {
        "mode": "what_now",
        "available_minutes": 90,
        "lat": 1.2345,
        "lng": 6.789,
        "gps": {"lat": 1.2345, "lng": 6.789},
        "latitude": 1.2345,
        "longitude": 6.789,
    }
    result = _process(_make_trip(ctx_node, now_utc), now_utc, monkeypatch, prefs)
    assert len(stub.calls) == 1
    lat, lng, minutes, identity = stub.calls[0]
    assert (lat, lng) == (ctx_node["lat"], ctx_node["lng"])
    assert minutes == 25
    assert identity == "u-wn-net"
    assert result["ask_response"]["what_now"]["reachability_source"] == "network_isochrone"


def test_minutes_follow_walking_cap(ctx_node, now_utc):
    for walking, minutes in (("short", 15), ("normal", 25), ("longer", 45)):
        stub = StubProvider()
        reach = asyncio.run(
            fetch_what_now_reachability(_req(walking), [ctx_node], now_utc, REGION, stub, "u")
        )
        assert reach == POLYGONS
        assert [c[2] for c in stub.calls] == [minutes]


def test_state_machine_what_now_passes_polygons_when_enabled(ctx_node, now_utc, monkeypatch):
    stub = StubProvider()
    monkeypatch.setattr(rp, "get_reachability_provider", lambda: stub)
    result = _process(
        _make_trip(ctx_node, now_utc),
        now_utc,
        monkeypatch,
        {"mode": "what_now", "available_minutes": 90},
    )
    what_now = result["ask_response"]["what_now"]
    names = [c["name"] for c in what_now["candidates"]]
    assert what_now["reachability_source"] == "network_isochrone"
    assert "Inside Temple" in names
    assert "Across Water Cafe" not in names
    assert len(stub.calls) == 1


def test_state_machine_what_now_flag_off_makes_no_provider_call(ctx_node, now_utc, monkeypatch):
    from config.settings import settings

    assert settings.reachability_provider == "off"
    calls = []

    async def _spy(self, *args, **kwargs):
        calls.append(args)
        raise AssertionError("provider called with the flag off")

    monkeypatch.setattr(rp.GoogleIsochronesProvider, "walk_isochrone", _spy)
    monkeypatch.setattr(settings, "google_maps_api_key", "test-key-present")
    assert rp.get_reachability_provider() is None
    result = _process(
        _make_trip(ctx_node, now_utc),
        now_utc,
        monkeypatch,
        {"mode": "what_now", "available_minutes": 90},
    )
    what_now = result["ask_response"]["what_now"]
    assert calls == []
    assert what_now["reachability_source"] == "haversine_estimate"
    assert {"Inside Temple", "Across Water Cafe"} <= {c["name"] for c in what_now["candidates"]}


def test_touched_files_are_ascii():
    for rel in (
        "services/geo_polygon.py",
        "services/reachability_provider.py",
        "services/ask_service.py",
        "agents/state_machine.py",
        "config/settings.py",
        "tests/test_reachability_provider.py",
        "tests/test_what_now_network_reachability.py",
    ):
        assert (REPO_ROOT / rel).read_text(encoding="utf-8").isascii(), rel
    # .env.example has a pre-existing non-ASCII comment on main; check the
    # one line this slice adds.
    env_lines = (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    added = [line for line in env_lines if line.startswith("TB_REACHABILITY_PROVIDER")]
    assert added == ["TB_REACHABILITY_PROVIDER=off"]
    assert all(line.isascii() for line in added)
