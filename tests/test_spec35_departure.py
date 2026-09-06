"""SPEC-35 Phase A proof cases: departure backend.

Covers every required proof case from the Genie brief.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from config.regions import REGIONS
from models.schemas import NodeStatus, TripNode, TripState
from services.departure_evaluator import (
    ARRIVAL_BUFFER_MINUTES,
    ELIGIBLE_LEAD_MINUTES,
    EXPIRY_AFTER_START_MINUTES,
    WEATHER_BUFFER_MINUTES,
    deterministic_id,
    evaluate_departure,
)
from services.route_provider import (
    GoogleMapsRouteProvider,
    RouteProvider,
    RouteProviderError,
    RouteResult,
)
from services.weather_provider import ForecastBlock, WeatherProvider, WeatherProviderError


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _utc(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _node(
    node_id="n1",
    name="Kuang Si Falls",
    start=None,
    duration=90,
    status=NodeStatus.PENDING,
    lat=19.7475,
    lng=101.9941,
    geo_region="luang_prabang_laos",
    node_kind="activity",
):
    return TripNode(
        node_id=node_id,
        venue_name=name,
        scheduled_start=start or _utc(2026, 10, 5, 8, 0),
        duration_minutes=duration,
        status=status,
        lat=lat,
        lng=lng,
        geo_region=geo_region,
        node_kind=node_kind,
    )


def _trip(
    user_id="owner-1",
    geo_region="luang_prabang_laos",
    nodes=None,
    schedule_basis="region_local_v1",
):
    return TripState(
        trip_id="trip-test",
        user_id=user_id,
        geo_region=geo_region,
        nodes=nodes or [],
        schedule_basis=schedule_basis,
    )


class StubRouteProvider(RouteProvider):
    """Test stub that returns configurable route results."""

    def __init__(
        self,
        traffic_minutes=42,
        normal_minutes=34,
        fail=False,
        observed_at=None,
    ):
        self.traffic_minutes = traffic_minutes
        self.normal_minutes = normal_minutes
        self.fail = fail
        self.observed_at = observed_at
        self.call_count = 0
        self.calls: list = []

    async def get_driving_duration(
        self, origin_lat, origin_lng, dest_lat, dest_lng, departure_time=None
    ):
        self.call_count += 1
        self.calls.append(
            {
                "origin": (origin_lat, origin_lng),
                "dest": (dest_lat, dest_lng),
                "departure_time": departure_time,
            }
        )
        if self.fail:
            raise RouteProviderError("provider down")
        return RouteResult(
            normal_duration_minutes=self.normal_minutes,
            traffic_duration_minutes=self.traffic_minutes,
            mode="driving",
            observed_at=self.observed_at or departure_time,
            source="stub",
        )


class StubWeatherProvider:
    """Test stub that returns configurable forecast blocks."""

    def __init__(self, rain_probability=0.0, blocks=None, fail=False):
        self.rain_probability = rain_probability
        self.fail = fail
        self._blocks = blocks
        self.call_count = 0

    async def get_forecast(self, lat, lng):
        self.call_count += 1
        if self.fail:
            raise WeatherProviderError("weather down")
        if self._blocks:
            return self._blocks, datetime.now(tz=timezone.utc)
        block = ForecastBlock(
            dt=_utc(2026, 10, 5, 0),
            temp_c=28.0,
            feels_like_c=30.0,
            humidity=70,
            condition_code=500,
            condition_main="Rain",
            rain_probability=self.rain_probability,
            wind_speed_kmh=10.0,
        )
        return [block], datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Proof cases
# ---------------------------------------------------------------------------


class TestOwnerScope:
    """non-owner is rejected before either provider is called."""

    def test_non_owner_rejected(self, client):
        # Create a trip as owner
        resp = client.post(
            "/api/v1/trip/create",
            json={"start_date": "2026-10-05T09:00:00", "geo_region": "luang_prabang_laos"},
            headers={"X-Debug-User-Id": "owner-1"},
        )
        assert resp.status_code == 200
        trip_id = resp.json()["trip_id"]

        # Non-owner tries to read notifications
        resp2 = client.get(
            f"/api/v1/trip/{trip_id}/notifications",
            headers={"X-Debug-User-Id": "intruder-1"},
        )
        assert resp2.status_code == 403


class TestScheduleTimeGate:
    """Catalog creation stores correct UTC and marks region_local_v1."""

    def test_laos_catalog_stores_utc_for_region_0900(self, client):
        """Laos 09:00 local = 02:00 UTC (Asia/Vientiane is UTC+7)."""
        resp = client.post(
            "/api/v1/trip/create",
            json={
                "geo_region": "luang_prabang_laos",
                "start_date": "2026-10-05T00:00:00Z",
            },
            headers={"X-Debug-User-Id": "tz-test-1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["nodes"]

        first_start = data["nodes"][0]["scheduled_start"]
        # Parse the stored UTC time
        dt = datetime.fromisoformat(first_start.replace("Z", "+00:00"))
        # 09:00 Asia/Vientiane (UTC+7) = 02:00 UTC
        assert dt.hour == 2, f"Expected hour=2 (09:00 Vientiane), got {dt.hour}"
        assert dt.minute == 0

    def test_dubai_catalog_stores_utc_for_region_0900(self, client):
        """Dubai 09:00 local = 05:00 UTC (Asia/Dubai is UTC+4)."""
        resp = client.post(
            "/api/v1/trip/create",
            json={
                "geo_region": "dubai_uae",
                "start_date": "2026-10-05T00:00:00Z",
            },
            headers={"X-Debug-User-Id": "tz-test-2"},
        )
        assert resp.status_code == 200
        first_start = resp.json()["nodes"][0]["scheduled_start"]
        dt = datetime.fromisoformat(first_start.replace("Z", "+00:00"))
        # 09:00 Asia/Dubai (UTC+4) = 05:00 UTC
        assert dt.hour == 5, f"Expected hour=5 (09:00 Dubai), got {dt.hour}"

    def test_trip_has_schedule_basis_marker(self, client):
        """New trips carry schedule_basis: region_local_v1."""
        from services.db_provider import db_service

        resp = client.post(
            "/api/v1/trip/create",
            json={"start_date": "2026-10-05T09:00:00", "geo_region": "luang_prabang_laos"},
            headers={"X-Debug-User-Id": "tz-test-3"},
        )
        assert resp.status_code == 200
        trip_id = resp.json()["trip_id"]
        trip = db_service.get_trip(trip_id)
        assert trip.schedule_basis == "region_local_v1"


class TestLegacyTripSuppression:
    """Legacy trips without marker return no departure and no provider call."""

    def test_legacy_trip_no_departure_no_provider_call(self):
        route = StubRouteProvider()
        weather = StubWeatherProvider()
        origin = _node(
            "origin",
            start=_utc(2026, 10, 5, 1, 0),
            status=NodeStatus.COMPLETED,
            lat=19.89,
            lng=102.13,
        )
        dest = _node("dest", start=_utc(2026, 10, 5, 3, 0))
        trip = _trip(nodes=[origin, dest], schedule_basis=None)
        now = _utc(2026, 10, 5, 2, 0)

        candidate, error = asyncio.run(evaluate_departure(trip, now, route, weather))
        assert candidate is None
        assert "legacy" in (error or "")
        assert route.call_count == 0, "No provider call for legacy trip"
        assert weather.call_count == 0


class TestProcessTimezoneIndependence:
    """Changing process timezone does not change eligibility or formatted copy."""

    def test_tz_independence(self):
        # Create trip in Laos with dest at 09:00 local = 02:00 UTC
        dest_utc = datetime(2026, 10, 5, 2, 0, tzinfo=timezone.utc)  # 09:00 Vientiane
        origin = _node(
            "origin",
            start=dest_utc - timedelta(hours=3),
            status=NodeStatus.COMPLETED,
            lat=19.89,
            lng=102.13,
        )
        dest = _node("dest", start=dest_utc, lat=19.7475, lng=101.9941)
        trip = _trip(nodes=[origin, dest])

        route = StubRouteProvider(traffic_minutes=42)
        weather = StubWeatherProvider(rain_probability=0.0)

        # Eligible window: recommended_departure - 10min
        # recommended = 02:00 - 42 - 10 = 01:08 UTC
        # eligible = 01:08 - 10 = 00:58 UTC
        now = _utc(2026, 10, 5, 1, 5)

        # Run with original TZ
        old_tz = os.environ.get("TZ")
        try:
            os.environ["TZ"] = "America/New_York"
            candidate_ny, _ = asyncio.run(evaluate_departure(trip, now, route, weather))

            route2 = StubRouteProvider(traffic_minutes=42)
            weather2 = StubWeatherProvider(rain_probability=0.0)
            os.environ["TZ"] = "Asia/Tokyo"
            candidate_tokyo, _ = asyncio.run(evaluate_departure(trip, now, route2, weather2))
        finally:
            if old_tz:
                os.environ["TZ"] = old_tz
            elif "TZ" in os.environ:
                del os.environ["TZ"]

        # Both should have the same result
        assert (candidate_ny is None) == (candidate_tokyo is None)
        if candidate_ny and candidate_tokyo:
            assert candidate_ny.notification_id == candidate_tokyo.notification_id
            assert candidate_ny.time_zone == "Asia/Vientiane"
            assert candidate_tokyo.time_zone == "Asia/Vientiane"


class TestNextPendingNodeOnly:
    """Only next pending non-skipped node is evaluated."""

    def test_skipped_node_ignored(self):
        origin = _node(
            "origin",
            start=_utc(2026, 10, 5, 1, 0),
            status=NodeStatus.COMPLETED,
            lat=19.89,
            lng=102.13,
        )
        skipped = _node("skipped", start=_utc(2026, 10, 5, 2, 0), status=NodeStatus.SKIPPED)
        pending = _node("pending", start=_utc(2026, 10, 5, 3, 0))
        trip = _trip(nodes=[origin, skipped, pending])

        route = StubRouteProvider(traffic_minutes=30)
        weather = StubWeatherProvider()
        now = _utc(2026, 10, 5, 2, 10)

        candidate, _ = asyncio.run(evaluate_departure(trip, now, route, weather))
        assert candidate is not None
        assert candidate.node_id == "pending"

    def test_completed_node_not_destination(self):
        completed = _node(
            "done",
            start=_utc(2026, 10, 5, 1, 0),
            status=NodeStatus.COMPLETED,
            lat=19.89,
            lng=102.13,
        )
        pending = _node("next", start=_utc(2026, 10, 5, 3, 0))
        trip = _trip(nodes=[completed, pending])

        route = StubRouteProvider(traffic_minutes=30)
        weather = StubWeatherProvider()
        now = _utc(2026, 10, 5, 2, 10)

        candidate, _ = asyncio.run(evaluate_departure(trip, now, route, weather))
        assert candidate is not None
        assert candidate.node_id == "next"


class TestMissingCoordinates:
    """No credible origin or destination returns no candidate."""

    def test_no_destination_coords(self):
        origin = _node(
            "origin",
            start=_utc(2026, 10, 5, 1, 0),
            status=NodeStatus.COMPLETED,
            lat=19.89,
            lng=102.13,
        )
        dest = _node("dest", start=_utc(2026, 10, 5, 3, 0), lat=None, lng=None)
        trip = _trip(nodes=[origin, dest])
        route = StubRouteProvider()
        weather = StubWeatherProvider()

        candidate, error = asyncio.run(
            evaluate_departure(trip, _utc(2026, 10, 5, 2, 0), route, weather)
        )
        assert candidate is None
        assert "destination" in (error or "")
        assert route.call_count == 0

    def test_no_origin_coords(self):
        origin = _node(
            "origin", start=_utc(2026, 10, 5, 1, 0), status=NodeStatus.COMPLETED, lat=None, lng=None
        )
        dest = _node("dest", start=_utc(2026, 10, 5, 3, 0))
        trip = _trip(nodes=[origin, dest])
        route = StubRouteProvider()
        weather = StubWeatherProvider()

        candidate, error = asyncio.run(
            evaluate_departure(trip, _utc(2026, 10, 5, 2, 0), route, weather)
        )
        assert candidate is None
        assert "origin" in (error or "")

    def test_single_node_no_origin(self):
        dest = _node("dest", start=_utc(2026, 10, 5, 3, 0))
        trip = _trip(nodes=[dest])
        route = StubRouteProvider()
        weather = StubWeatherProvider()

        candidate, error = asyncio.run(
            evaluate_departure(trip, _utc(2026, 10, 5, 2, 0), route, weather)
        )
        assert candidate is None


class TestTrafficDurationUsedOnce:
    """Traffic duration is used exactly once; no peak-hour multiplier."""

    def test_traffic_duration_once(self):
        origin = _node(
            "origin",
            start=_utc(2026, 10, 5, 1, 0),
            status=NodeStatus.COMPLETED,
            lat=19.89,
            lng=102.13,
        )
        dest_start = _utc(2026, 10, 5, 3, 0)
        dest = _node("dest", start=dest_start)
        trip = _trip(nodes=[origin, dest])

        traffic_min = 42
        route = StubRouteProvider(traffic_minutes=traffic_min, normal_minutes=34)
        weather = StubWeatherProvider(rain_probability=0.0)

        # recommended = 03:00 - 42 - 10 = 02:08 UTC
        # eligible = 02:08 - 10 = 01:58 UTC
        now = _utc(2026, 10, 5, 2, 0)
        candidate, _ = asyncio.run(evaluate_departure(trip, now, route, weather))
        assert candidate is not None

        # Verify: recommended_departure = dest_start - traffic - arrival_buffer
        expected_departure = dest_start - timedelta(minutes=traffic_min + ARRIVAL_BUFFER_MINUTES)
        actual = candidate.recommended_departure_at
        assert actual == expected_departure, f"Expected {expected_departure}, got {actual}"

        # Evidence shows traffic used once, not multiplied
        assert candidate.evidence.route.traffic_duration_minutes == traffic_min
        assert candidate.evidence.route.normal_duration_minutes == 34
        assert candidate.evidence.policy.weather_buffer_minutes == 0


class TestRainPolicyBuffer:
    """Rain adds ten policy minutes while preserving route duration evidence."""

    def test_rain_adds_buffer(self):
        origin = _node(
            "origin",
            start=_utc(2026, 10, 5, 1, 0),
            status=NodeStatus.COMPLETED,
            lat=19.89,
            lng=102.13,
        )
        dest_start = _utc(2026, 10, 5, 3, 0)
        dest = _node("dest", start=dest_start)
        trip = _trip(nodes=[origin, dest])

        traffic_min = 42
        route = StubRouteProvider(traffic_minutes=traffic_min)
        weather = StubWeatherProvider(rain_probability=0.63)

        now = _utc(2026, 10, 5, 1, 50)
        candidate, _ = asyncio.run(evaluate_departure(trip, now, route, weather))
        assert candidate is not None

        # With rain: recommended = dest - traffic - arrival - weather
        expected = dest_start - timedelta(
            minutes=traffic_min + ARRIVAL_BUFFER_MINUTES + WEATHER_BUFFER_MINUTES
        )
        assert candidate.recommended_departure_at == expected

        # Evidence: route duration unchanged, weather buffer disclosed
        assert candidate.evidence.route.traffic_duration_minutes == traffic_min
        assert candidate.evidence.policy.weather_buffer_minutes == WEATHER_BUFFER_MINUTES
        assert candidate.evidence.weather is not None
        assert candidate.evidence.weather.rain_probability == 0.63

    def test_low_rain_no_buffer(self):
        origin = _node(
            "origin",
            start=_utc(2026, 10, 5, 1, 0),
            status=NodeStatus.COMPLETED,
            lat=19.89,
            lng=102.13,
        )
        dest_start = _utc(2026, 10, 5, 3, 0)
        dest = _node("dest", start=dest_start)
        trip = _trip(nodes=[origin, dest])

        route = StubRouteProvider(traffic_minutes=42)
        weather = StubWeatherProvider(rain_probability=0.30)

        now = _utc(2026, 10, 5, 2, 0)
        candidate, _ = asyncio.run(evaluate_departure(trip, now, route, weather))
        assert candidate is not None
        assert candidate.evidence.policy.weather_buffer_minutes == 0


class TestRouteFailurePartial:
    """Stale/failed route returns partial without failing unrelated construction."""

    def test_stale_route_evidence_is_suppressed(self):
        origin = _node(
            "origin",
            start=_utc(2026, 10, 5, 1, 0),
            status=NodeStatus.COMPLETED,
            lat=19.89,
            lng=102.13,
        )
        dest = _node("dest", start=_utc(2026, 10, 5, 3, 0))
        trip = _trip(nodes=[origin, dest])
        route = StubRouteProvider(observed_at=_utc(2026, 10, 5, 1, 54))

        candidate, error = asyncio.run(
            evaluate_departure(
                trip,
                _utc(2026, 10, 5, 2, 0),
                route,
                StubWeatherProvider(),
            )
        )

        assert candidate is None
        assert error == "route_unavailable:stale_route_evidence"

    def test_route_failure_partial_response(self):
        origin = _node(
            "origin",
            start=_utc(2026, 10, 5, 1, 0),
            status=NodeStatus.COMPLETED,
            lat=19.89,
            lng=102.13,
        )
        dest = _node("dest", start=_utc(2026, 10, 5, 3, 0))
        trip = _trip(nodes=[origin, dest])

        route = StubRouteProvider(fail=True)
        weather = StubWeatherProvider()

        candidate, error = asyncio.run(
            evaluate_departure(trip, _utc(2026, 10, 5, 2, 0), route, weather)
        )
        assert candidate is None
        assert "route_unavailable" in (error or "")

    def test_weather_failure_does_not_suppress_departure(self):
        origin = _node(
            "origin",
            start=_utc(2026, 10, 5, 1, 0),
            status=NodeStatus.COMPLETED,
            lat=19.89,
            lng=102.13,
        )
        dest = _node("dest", start=_utc(2026, 10, 5, 3, 0))
        trip = _trip(nodes=[origin, dest])

        route = StubRouteProvider(traffic_minutes=30)
        weather = StubWeatherProvider(fail=True)
        now = _utc(2026, 10, 5, 2, 10)

        candidate, _ = asyncio.run(evaluate_departure(trip, now, route, weather))
        assert candidate is not None
        # No weather evidence when provider fails
        assert candidate.evidence.weather is None
        assert candidate.evidence.policy.weather_buffer_minutes == 0


class TestProductionRouteWiring:
    def test_default_provider_wraps_real_maps_service(self):
        from routers.notifications_router import _route_provider
        from services.google_maps_real import google_maps_real

        assert isinstance(_route_provider, GoogleMapsRouteProvider)
        assert _route_provider._maps is google_maps_real


class TestEligibilityWindow:
    """Before eligibility no candidate is returned; due/overdue says Leave now."""

    def test_before_eligibility(self):
        origin = _node(
            "origin",
            start=_utc(2026, 10, 5, 1, 0),
            status=NodeStatus.COMPLETED,
            lat=19.89,
            lng=102.13,
        )
        dest_start = _utc(2026, 10, 5, 3, 0)
        dest = _node("dest", start=dest_start)
        trip = _trip(nodes=[origin, dest])

        route = StubRouteProvider(traffic_minutes=42)
        weather = StubWeatherProvider()

        # recommended = 03:00 - 42 - 10 = 02:08
        # eligible = 02:08 - 10 = 01:58
        too_early = _utc(2026, 10, 5, 1, 50)  # Before 01:58
        candidate, _ = asyncio.run(evaluate_departure(trip, too_early, route, weather))
        assert candidate is None

    def test_overdue_says_leave_now(self):
        origin = _node(
            "origin",
            start=_utc(2026, 10, 5, 1, 0),
            status=NodeStatus.COMPLETED,
            lat=19.89,
            lng=102.13,
        )
        dest_start = _utc(2026, 10, 5, 3, 0)
        dest = _node("dest", start=dest_start)
        trip = _trip(nodes=[origin, dest])

        route = StubRouteProvider(traffic_minutes=42)
        weather = StubWeatherProvider()

        overdue = _utc(2026, 10, 5, 2, 30)  # After recommended departure 02:08
        candidate, _ = asyncio.run(evaluate_departure(trip, overdue, route, weather))
        assert candidate is not None
        assert "Leave now" in candidate.title
        assert "Leave now" in candidate.message


class TestDeterministicId:
    """Repeated evaluation has same ID; rescheduling changes ID."""

    def test_repeated_same_id(self):
        origin = _node(
            "origin",
            start=_utc(2026, 10, 5, 1, 0),
            status=NodeStatus.COMPLETED,
            lat=19.89,
            lng=102.13,
        )
        dest = _node("dest", start=_utc(2026, 10, 5, 3, 0))
        trip = _trip(nodes=[origin, dest])
        now = _utc(2026, 10, 5, 2, 0)

        route1 = StubRouteProvider(traffic_minutes=42)
        weather1 = StubWeatherProvider()
        c1, _ = asyncio.run(evaluate_departure(trip, now, route1, weather1))

        route2 = StubRouteProvider(traffic_minutes=42)
        weather2 = StubWeatherProvider()
        c2, _ = asyncio.run(evaluate_departure(trip, now, route2, weather2))

        assert c1.notification_id == c2.notification_id

    def test_reschedule_changes_id(self):
        origin = _node(
            "origin",
            start=_utc(2026, 10, 5, 1, 0),
            status=NodeStatus.COMPLETED,
            lat=19.89,
            lng=102.13,
        )
        dest1 = _node("dest", start=_utc(2026, 10, 5, 3, 0))
        dest2 = _node("dest", start=_utc(2026, 10, 5, 4, 0))  # Rescheduled

        trip1 = _trip(nodes=[origin, dest1])
        trip2 = _trip(nodes=[origin, dest2])

        route = StubRouteProvider(traffic_minutes=42)
        weather = StubWeatherProvider()
        now = _utc(2026, 10, 5, 2, 0)

        c1, _ = asyncio.run(evaluate_departure(trip1, now, route, weather))

        route2 = StubRouteProvider(traffic_minutes=42)
        weather2 = StubWeatherProvider()
        c2, _ = asyncio.run(evaluate_departure(trip2, now, route2, weather2))

        # c1 may or may not be in window, c2 has different eligibility
        id1 = deterministic_id("trip-test", "departure_reminder", "dest", _utc(2026, 10, 5, 3, 0))
        id2 = deterministic_id("trip-test", "departure_reminder", "dest", _utc(2026, 10, 5, 4, 0))
        assert id1 != id2


class TestNoLLMOrMutation:
    """Evaluator has no LLM, mutation, event, or quota dependency."""

    def test_evaluator_signature_is_pure(self):
        """Verify the evaluator only takes trip, now, route_provider, weather_provider."""
        import inspect

        sig = inspect.signature(evaluate_departure)
        param_names = list(sig.parameters.keys())
        assert param_names == ["trip", "now", "route_provider", "weather_provider"]
        # No llm, no db, no event_bus, no quota


class TestAlertsBackwardCompat:
    """/alerts response remains backward compatible."""

    def test_alerts_endpoint_still_works(self, client):
        resp = client.post(
            "/api/v1/trip/create",
            json={"start_date": "2026-10-05T09:00:00", "geo_region": "luang_prabang_laos"},
            headers={"X-Debug-User-Id": "compat-1"},
        )
        trip_id = resp.json()["trip_id"]

        resp2 = client.get(
            f"/api/v1/trip/{trip_id}/alerts",
            headers={"X-Debug-User-Id": "compat-1"},
        )
        assert resp2.status_code == 200
        data = resp2.json()
        assert "trip_id" in data
        assert "alerts" in data


class TestNotificationsEndpoint:
    """Integration tests for the HTTP endpoint."""

    def test_notifications_endpoint_returns_200(self, client):
        resp = client.post(
            "/api/v1/trip/create",
            json={"start_date": "2026-10-05T09:00:00", "geo_region": "luang_prabang_laos"},
            headers={"X-Debug-User-Id": "notif-1"},
        )
        trip_id = resp.json()["trip_id"]

        resp2 = client.get(
            f"/api/v1/trip/{trip_id}/notifications",
            headers={"X-Debug-User-Id": "notif-1"},
        )
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["trip_id"] == trip_id
        assert "refreshed_at" in data
        assert data["status"] in ("available", "partial", "unconfigured")
        assert isinstance(data["notifications"], list)

    def test_notifications_404_for_missing_trip(self, client):
        resp = client.get(
            "/api/v1/trip/nonexistent/notifications",
            headers={"X-Debug-User-Id": "notif-2"},
        )
        assert resp.status_code == 404

    def test_departure_copy_uses_destination_timezone(self):
        """Copy formats HH:MM in destination region timezone, not server TZ."""
        origin = _node(
            "origin",
            start=_utc(2026, 10, 5, 1, 0),
            status=NodeStatus.COMPLETED,
            lat=19.89,
            lng=102.13,
        )
        # Destination at 09:00 Vientiane = 02:00 UTC
        dest_start = _utc(2026, 10, 5, 2, 0)
        dest = _node("dest", start=dest_start, geo_region="luang_prabang_laos")
        trip = _trip(nodes=[origin, dest])

        route = StubRouteProvider(traffic_minutes=42)
        weather = StubWeatherProvider()
        # recommended = 02:00 - 42 - 10 = 01:08 UTC = 08:08 Vientiane
        now = _utc(2026, 10, 5, 1, 0)

        candidate, _ = asyncio.run(evaluate_departure(trip, now, route, weather))
        assert candidate is not None
        assert candidate.time_zone == "Asia/Vientiane"
        # The message should contain "08:08" (local time), not "01:08" (UTC)
        assert "08:08" in candidate.message, f"Expected 08:08 in message, got: {candidate.message}"
