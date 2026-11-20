"""Network reachability provider (services/reachability_provider.py) and the
production point-in-polygon (services/geo_polygon.py).

No test opens a real socket: HTTP goes through httpx.MockTransport and an
autouse guard fails any socket connect or DNS lookup.
"""

import asyncio
import importlib.util
import json
import logging
import math
from pathlib import Path

import httpx
import pytest

import services.reachability_provider as rp
from monitoring.spend_circuit import SpendCircuit
from services import geo_polygon
from tests.net_guard import block_external_sockets

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "data" / "isochrone_fixtures"
KEY = "test-maps-key-0123456789abcdef"
LAT, LNG = -6.16091, 39.18963  # House of Wonders


def _square(w, s, e, n):
    return [[w, s], [e, s], [e, n], [w, n], [w, s]]


def _response_around(lat, lng, d=0.01):
    return {
        "isochrone": {
            "geoJson": {
                "type": "MultiPolygon",
                "coordinates": [[_square(lng - d, lat - d, lng + d, lat + d)]],
            }
        }
    }


class _Handler:
    """MockTransport handler: records requests, answers around the origin."""

    def __init__(self, status=200, payload=None, raise_exc=None, raw=None):
        self.calls = []
        self.status, self.payload, self.raise_exc, self.raw = status, payload, raise_exc, raw

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.raw is not None:
            return httpx.Response(self.status, content=self.raw)
        body = json.loads(request.content)
        payload = self.payload or _response_around(
            body["location"]["latitude"], body["location"]["longitude"]
        )
        return httpx.Response(self.status, json=payload)


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _provider(handler, circuit=None, clock=None, key=KEY):
    return rp.GoogleIsochronesProvider(
        key,
        transport=httpx.MockTransport(handler),
        spend_circuit=circuit or SpendCircuit(max_process_usd=100.0, max_identity_usd=100.0),
        clock=clock or _Clock(),
    )


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _no_sockets(monkeypatch):
    block_external_sockets(monkeypatch)
    rp._reset_for_tests()
    yield
    rp._reset_for_tests()


def _load_trial_script():
    path = REPO_ROOT / "scripts" / "isochrone_trial.py"
    spec = importlib.util.spec_from_file_location("isochrone_trial_for_provider_tests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_geo_polygon_matches_trial_script_on_fixtures():
    trial = _load_trial_script()
    fixtures = sorted(FIXTURES.glob("*.geojson"))
    assert len(fixtures) >= 5
    checked = 0
    for path in fixtures:
        feature = json.loads(path.read_text(encoding="utf-8"))
        region = feature["properties"]["region"]
        script_polys = trial.polygons_from_geojson(feature)
        prod_polys = geo_polygon.polygons_from_geojson(feature)
        assert prod_polys == script_polys, path.name
        venues = trial.load_venues(region)
        assert venues, region
        inside = 0
        for v in venues:
            expected = trial.point_in_multipolygon(v["lng"], v["lat"], script_polys)
            got = geo_polygon.point_in_multipolygon(v["lng"], v["lat"], prod_polys)
            assert got == expected, (path.name, v["name"])
            inside += got
            checked += 1
        assert 0 < inside < len(venues), path.name  # fixture splits the catalog
    assert checked > 100


def test_point_in_polygon_respects_hole():
    polygon = [_square(0.0, 0.0, 10.0, 10.0), list(reversed(_square(4.0, 4.0, 6.0, 6.0)))]
    assert geo_polygon.point_in_polygon(1.0, 1.0, polygon) is True
    assert geo_polygon.point_in_polygon(5.0, 5.0, polygon) is False
    assert geo_polygon.point_in_polygon(11.0, 5.0, polygon) is False
    assert geo_polygon.point_in_multipolygon(5.0, 5.0, [polygon]) is False
    assert geo_polygon.point_in_multipolygon(5.0, 5.0, [polygon, [_square(4.5, 4.5, 5.5, 5.5)]])
    # Same answer through every accepted wrapper shape.
    geometry = {"type": "Polygon", "coordinates": polygon}
    for wrapped in (
        geometry,
        {"type": "Feature", "geometry": geometry},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": geometry}]},
        {"isochrone": {"geoJson": json.dumps(geometry)}},
    ):
        polys = geo_polygon.polygons_from_geojson(wrapped)
        assert geo_polygon.point_in_multipolygon(5.0, 5.0, polys) is False
        assert geo_polygon.point_in_multipolygon(1.0, 1.0, polys) is True


def test_request_shape_and_key_in_header_only():
    handler = _Handler()
    result = _run(_provider(handler).walk_isochrone(LAT, LNG, 25, "u1"))
    assert len(handler.calls) == 1
    req = handler.calls[0]
    assert req.method == "POST"
    assert str(req.url) == "https://isochrones.googleapis.com/v1/isochrones:generate"
    assert req.headers["X-Goog-Api-Key"] == KEY
    assert req.headers["X-Goog-FieldMask"] == "*"
    assert req.headers["Content-Type"].startswith("application/json")
    assert json.loads(req.content) == {
        "location": {"latitude": LAT, "longitude": LNG},
        "travelDuration": "1500s",
        "travelMode": "WALK",
        "travelDirection": "FROM",
        "routingPreference": "TRAFFIC_UNAWARE",
        "enableSmoothing": False,
    }
    assert KEY not in str(req.url)
    assert result.minutes == 25 and result.mode == "walk" and result.source == "network_isochrone"
    assert result.observed_at.tzinfo is not None
    assert geo_polygon.point_in_multipolygon(LNG, LAT, result.polygons)


def test_cache_hit_skips_second_http_call():
    handler = _Handler()
    provider = _provider(handler)
    first = _run(provider.walk_isochrone(LAT, LNG, 25, "u1"))
    second = _run(provider.walk_isochrone(LAT + 0.0001, LNG - 0.0001, 25, "u2"))  # same ~100 m key
    assert len(handler.calls) == 1
    assert second is first
    _run(provider.walk_isochrone(LAT, LNG, 45, "u1"))  # different minutes -> new key
    assert len(handler.calls) == 2


def test_cache_expires_after_ttl():
    handler, clock = _Handler(), _Clock()
    provider = _provider(handler, clock=clock)
    _run(provider.walk_isochrone(LAT, LNG, 25, "u1"))
    clock.now += rp.CACHE_TTL_S - 1
    _run(provider.walk_isochrone(LAT, LNG, 25, "u1"))
    assert len(handler.calls) == 1
    clock.now += 1
    _run(provider.walk_isochrone(LAT, LNG, 25, "u1"))
    assert len(handler.calls) == 2


def test_cache_is_bounded():
    handler = _Handler()
    provider = _provider(handler)
    origins = [(10.0 + i * 0.01, 20.0) for i in range(rp.CACHE_MAX_ENTRIES + 1)]
    for lat, lng in origins:
        _run(provider.walk_isochrone(lat, lng, 25, "u1"))
    assert len(provider._cache) == rp.CACHE_MAX_ENTRIES
    calls = len(handler.calls)
    _run(provider.walk_isochrone(*origins[-1], 25, "u1"))  # newest still cached
    assert len(handler.calls) == calls
    _run(provider.walk_isochrone(*origins[0], 25, "u1"))  # oldest insert evicted
    assert len(handler.calls) == calls + 1


def test_spend_cap_raises_before_any_http():
    handler = _Handler()
    capped = SpendCircuit(max_process_usd=0.001, max_identity_usd=0.001)
    with pytest.raises(rp.ReachabilityError) as exc:
        _run(_provider(handler, circuit=capped).walk_isochrone(LAT, LNG, 25, "u1"))
    assert exc.value.code == "spend_capped"
    assert handler.calls == []
    # The module default circuit is dedicated and capped per identity.
    assert rp.isochrone_spend_circuit.max_process_usd == 1.50
    assert rp.isochrone_spend_circuit.max_identity_usd == 0.15


def test_success_records_spend_once_and_cache_hit_records_none():
    handler = _Handler()
    circuit = SpendCircuit(max_process_usd=100.0, max_identity_usd=100.0)
    provider = _provider(handler, circuit=circuit)
    _run(provider.walk_isochrone(LAT, LNG, 25, "u1"))
    assert math.isclose(circuit.spent("u1"), rp.ISOCHRONE_EST_USD_PER_CALL)
    _run(provider.walk_isochrone(LAT, LNG, 25, "u1"))
    _run(provider.walk_isochrone(LAT, LNG, 25, "u2"))
    assert math.isclose(circuit.spent("u1"), rp.ISOCHRONE_EST_USD_PER_CALL)
    assert circuit.spent("u2") == 0
    assert math.isclose(circuit.spent(), rp.ISOCHRONE_EST_USD_PER_CALL)
    assert len(handler.calls) == 1


def test_timeout_maps_to_closed_code():
    circuit = SpendCircuit(max_process_usd=100.0, max_identity_usd=100.0)
    handler = _Handler(raise_exc=httpx.ReadTimeout("slow"))
    with pytest.raises(rp.ReachabilityError) as exc:
        _run(_provider(handler, circuit=circuit).walk_isochrone(LAT, LNG, 25, "u1"))
    assert exc.value.code == "timeout"
    assert circuit.spent() == 0
    handler = _Handler(raise_exc=httpx.ConnectError("down"))
    with pytest.raises(rp.ReachabilityError) as exc:
        _run(_provider(handler).walk_isochrone(LAT, LNG, 25, "u1"))
    assert exc.value.code == "http_error"


def test_non_2xx_maps_to_http_error_and_is_not_cached():
    circuit = SpendCircuit(max_process_usd=100.0, max_identity_usd=100.0)
    handler = _Handler(status=503, payload={"error": {"message": "unavailable"}})
    provider = _provider(handler, circuit=circuit)
    for _ in range(2):
        with pytest.raises(rp.ReachabilityError) as exc:
            _run(provider.walk_isochrone(LAT, LNG, 25, "u1"))
        assert exc.value.code == "http_error"
    assert len(handler.calls) == 2
    assert provider._cache == {}
    assert circuit.spent() == 0
    for raw in (
        b"not json",
        b'{"isochrone": {"geoJson": {"type": "Point"}}}',
        b'{"type": "MultiPolygon", "coordinates": []}',
    ):
        with pytest.raises(rp.ReachabilityError) as exc:
            _run(_provider(_Handler(raw=raw)).walk_isochrone(LAT, LNG, 25, "u1"))
        assert exc.value.code == "parse_error"


def test_origin_outside_polygon_raises_origin_outside():
    far = _response_around(0.0, 0.0)
    circuit = SpendCircuit(max_process_usd=100.0, max_identity_usd=100.0)
    handler = _Handler(payload=far)
    provider = _provider(handler, circuit=circuit)
    with pytest.raises(rp.ReachabilityError) as exc:
        _run(provider.walk_isochrone(LAT, LNG, 25, "u1"))
    assert exc.value.code == "origin_outside"
    assert provider._cache == {}
    assert circuit.spent() == 0


def test_invalid_minutes_rejected_without_io():
    handler = _Handler()
    circuit = SpendCircuit(max_process_usd=100.0, max_identity_usd=100.0)
    provider = _provider(handler, circuit=circuit)
    for lat, lng, minutes in (
        (LAT, LNG, 0),
        (LAT, LNG, 121),
        (LAT, LNG, 25.5),
        (LAT, LNG, True),
        (float("nan"), LNG, 25),
        (LAT, float("inf"), 25),
        (91.0, LNG, 25),
        (LAT, -181.0, 25),
        (None, LNG, 25),
    ):
        with pytest.raises(rp.ReachabilityError) as exc:
            _run(provider.walk_isochrone(lat, lng, minutes, "u1"))
        assert exc.value.code == "invalid_input"
    assert handler.calls == []
    assert circuit.spent() == 0
    _run(provider.walk_isochrone(LAT, LNG, 120, "u1"))  # WALK max accepted
    assert len(handler.calls) == 1


def test_logs_never_contain_key_or_coordinates(caplog):
    caplog.set_level(logging.DEBUG)
    big = SpendCircuit(max_process_usd=100.0, max_identity_usd=100.0)
    capped = SpendCircuit(max_process_usd=0.001, max_identity_usd=0.001)
    ok = _provider(_Handler(), circuit=big)
    cases = [
        (ok, LAT, LNG, 25),  # success
        (ok, LAT, LNG, 25),  # cache hit
        (_provider(_Handler(raise_exc=httpx.ReadTimeout("slow")), circuit=big), LAT, LNG, 30),
        (
            _provider(_Handler(status=500, payload={"error": "boom " + KEY}), circuit=big),
            LAT,
            LNG,
            30,
        ),
        (_provider(_Handler(raw=b"<html>" + str(LAT).encode()), circuit=big), LAT, LNG, 30),
        (_provider(_Handler(payload=_response_around(0.0, 0.0)), circuit=big), LAT, LNG, 30),
        (_provider(_Handler(), circuit=capped), LAT, LNG, 30),
        (_provider(_Handler(), circuit=big), LAT, LNG, 0),
        (_provider(_Handler(), circuit=big, key=""), LAT, LNG, 30),
    ]
    codes = []
    for provider, lat, lng, minutes in cases:
        try:
            _run(provider.walk_isochrone(lat, lng, minutes, "user-log-check"))
            codes.append("ok")
        except rp.ReachabilityError as exc:
            codes.append(exc.code)
    assert set(codes) == {
        "ok",
        "timeout",
        "http_error",
        "parse_error",
        "origin_outside",
        "spend_capped",
        "invalid_input",
        "not_configured",
    }
    text = caplog.text
    for needle in (KEY, str(LAT), str(LNG), "-6.161", "39.19", "<html>", "boom"):
        assert needle not in text, needle
    ours = [r.getMessage() for r in caplog.records if r.name == "travelbuddy"]
    assert ours
    for message in ours:
        provider_part, outcome_part = message.split(" outcome=")
        assert provider_part == "reachability provider=google_isochrones"
        assert outcome_part in rp.ERROR_CODES | {"ok"}


def test_factory_off_by_default_returns_none(monkeypatch):
    from config.settings import Settings, settings

    assert Settings.model_fields["reachability_provider"].default == "off"
    monkeypatch.setattr(settings, "google_maps_api_key", KEY)
    for value in ("off", "", "Google_Isochrones", "google_isochrones ", "on"):
        monkeypatch.setattr(settings, "reachability_provider", value)
        assert rp.get_reachability_provider() is None, value


def test_factory_without_key_returns_none(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "reachability_provider", "google_isochrones")
    for key in (None, "", "   "):
        monkeypatch.setattr(settings, "google_maps_api_key", key)
        assert rp.get_reachability_provider() is None


def test_factory_returns_singleton_when_enabled(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "reachability_provider", "google_isochrones")
    monkeypatch.setattr(settings, "google_maps_api_key", KEY)
    first = rp.get_reachability_provider()
    assert isinstance(first, rp.GoogleIsochronesProvider)
    assert rp.get_reachability_provider() is first
    rp._reset_for_tests()
    assert rp.get_reachability_provider() is not first
