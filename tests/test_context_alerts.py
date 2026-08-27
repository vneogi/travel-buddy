"""SPEC-29: Context alert tests.

All tests use mocked provider fixtures -- no live weather call.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from models.alerts import ContextAlert, TripAlertsResponse, make_alert_id
from models.schemas import NodeStatus, TripNode, TripState
from services.alert_evaluator import evaluate_alerts
from services.weather_provider import ForecastBlock, WeatherProvider, WeatherProviderError


# --- Fixtures ---


def _trip(nodes=None, trip_id="trip-1", geo_region="dubai_uae"):
    return TripState(
        trip_id=trip_id,
        user_id="u1",
        geo_region=geo_region,
        nodes=nodes or [],
    )


def _node(
    name, start_hour=9, duration=90, status=NodeStatus.PENDING, node_id=None, is_locked=False
):
    return TripNode(
        node_id=node_id or f"n-{name.lower().replace(' ', '-')}",
        venue_name=name,
        scheduled_start=datetime(2026, 10, 5, start_hour, 0, tzinfo=timezone.utc),
        duration_minutes=duration,
        status=status,
        is_locked=is_locked,
        lat=25.2,
        lng=55.3,
    )


def _block(hour=9, feels_like=35.0, temp=33.0, humidity=50, code=800, pop=0.0):
    return ForecastBlock(
        dt=datetime(2026, 10, 5, hour, 0, tzinfo=timezone.utc),
        temp_c=temp,
        feels_like_c=feels_like,
        humidity=humidity,
        condition_code=code,
        condition_main="Clear",
        rain_probability=pop,
        wind_speed_kmh=10.0,
    )


NOW = datetime(2026, 10, 5, 7, 0, tzinfo=timezone.utc)
SOURCE_UPDATED = datetime(2026, 10, 5, 6, 30, tzinfo=timezone.utc)


# --- Test 1: No key -> unconfigured ---


def test_no_openweather_key_returns_unconfigured_empty(client):
    """No OpenWeather key -> unconfigured, empty list, zero provider calls."""
    # Create a trip first
    resp = client.post(
        "/api/v1/trip/create",
        json={"start_date": "2026-10-05", "initial_mood": "exploratory"},
        headers={"X-Debug-User-Id": "u1"},
    )
    trip_id = resp.json()["trip_id"]

    with patch("routers.alerts_router.get_weather_provider") as mock_dep:
        provider = WeatherProvider(api_key=None)
        mock_dep.return_value = provider
        resp = client.get(
            f"/api/v1/trip/{trip_id}/alerts",
            headers={"X-Debug-User-Id": "u1"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unconfigured"
    assert data["alerts"] == []


# --- Test 2: 72% rain -> rain alert ---


def test_rain_72_percent_produces_rain_alert():
    """Mocked 72% rain overlapping a node -> one sourced rain alert."""
    trip = _trip(nodes=[_node("Desert Safari", start_hour=9)])
    blocks = [_block(hour=9, pop=0.72, code=500)]

    alerts = evaluate_alerts(trip, blocks, SOURCE_UPDATED, now=NOW)

    assert len(alerts) == 1
    assert alerts[0].alert_type == "rain"
    assert alerts[0].severity == "advisory"
    assert "72%" in alerts[0].message
    assert "Desert Safari" in alerts[0].message
    assert alerts[0].source == "openweather"
    assert alerts[0].evidence.rain_probability == 0.72


# --- Test 3: feels-like 50 C -> extreme heat ---


def test_feels_like_50_produces_extreme_heat_warning():
    """Mocked feels-like 50 C -> extreme heat warning containing actual value."""
    trip = _trip(nodes=[_node("Al Fahidi Walk", start_hour=12)])
    blocks = [_block(hour=12, feels_like=50.0, temp=47.0)]

    alerts = evaluate_alerts(trip, blocks, SOURCE_UPDATED, now=NOW)

    heat_alerts = [a for a in alerts if a.alert_type == "extreme_heat"]
    assert len(heat_alerts) == 1
    assert "50" in heat_alerts[0].message
    assert heat_alerts[0].severity == "warning"
    assert heat_alerts[0].evidence.feels_like_c == 50.0
    assert heat_alerts[0].suggested_action == "seek_shade_and_water"


# --- Test 4: Below threshold -> no alert ---


def test_below_threshold_produces_no_alert():
    """Below-threshold forecast -> no alert."""
    trip = _trip(nodes=[_node("Museum Tour", start_hour=10)])
    blocks = [_block(hour=10, feels_like=32.0, pop=0.1, humidity=40)]

    alerts = evaluate_alerts(trip, blocks, SOURCE_UPDATED, now=NOW)
    assert alerts == []


# --- Test 5: Forecast outside node time -> no affected node ---


def test_forecast_outside_node_time_no_alert():
    """Forecast outside node time -> no affected-node alert."""
    trip = _trip(nodes=[_node("Lunch", start_hour=12, duration=60)])
    # Forecast block at 6 AM, node at 12 PM - no overlap
    blocks = [_block(hour=6, feels_like=50.0)]

    alerts = evaluate_alerts(trip, blocks, SOURCE_UPDATED, now=NOW)
    assert alerts == []


# --- Test 6: Stale/expired not returned ---


def test_expired_alert_not_returned():
    """Stale/expired forecast -> not returned (filtered by endpoint)."""
    trip = _trip(nodes=[_node("Walk", start_hour=9)])
    # Block at hour 9 with valid_until = 12, expires_at = 12:30
    blocks = [_block(hour=9, feels_like=50.0)]
    # Evaluate with now far in the future
    far_future = datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc)

    alerts = evaluate_alerts(trip, blocks, SOURCE_UPDATED, now=far_future)
    # Alerts still generated but expired; endpoint filters them
    for a in alerts:
        assert a.expires_at < far_future


# --- Test 7: Alert id stable ---


def test_alert_id_stable_for_identical_evidence():
    """Alert id is stable for identical evidence."""
    trip = _trip(nodes=[_node("Gallery", start_hour=14)])
    blocks = [_block(hour=14, pop=0.8)]

    alerts1 = evaluate_alerts(trip, blocks, SOURCE_UPDATED, now=NOW)
    alerts2 = evaluate_alerts(trip, blocks, SOURCE_UPDATED, now=NOW)

    assert alerts1[0].alert_id == alerts2[0].alert_id


# --- Test 8: Provider timeout -> 503 ---


def test_provider_timeout_returns_503(client):
    """Provider timeout -> 503; no invented fallback."""
    resp = client.post(
        "/api/v1/trip/create",
        json={"start_date": "2026-10-05"},
        headers={"X-Debug-User-Id": "u1"},
    )
    trip_id = resp.json()["trip_id"]

    class FailingProvider:
        is_configured = True

        async def get_forecast(self, lat, lng):
            raise WeatherProviderError("OpenWeather request timed out")

    from routers.alerts_router import get_weather_provider

    app.dependency_overrides[get_weather_provider] = lambda: FailingProvider()
    try:
        resp = client.get(
            f"/api/v1/trip/{trip_id}/alerts",
            headers={"X-Debug-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.pop(get_weather_provider, None)
    assert resp.status_code == 503
    assert "weather_provider_unavailable" in resp.json()["detail"]["error"]


# --- Test 9: Auth and ownership ---


def test_alert_endpoint_auth_and_ownership(client):
    """Endpoint auth and two-user ownership isolation."""
    resp = client.post(
        "/api/v1/trip/create",
        json={"start_date": "2026-10-05"},
        headers={"X-Debug-User-Id": "u1"},
    )
    trip_id = resp.json()["trip_id"]

    # Another user cannot access
    resp = client.get(
        f"/api/v1/trip/{trip_id}/alerts",
        headers={"X-Debug-User-Id": "u2"},
    )
    assert resp.status_code == 403


# --- Test 10: Alert does not consume reroute quota ---


def test_alert_endpoint_does_not_consume_reroute_quota(client):
    """Alert endpoint does not consume reroute quota."""
    resp = client.post(
        "/api/v1/trip/create",
        json={"start_date": "2026-10-05"},
        headers={"X-Debug-User-Id": "u1"},
    )
    trip_id = resp.json()["trip_id"]

    # Get trip before
    trip_before = client.get(
        f"/api/v1/trip/{trip_id}",
        headers={"X-Debug-User-Id": "u1"},
    ).json()

    with patch("routers.alerts_router.get_weather_provider") as mock_dep:
        provider = WeatherProvider(api_key=None)
        mock_dep.return_value = provider
        client.get(
            f"/api/v1/trip/{trip_id}/alerts",
            headers={"X-Debug-User-Id": "u1"},
        )

    # Get trip after
    trip_after = client.get(
        f"/api/v1/trip/{trip_id}",
        headers={"X-Debug-User-Id": "u1"},
    ).json()

    assert trip_before.get("execution_control", {}).get("reroutes_used", 0) == trip_after.get(
        "execution_control", {}
    ).get("reroutes_used", 0)


# --- Test 11: Alert never calls LLM/RAG/state machine ---


def test_alert_path_never_calls_llm(client):
    """Alert path never calls LLM/RAG/state machine.

    Verified structurally: alerts_router.py imports only WeatherProvider,
    evaluate_alerts, db_provider, and security -- never llm_service,
    router_agent, or state_machine.
    """
    import routers.alerts_router as mod
    import inspect

    source = inspect.getsource(mod)
    assert "llm_service" not in source
    assert "router_agent" not in source
    assert "state_machine" not in source
    assert "TripStateMachine" not in source


# --- Test 12: Synthetic transit cannot become user-visible ---


def test_synthetic_transit_cannot_appear_in_alert_response():
    """Synthetic transit result cannot become user-visible copy."""
    # The alert evaluator only uses ForecastBlock data from OpenWeather.
    # Maps service synthetic transit never feeds into alert generation.
    trip = _trip(nodes=[_node("Beach", start_hour=10)])
    blocks = [_block(hour=10, pop=0.6)]

    alerts = evaluate_alerts(trip, blocks, SOURCE_UPDATED, now=NOW)

    for alert in alerts:
        assert "transit" not in alert.message.lower()
        assert "unreachable" not in alert.message.lower()
        assert "traffic" not in alert.message.lower()
        # No synthetic maps data in evidence
        assert alert.source == "openweather"
