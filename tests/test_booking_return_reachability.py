"""Network reachability slice 2: booking-return check for What Now.

No test opens a real socket: provider HTTP goes through httpx.MockTransport,
What Now tests use stub providers, and an autouse guard fails any socket
connect or DNS lookup.
"""

import asyncio
import importlib
import json
import logging
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

import services.reachability_provider as rp
from models.schemas import EventType, NodeStatus, TripNode, TripState
from monitoring.spend_circuit import SpendCircuit
from services.ask_service import (
    WhatNowRequest,
    _booking_return_band,
    fetch_booking_return_reachability,
    handle_what_now,
)
from services.reachability_provider import IsochroneResult, ReachabilityError
from tests.test_spec46_what_now import FakeDb, _v

REPO_ROOT = Path(__file__).resolve().parent.parent
REGION = "vientiane_laos"
KEY = "test-maps-key-0123456789abcdef"
LAT, LNG = 17.96345, 102.61112
NOW = datetime(2026, 10, 2, 4, 0, tzinfo=timezone.utc)  # 11:00 ICT


def _square(w, s, e, n):
    return [[w, s], [e, s], [e, n], [w, n], [w, s]]


def _poly(w, s, e, n):
    return ((tuple(tuple(p) for p in _square(w, s, e, n)),),)


# Covers the context, Inside Temple and Far Temple, not Across Water Cafe.
POLYGONS = _poly(102.6105, 17.9630, 102.6500, 17.9950)
BIG = _poly(102.5, 17.9, 102.7, 18.1)
TINY = _poly(100.0, 10.0, 100.01, 10.01)


def _rows():
    return [
        _v("v-in", "Inside Temple", lat=17.9640, lng=102.6120),
        _v("v-out", "Across Water Cafe", lat=17.9620, lng=102.6090),
        _v("v-far", "Far Temple", lat=17.9900, lng=102.6400),
    ]


def _ctx():
    return {
        "node_id": "n1",
        "venue_name": "Context Temple",
        "venue_id": "ctx-1",
        "scheduled_start": (NOW - timedelta(minutes=30)).isoformat(),
        "duration_minutes": 60,
        "geo_region": REGION,
        "micro_location": "nam_phou_fountain",
        "lat": LAT,
        "lng": LNG,
        "vibe_tags": ["quiet", "culture"],
        "is_locked": False,
        "node_kind": "activity",
    }


def _booking(gap_min=100, *, now=NOW, booking_type="tour", region=REGION, lat=LAT, lng=LNG):
    start = now + timedelta(minutes=gap_min)
    return {
        "node_id": "bk1",
        "venue_name": "Tour Pickup",
        "scheduled_start": start.isoformat(),
        "duration_minutes": 60,
        "geo_region": region,
        "lat": lat,
        "lng": lng,
        "is_locked": True,
        "node_kind": "booking",
        "booking_type": booking_type,
    }


class _Stub:
    """Records FROM and TO calls; each direction returns its own polygons."""

    def __init__(self, from_polygons=BIG, to_polygons=POLYGONS, to_exc=None):
        self.from_calls, self.to_calls = [], []
        self.from_polygons, self.to_polygons, self.to_exc = from_polygons, to_polygons, to_exc

    @staticmethod
    def _result(polygons, minutes):
        return IsochroneResult(
            polygons=polygons,
            minutes=minutes,
            mode="walk",
            source="network_isochrone",
            observed_at=datetime.now(timezone.utc),
        )

    async def walk_isochrone(self, lat, lng, minutes, identity):
        self.from_calls.append((lat, lng, minutes, identity))
        return self._result(self.from_polygons, minutes)

    async def walk_isochrone_to(self, lat, lng, minutes, identity):
        self.to_calls.append((lat, lng, minutes, identity))
        if self.to_exc is not None:
            raise self.to_exc
        return self._result(self.to_polygons, minutes)


class _Handler:
    """MockTransport handler: records requests, answers around the origin."""

    def __init__(self, status=200):
        self.calls, self.status = [], status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        body = json.loads(request.content)
        lat, lng = body["location"]["latitude"], body["location"]["longitude"]
        d = 0.01
        payload = {
            "isochrone": {
                "geoJson": {
                    "type": "MultiPolygon",
                    "coordinates": [[_square(lng - d, lat - d, lng + d, lat + d)]],
                }
            }
        }
        return httpx.Response(self.status, json=payload)


def _google(handler, circuit=None):
    return rp.GoogleIsochronesProvider(
        KEY,
        transport=httpx.MockTransport(handler),
        spend_circuit=circuit or SpendCircuit(max_process_usd=100.0, max_identity_usd=100.0),
        clock=lambda: 1000.0,
    )


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__(logging.INFO)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


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


def _run(coro):
    return asyncio.run(coro)


def _fetch(nodes, stub, now=NOW, region=REGION):
    return _run(fetch_booking_return_reachability(nodes, now, region, stub, "u"))


def _what_now(nodes, rows=None, **kwargs):
    rows = _rows() if rows is None else rows
    return handle_what_now(
        WhatNowRequest(available_minutes=90), nodes, NOW, REGION, FakeDb({REGION: rows}), **kwargs
    ).what_now


def _names(result):
    return [c["name"] for c in result["candidates"]]


# ---------------------------------------------------------------- provider


def test_to_request_body_differs_from_from_only_in_direction():
    from_handler, to_handler = _Handler(), _Handler()
    _run(_google(from_handler).walk_isochrone(LAT, LNG, 30, "u1"))
    _run(_google(to_handler).walk_isochrone_to(LAT, LNG, 30, "u1"))
    from_body = json.loads(from_handler.calls[0].content)
    to_body = json.loads(to_handler.calls[0].content)
    assert from_body["travelDirection"] == "FROM"
    assert to_body["travelDirection"] == "TO"
    assert {k: v for k, v in to_body.items() if k != "travelDirection"} == {
        k: v for k, v in from_body.items() if k != "travelDirection"
    }
    to_req, from_req = to_handler.calls[0], from_handler.calls[0]
    assert str(to_req.url) == str(from_req.url)
    for header in ("X-Goog-Api-Key", "X-Goog-FieldMask", "Content-Type"):
        assert to_req.headers[header] == from_req.headers[header]


def test_from_request_and_cache_key_unchanged():
    handler = _Handler()
    provider = _google(handler)
    sink = _ListHandler()
    log = logging.getLogger("travelbuddy")
    log.addHandler(sink)
    old_level = log.level
    log.setLevel(logging.INFO)
    try:
        _run(provider.walk_isochrone(LAT, LNG, 25, "u1"))
    finally:
        log.removeHandler(sink)
        log.setLevel(old_level)
    assert json.loads(handler.calls[0].content) == {
        "location": {"latitude": LAT, "longitude": LNG},
        "travelDuration": "1500s",
        "travelMode": "WALK",
        "travelDirection": "FROM",
        "routingPreference": "TRAFFIC_UNAWARE",
        "enableSmoothing": False,
    }
    assert list(provider._cache) == [f"{round(LAT, 3)},{round(LNG, 3)}:25"]
    assert provider._cache_key(LAT, LNG, 25) == f"{round(LAT, 3)},{round(LNG, 3)}:25"
    assert sink.messages == ["reachability provider=google_isochrones outcome=ok"]


def test_to_and_from_cache_entries_are_separate():
    handler = _Handler()
    provider = _google(handler)
    from_result = _run(provider.walk_isochrone(LAT, LNG, 30, "u1"))
    to_result = _run(provider.walk_isochrone_to(LAT, LNG, 30, "u1"))
    assert len(handler.calls) == 2
    base = f"{round(LAT, 3)},{round(LNG, 3)}:30"
    assert set(provider._cache) == {base, f"{base}:to"}
    assert _run(provider.walk_isochrone_to(LAT, LNG, 30, "u2")) is to_result
    assert _run(provider.walk_isochrone(LAT, LNG, 30, "u2")) is from_result
    assert len(handler.calls) == 2


def test_to_respects_spend_cap_before_http():
    handler = _Handler()
    capped = SpendCircuit(max_process_usd=0.001, max_identity_usd=0.001)
    with pytest.raises(ReachabilityError) as err:
        _run(_google(handler, circuit=capped).walk_isochrone_to(LAT, LNG, 30, "u1"))
    assert err.value.code == "spend_capped"
    assert handler.calls == []


def test_to_logs_direction_and_never_key_or_coordinates():
    sink = _ListHandler()
    log = logging.getLogger("travelbuddy")
    log.addHandler(sink)
    old_level = log.level
    log.setLevel(logging.INFO)
    try:
        _run(_google(_Handler()).walk_isochrone_to(LAT, LNG, 30, "u1"))
        with pytest.raises(ReachabilityError):
            _run(_google(_Handler(status=500)).walk_isochrone_to(LAT, LNG, 30, "u1"))
    finally:
        log.removeHandler(sink)
        log.setLevel(old_level)
    assert sink.messages == [
        "reachability provider=google_isochrones direction=to outcome=ok",
        "reachability provider=google_isochrones direction=to outcome=http_error",
    ]
    text = "\n".join(sink.messages)
    for secret in (KEY, str(LAT), str(LNG), "isochrones.googleapis.com", "location"):
        assert secret not in text


def test_abc_default_walk_isochrone_to_raises_not_configured():
    class FromOnly(rp.ReachabilityProvider):
        async def walk_isochrone(self, lat, lng, minutes, identity):
            raise AssertionError("not used")

    with pytest.raises(ReachabilityError) as err:
        _run(FromOnly().walk_isochrone_to(LAT, LNG, 30, "u1"))
    assert err.value.code == "not_configured"


# -------------------------------------------------------- gate and helper


def test_booking_return_off_by_default():
    from config.settings import Settings, settings

    assert Settings.model_fields["reachability_booking_return"].default == "off"
    assert settings.reachability_booking_return == "off"
    assert rp.booking_return_enabled() is False


def test_booking_return_needs_exact_on_value(monkeypatch):
    from config.settings import settings

    for value in ("ON", "On", " on", "on ", "true", "1", "yes", "off", ""):
        monkeypatch.setattr(settings, "reachability_booking_return", value)
        assert rp.booking_return_enabled() is False, value
    monkeypatch.setattr(settings, "reachability_booking_return", "on")
    assert rp.booking_return_enabled() is True


def test_band_rounds_up_to_next_band():
    cases = ((1, 15), (15, 15), (16, 30), (44, 45), (46, 60), (61, 90), (91, 120), (120, 120))
    for gap, band in cases:
        stub = _Stub()
        reach = _fetch([_ctx(), _booking(gap)], stub)
        assert reach is not None, gap
        assert reach[0] == "bk1" and reach[1] == band, gap
        assert [c[2] for c in stub.to_calls] == [band], gap
    # A part minute rounds up too: 15 min 1 s is a 16 minute gap.
    start = NOW + timedelta(minutes=15, seconds=1)
    bk = dict(_booking(15), scheduled_start=start.isoformat())
    assert _fetch([_ctx(), bk], _Stub())[1] == 30


def test_no_call_when_gap_over_120_or_under_1():
    for nodes in (
        [_ctx(), _booking(121)],
        [_ctx(), _booking(0)],
        [_ctx(), _booking(-5)],
    ):
        stub = _Stub()
        assert _fetch(nodes, stub) is None
        assert stub.to_calls == []
    assert _booking_return_band(_booking(0), NOW, REGION) is None


def test_no_call_for_flight_hotel_other_region_or_other_day():
    late = datetime(2026, 10, 2, 16, 30, tzinfo=timezone.utc)  # 23:30 ICT
    for nodes, now in (
        ([_ctx(), _booking(60, booking_type="flight")], NOW),
        ([_ctx(), _booking(60, booking_type="hotel")], NOW),
        ([_ctx(), _booking(60, region="luang_prabang_laos")], NOW),
        ([_ctx(), _booking(60, now=late)], late),  # 00:30 ICT the next day
    ):
        stub = _Stub()
        assert _fetch(nodes, stub, now=now) is None
        assert stub.to_calls == []


def test_no_call_when_booking_has_no_finite_coords():
    for lat, lng in (
        (None, LNG),
        (LAT, None),
        ("abc", LNG),
        (float("nan"), LNG),
        (LAT, float("inf")),
    ):
        stub = _Stub()
        assert _fetch([_ctx(), _booking(60, lat=lat, lng=lng)], stub) is None
        assert stub.to_calls == []


def _trip_with_booking(bk_lat=17.9650, bk_lng=102.6125, gap=100):
    ctx = _ctx()
    return TripState(
        trip_id="trip-br",
        user_id="u-br",
        geo_region=REGION,
        nodes=[
            TripNode(
                node_id=ctx["node_id"],
                venue_name=ctx["venue_name"],
                venue_id=ctx["venue_id"],
                scheduled_start=datetime.fromisoformat(ctx["scheduled_start"]),
                duration_minutes=ctx["duration_minutes"],
                geo_region=REGION,
                micro_location=ctx["micro_location"],
                lat=LAT,
                lng=LNG,
                is_locked=False,
                status=NodeStatus.PENDING,
            ),
            TripNode(
                node_id="bk1",
                venue_name="Tour Pickup",
                scheduled_start=NOW + timedelta(minutes=gap),
                duration_minutes=60,
                geo_region=REGION,
                lat=bk_lat,
                lng=bk_lng,
                is_locked=True,
                node_kind="booking",
                booking_type="tour",
                status=NodeStatus.PENDING,
            ),
        ],
    )


def _process(trip, monkeypatch, preferences, user_id="u-br-net"):
    sm = importlib.import_module("agents.state_machine")
    monkeypatch.setattr(sm.db_service, "list_venues_for_region", lambda region: _rows())
    return asyncio.run(
        sm.state_machine.process_event(
            trip_state=trip,
            event_type=EventType.ASK_INFO.value,
            message="What now?",
            preferences=preferences,
            now_utc=NOW,
            user_id=user_id,
        )
    )


def test_origin_is_booking_coords_not_preferences(monkeypatch):
    from config.settings import settings

    stub = _Stub()
    monkeypatch.setattr(rp, "get_reachability_provider", lambda: stub)
    monkeypatch.setattr(settings, "reachability_booking_return", "on")
    prefs = {
        "mode": "what_now",
        "available_minutes": 90,
        "lat": 1.2345,
        "lng": 6.789,
        "gps": {"lat": 1.2345, "lng": 6.789},
        "latitude": 1.2345,
        "longitude": 6.789,
    }
    result = _process(_trip_with_booking(), monkeypatch, prefs)
    assert len(stub.to_calls) == 1
    lat, lng, minutes, identity = stub.to_calls[0]
    assert (lat, lng) == (17.9650, 102.6125)
    assert minutes == 120
    assert identity == "u-br-net"
    assert result["ask_response"]["what_now"]["booking_reachability_source"] == "network_isochrone"


def test_provider_error_returns_none():
    for exc in [ReachabilityError(code) for code in sorted(rp.ERROR_CODES)] + [RuntimeError("x")]:
        stub = _Stub(to_exc=exc)
        assert _fetch([_ctx(), _booking(60)], stub) is None
        assert len(stub.to_calls) == 1


# -------------------------------------------------------------- What Now


def test_no_booking_reach_candidates_identical_to_baseline():
    nodes = [_ctx(), _booking(100)]
    baseline = _what_now(nodes)
    explicit_none = _what_now(nodes, booking_reach=None)
    assert explicit_none == baseline
    assert set(_names(baseline)) == {"Inside Temple", "Across Water Cafe"}


def test_outside_to_area_drops_candidate_haversine_kept():
    nodes = [_ctx(), _booking(100)]
    assert "Across Water Cafe" in _names(_what_now(nodes))
    result = _what_now(nodes, booking_reach=("bk1", 120, POLYGONS))
    assert "Across Water Cafe" not in _names(result)


def test_inside_to_area_keeps_candidate():
    nodes = [_ctx(), _booking(100)]
    result = _what_now(nodes, booking_reach=("bk1", 120, POLYGONS))
    assert "Inside Temple" in _names(result)
    baseline = {c["name"]: c for c in _what_now(nodes)["candidates"]}
    kept = {c["name"]: c for c in result["candidates"]}
    assert kept["Inside Temple"] == baseline["Inside Temple"]


def test_booking_reach_never_adds_candidate():
    nodes = [_ctx(), _booking(100)]
    baseline = _what_now(nodes)
    result = _what_now(nodes, booking_reach=("bk1", 120, BIG))
    assert result["candidates"] == baseline["candidates"]
    assert "Far Temple" not in _names(result)


def test_booking_reach_for_other_node_id_is_ignored():
    nodes = [_ctx(), _booking(100)]
    baseline = _what_now(nodes)
    result = _what_now(nodes, booking_reach=("other-node", 120, TINY))
    assert result["candidates"] == baseline["candidates"]


def test_candidate_without_coords_not_dropped():
    # A lock in another region is ignored by the Haversine check, so a
    # candidate without coordinates survives it. The reverse-area check must
    # not drop it either; candidates with coordinates outside the area go.
    nodes = [_ctx(), _booking(60, region="luang_prabang_laos")]
    rows = _rows() + [_v("v-nc", "No Coords Cafe", lat=None, lng=None)]
    baseline = _what_now(nodes, rows=rows)
    assert "No Coords Cafe" in _names(baseline)
    result = _what_now(nodes, rows=rows, booking_reach=("bk1", 120, TINY))
    assert "No Coords Cafe" in _names(result)
    assert "Inside Temple" not in _names(result)
    nc_base = next(c for c in baseline["candidates"] if c["name"] == "No Coords Cafe")
    nc_new = next(c for c in result["candidates"] if c["name"] == "No Coords Cafe")
    assert nc_new == nc_base


def test_envelope_values_network_haversine_not_applicable():
    applicable = [_ctx(), _booking(100)]
    assert (
        _what_now(applicable, booking_reach=("bk1", 120, BIG))["booking_reachability_source"]
        == "network_isochrone"
    )
    assert _what_now(applicable)["booking_reachability_source"] == "haversine_estimate"
    assert _what_now([_ctx()])["booking_reachability_source"] == "not_applicable"
    assert _what_now([_ctx(), _booking(200)])["booking_reachability_source"] == "not_applicable"
    other_region = [_ctx(), _booking(60, region="luang_prabang_laos")]
    assert _what_now(other_region)["booking_reachability_source"] == "not_applicable"
    assert _booking_return_band(_booking(100, booking_type="flight"), NOW, REGION) is None


def test_slice1_reachability_source_unchanged():
    nodes = [_ctx(), _booking(100)]
    assert _what_now(nodes)["reachability_source"] == "haversine_estimate"
    reach = ("bk1", 120, BIG)
    assert _what_now(nodes, booking_reach=reach)["reachability_source"] == "haversine_estimate"
    with_both = _what_now(nodes, reach_polygons=BIG, booking_reach=reach)
    assert with_both["reachability_source"] == "network_isochrone"


def test_trip_event_response_keeps_booking_reachability_source():
    """FastAPI response_model=TripEventResponse must not drop the field."""
    from models.schemas import TripEventResponse

    what_now = {
        "location_source": "trip_position",
        "context_label": "Using your trip position",
        "candidates": [{"candidate_id": "what_now:in", "venue_id": "in", "name": "Inside Temple"}],
        "reachability_source": "network_isochrone",
        "booking_reachability_source": "network_isochrone",
    }
    resp = TripEventResponse(
        trip_id="t1",
        status="ok",
        message="ok",
        ask_response={
            "answer": "Found 1 option within reach: Inside Temple.",
            "tier": "hedge",
            "path": "grounded_deterministic",
            "intent": "what_now",
            "source_ids": ["in"],
            "source_class": "curated_catalog",
            "what_now": what_now,
        },
    )
    assert resp.ask_response.what_now.booking_reachability_source == "network_isochrone"
    dumped = resp.model_dump()
    assert dumped["ask_response"]["what_now"]["booking_reachability_source"] == "network_isochrone"
    # Absent in the payload -> the schema default, never dropped.
    what_now.pop("booking_reachability_source")
    resp2 = TripEventResponse(
        trip_id="t1",
        status="ok",
        message="ok",
        ask_response=dict(resp.model_dump()["ask_response"], what_now=what_now),
    )
    assert resp2.model_dump()["ask_response"]["what_now"]["booking_reachability_source"] == (
        "not_applicable"
    )


# ---------------------------------------------------------- state machine


def test_state_machine_booking_return_off_makes_no_to_call(monkeypatch):
    from config.settings import settings

    assert settings.reachability_booking_return == "off"
    stub = _Stub()
    monkeypatch.setattr(rp, "get_reachability_provider", lambda: stub)
    result = _process(
        _trip_with_booking(), monkeypatch, {"mode": "what_now", "available_minutes": 90}
    )
    what_now = result["ask_response"]["what_now"]
    assert stub.to_calls == []
    assert len(stub.from_calls) == 1
    assert what_now["booking_reachability_source"] == "haversine_estimate"
    assert "Across Water Cafe" in {c["name"] for c in what_now["candidates"]}


def test_state_machine_booking_return_on_passes_reach(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "reachability_booking_return", "on")
    stub = _Stub()
    monkeypatch.setattr(rp, "get_reachability_provider", lambda: stub)
    result = _process(
        _trip_with_booking(), monkeypatch, {"mode": "what_now", "available_minutes": 90}
    )
    what_now = result["ask_response"]["what_now"]
    names = {c["name"] for c in what_now["candidates"]}
    assert len(stub.to_calls) == 1 and len(stub.from_calls) == 1
    assert what_now["booking_reachability_source"] == "network_isochrone"
    assert what_now["reachability_source"] == "network_isochrone"
    assert "Inside Temple" in names
    assert "Across Water Cafe" not in names


def test_touched_files_are_ascii():
    for rel in (
        "services/reachability_provider.py",
        "services/ask_service.py",
        "agents/state_machine.py",
        "models/schemas.py",
        "config/settings.py",
        "tests/test_booking_return_reachability.py",
    ):
        assert (REPO_ROOT / rel).read_text(encoding="utf-8").isascii(), rel
    env_lines = (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    added = [line for line in env_lines if line.startswith("TB_REACHABILITY_BOOKING_RETURN")]
    assert added == ["TB_REACHABILITY_BOOKING_RETURN=off"]
    assert all(line.isascii() for line in added)
