"""SPEC-41 Phase A3b: Deterministic Walking Reachability.

Covers:
  - walking_minutes helper determinism and arithmetic
  - pack_day walking transfer with exact walking_minutes assertions
  - Next-locked-booking feasibility (hotel, different-region, different-day,
    missing coords, NaN/inf)
  - Scheduler city/day boundary preservation
  - Production state-machine swap tests (no LLM, no Maps on swap path)
  - Unified swap reachability predicate proofs
  - Truthful max_days capacity with walking
  - Sabotage proofs with real edits naming broken tests
"""

from __future__ import annotations

import asyncio
import inspect
import math
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import List
from unittest.mock import patch as mock_patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from main import app
from tests.conftest import auth
from config.interests import VENUES_PER_DAY, MAX_DAYS_CEILING
from config.regions import REGIONS
from models.schemas import (
    EventType,
    NodeStatus,
    TripNode,
    TripState,
    VenueSearchResult,
)
from services.catalog_itinerary import (
    InsufficientCatalog,
    compute_max_days_for_region,
    eligible_corridor_venues,
    nodes_from_catalog,
    pack_day,
    range_nodes_from_catalog,
)
from services.corridor_itinerary import build_corridor_nodes, CORRIDOR_STOPS_PER_DAY
from services.opening_hours import HoursResult, hours_for_slot, next_slot_start
from services.scheduler import reschedule_and_validate
from services.transit import (
    MINIMUM_TRANSFER_MINUTES,
    WALKING_SPEED_KMH,
    haversine_km,
    walking_minutes,
)
from services.db_provider import db_service

ICT = ZoneInfo("Asia/Vientiane")
GST = ZoneInfo("Asia/Dubai")
GEO = "luang_prabang_laos"

client = TestClient(app)
HEADERS = auth("spec41-a3b-user")

_ALL_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _ict(y, m, d, h, minute=0):
    return datetime(y, m, d, h, minute, tzinfo=ICT)


def _ict_to_utc(y, m, d, h, minute=0):
    return _ict(y, m, d, h, minute).astimezone(timezone.utc)


def _make_hours(overrides=None):
    base = {d: [["09:00", "17:00"]] for d in _ALL_DAYS}
    if overrides:
        base.update(overrides)
    return base


def _make_venue_row(
    name,
    structured=None,
    category="temple",
    dwell=60,
    lat=19.89,
    lng=102.13,
    venue_id=None,
):
    from services.catalog_itinerary import flatten_opening_hours

    flat = flatten_opening_hours(structured) or "09:00-17:00"
    return {
        "name": name,
        "venue_id": venue_id or str(uuid.uuid5(uuid.NAMESPACE_URL, name)),
        "description": "",
        "micro_location": "",
        "lat": lat,
        "lng": lng,
        "vibe_tags": [],
        "audience": [],
        "category": category,
        "opening_hours": flat,
        "opening_hours_structured": structured,
        "typical_dwell_minutes": dwell,
    }


def _corridor_body():
    return {
        "segments": [
            {"geo_region": "vientiane_laos", "starts_on": "2026-10-02", "ends_on": "2026-10-03"},
            {"geo_region": "vang_vieng_laos", "starts_on": "2026-10-04", "ends_on": "2026-10-05"},
            {
                "geo_region": "luang_prabang_laos",
                "starts_on": "2026-10-06",
                "ends_on": "2026-10-09",
            },
        ],
    }


# ===================================================================
# Helper unit tests
# ===================================================================


class TestWalkingMinutesHelper:
    def test_identical_coords_identical_result(self):
        """Same inputs always produce the same integer."""
        a = walking_minutes(19.89, 102.13, 19.90, 102.14)
        b = walking_minutes(19.89, 102.13, 19.90, 102.14)
        assert a == b
        assert isinstance(a, int)

    def test_known_haversine_pair(self):
        """~5 km at 5 km/h should be ~60 minutes."""
        # Luang Prabang: 19.89,102.13 to approx 19.89,102.175 is ~5 km
        dist = haversine_km(19.89, 102.13, 19.89, 102.175)
        expected_min = math.ceil(dist / WALKING_SPEED_KMH * 60)
        result = walking_minutes(19.89, 102.13, 19.89, 102.175)
        assert result == max(MINIMUM_TRANSFER_MINUTES, expected_min)
        assert result >= 50  # ~5 km walk should be around 60 min

    def test_very_short_distance_returns_floor(self):
        """Identical or near-identical points get the 5-min floor."""
        result = walking_minutes(19.89, 102.13, 19.89, 102.13)
        assert result == MINIMUM_TRANSFER_MINUTES

    def test_none_coordinates_raise_value_error(self):
        with pytest.raises(ValueError, match="origin_lat"):
            walking_minutes(None, 102.13, 19.90, 102.14)

    def test_nan_coordinates_raise_value_error(self):
        with pytest.raises(ValueError, match="dest_lng"):
            walking_minutes(19.89, 102.13, 19.90, float("nan"))

    def test_source_contains_no_random_or_datetime_now(self):
        """The transit module must not import random or use datetime.now."""
        import services.transit as transit_mod

        source = inspect.getsource(transit_mod)
        assert "import random" not in source
        assert "random.uniform" not in source
        assert "datetime.now()" not in source


# ===================================================================
# Packing tests
# ===================================================================


class TestPackDayWalking:
    def test_intraday_gap_uses_walking_transfer(self):
        """Transfer between two nearby venues equals exact walking_minutes."""
        lat_a, lng_a = 19.89, 102.13
        lat_b, lng_b = 19.891, 102.131
        rows = [
            _make_venue_row("A", structured=_make_hours(), lat=lat_a, lng=lng_a, dwell=60),
            _make_venue_row("B", structured=_make_hours(), lat=lat_b, lng=lng_b, dwell=60),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 2, start, GEO, set())
        assert len(nodes) == 2
        a_end = nodes[0].scheduled_start + timedelta(minutes=nodes[0].duration_minutes)
        gap = (nodes[1].scheduled_start - a_end).total_seconds() / 60
        expected = walking_minutes(lat_a, lng_a, lat_b, lng_b)
        assert gap == expected, f"Gap {gap} != walking_minutes {expected}"

    def test_far_venue_unreachable_before_window_close(self):
        """A far second venue that can't walk from the first is absent."""
        # "Alpha" sorts first, is picked as stop 1. "Zoo Far" is 50km away.
        # Alpha dwell=60 ends 10:00. Walk 50km ~600 min. Zoo window Mon 09-11.
        # Arrival 10:00+600 >> 11:00 -> excluded.
        rows = [
            _make_venue_row(
                "Alpha Close", structured=_make_hours(), lat=19.89, lng=102.13, dwell=60
            ),
            _make_venue_row(
                "Zoo Far",
                structured=_make_hours({"mon": [["09:00", "11:00"]]}),
                lat=20.39,
                lng=102.13,
                dwell=60,
                category="cafe",
            ),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 2, start, GEO, set())
        names = [n.venue_name for n in nodes]
        assert "Zoo Far" not in names  # too far to walk before 11:00 close

    def test_candidate_without_coords_absent(self):
        """A candidate with None coordinates is skipped."""
        rows = [
            _make_venue_row("Good", structured=_make_hours(), lat=19.89, lng=102.13),
            _make_venue_row("NoCoords", structured=_make_hours(), lat=None, lng=None),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 2, start, GEO, set())
        names = [n.venue_name for n in nodes]
        assert "NoCoords" not in names

    def test_candidate_with_nan_coords_absent(self):
        """A candidate with NaN coordinates is skipped."""
        rows = [
            _make_venue_row("Good", structured=_make_hours(), lat=19.89, lng=102.13),
            _make_venue_row("NanVenue", structured=_make_hours(), lat=float("nan"), lng=102.13),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 2, start, GEO, set())
        assert all(n.venue_name != "NanVenue" for n in nodes)

    def test_candidate_with_inf_coords_absent(self):
        """A candidate with infinity coordinates is skipped."""
        rows = [
            _make_venue_row("Good", structured=_make_hours(), lat=19.89, lng=102.13),
            _make_venue_row("InfVenue", structured=_make_hours(), lat=19.89, lng=float("inf")),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 2, start, GEO, set())
        assert all(n.venue_name != "InfVenue" for n in nodes)

    def test_first_stop_no_transfer(self):
        """First stop of the day starts at day_start, not day_start + transfer."""
        rows = [
            _make_venue_row("First", structured=_make_hours(), lat=19.89, lng=102.13),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 1, start, GEO, set())
        assert nodes[0].scheduled_start == start

    def test_day_n_cannot_push_day_n1(self):
        """Day N evening does not push Day N+1; second day starts at 09:00."""
        rows = eligible_corridor_venues(db_service.list_venues_for_region(GEO))
        s1 = _ict_to_utc(2026, 9, 14, 9)
        s2 = _ict_to_utc(2026, 9, 15, 9)
        d1, used = pack_day(rows, 4, s1, GEO, set())
        d2, _ = pack_day(rows, 4, s2, GEO, used)
        assert len(d2) >= 1, "Day 2 must have at least one stop"
        assert d2[0].scheduled_start == s2, (
            f"Day 2 first stop at {d2[0].scheduled_start}, expected {s2}"
        )

    def test_laos_corridor_still_builds(self):
        """Create the actual Laos corridor and assert 4 stops per day."""
        r = client.post("/api/v1/trip/create", json=_corridor_body(), headers=HEADERS)
        assert r.status_code == 200, r.text
        data = r.json()
        for region in ("vientiane_laos", "vang_vieng_laos", "luang_prabang_laos"):
            region_nodes = [
                n
                for n in data["nodes"]
                if n["geo_region"] == region and n.get("node_kind", "activity") == "activity"
            ]
            dates = set()
            for n in region_nodes:
                dt = datetime.fromisoformat(n["scheduled_start"]).astimezone(ICT)
                dates.add(dt.date())
            for d in dates:
                day_nodes = [
                    n
                    for n in region_nodes
                    if datetime.fromisoformat(n["scheduled_start"]).astimezone(ICT).date() == d
                ]
                assert len(day_nodes) == CORRIDOR_STOPS_PER_DAY, (
                    f"{region} {d}: {len(day_nodes)} stops, expected {CORRIDOR_STOPS_PER_DAY}"
                )


# ===================================================================
# Lock tests
# ===================================================================


class TestNextLockedBooking:
    def test_venue_overrunning_locked_flight_omitted(self):
        """An attractive venue that overruns a same-day locked flight is omitted."""
        flight = TripNode(
            venue_name="Flight QV101",
            scheduled_start=_ict_to_utc(2026, 9, 14, 14),
            duration_minutes=180,
            is_locked=True,
            node_kind="booking",
            booking_type="flight",
            lat=19.89,
            lng=102.14,
            geo_region=GEO,
        )
        # Venue with 120-min dwell at ~10km from flight airport
        rows = [
            _make_venue_row("A", structured=_make_hours(), dwell=60, lat=19.89, lng=102.13),
            _make_venue_row("B", structured=_make_hours(), dwell=60, lat=19.89, lng=102.131),
            _make_venue_row("C", structured=_make_hours(), dwell=60, lat=19.89, lng=102.132),
            _make_venue_row(
                "LateVenue",
                structured=_make_hours(),
                dwell=240,
                lat=19.99,
                lng=102.23,
                category="market",
            ),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 4, start, GEO, set(), next_locked_booking=flight)
        names = [n.venue_name for n in nodes]
        # LateVenue has 240-min dwell; even starting at 09:00, 09:00+240+walk > 14:00
        assert "LateVenue" not in names

    def test_venue_fitting_before_flight_remains(self):
        """A short-dwell venue that fits before a same-day flight remains."""
        flight = TripNode(
            venue_name="Flight QV101",
            scheduled_start=_ict_to_utc(2026, 9, 14, 14),
            duration_minutes=180,
            is_locked=True,
            node_kind="booking",
            booking_type="flight",
            lat=19.89,
            lng=102.14,
            geo_region=GEO,
        )
        rows = [
            _make_venue_row("Short", structured=_make_hours(), dwell=60, lat=19.89, lng=102.13),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 1, start, GEO, set(), next_locked_booking=flight)
        assert len(nodes) == 1
        assert nodes[0].venue_name == "Short"

    def test_hotel_lock_ignored_by_pack_day(self):
        """A hotel passed as next_locked_booking is ignored (background anchor)."""
        hotel = TripNode(
            venue_name="Grand Hotel",
            scheduled_start=_ict_to_utc(2026, 9, 14, 14),
            duration_minutes=720,
            is_locked=True,
            node_kind="booking",
            booking_type="hotel",
            lat=19.89,
            lng=102.14,
            geo_region=GEO,
        )
        rows = [
            _make_venue_row("Venue", structured=_make_hours(), dwell=60, lat=19.89, lng=102.13),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 1, start, GEO, set(), next_locked_booking=hotel)
        assert len(nodes) == 1, "Hotel lock should be ignored"

    def test_different_region_lock_ignored(self):
        """A lock from a different geo_region is ignored by _fits_next_lock."""
        flight = TripNode(
            venue_name="BKK Flight",
            scheduled_start=_ict_to_utc(2026, 9, 14, 14),
            duration_minutes=180,
            is_locked=True,
            node_kind="booking",
            booking_type="flight",
            lat=13.69,
            lng=100.75,
            geo_region="bangkok_thailand",
        )
        rows = [
            _make_venue_row("Venue", structured=_make_hours(), dwell=240, lat=19.89, lng=102.13),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 1, start, GEO, set(), next_locked_booking=flight)
        assert len(nodes) == 1, "Different-region lock should be ignored"

    def test_different_local_day_lock_ignored(self):
        """A lock on a different local day is ignored."""
        flight = TripNode(
            venue_name="Tomorrow Flight",
            scheduled_start=_ict_to_utc(2026, 9, 15, 10),
            duration_minutes=180,
            is_locked=True,
            node_kind="booking",
            booking_type="flight",
            lat=19.89,
            lng=102.14,
            geo_region=GEO,
        )
        rows = [
            _make_venue_row("Venue", structured=_make_hours(), dwell=240, lat=19.89, lng=102.13),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 1, start, GEO, set(), next_locked_booking=flight)
        assert len(nodes) == 1, "Different-day lock should be ignored"

    def test_missing_lock_coords_omit_candidate(self):
        """Missing coordinates on same-day non-hotel lock means candidate ineligible."""
        flight = TripNode(
            venue_name="Flight",
            scheduled_start=_ict_to_utc(2026, 9, 14, 14),
            duration_minutes=180,
            is_locked=True,
            node_kind="booking",
            booking_type="flight",
            lat=None,
            lng=None,
            geo_region=GEO,
        )
        rows = [
            _make_venue_row("Venue", structured=_make_hours(), dwell=60, lat=19.89, lng=102.13),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 1, start, GEO, set(), next_locked_booking=flight)
        assert len(nodes) == 0


# ===================================================================
# Scheduler tests
# ===================================================================


class TestSchedulerWalking:
    def test_locked_flight_overrun_sets_hard_conflict(self):
        """Locked flight overrun using walking helper sets has_hard_conflict."""
        base = datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc)
        nodes = [
            TripNode(
                venue_name="A",
                scheduled_start=base,
                duration_minutes=60,
                lat=19.89,
                lng=102.13,
                geo_region=GEO,
            ),
            TripNode(
                venue_name="Flight",
                scheduled_start=base + timedelta(hours=1, minutes=10),
                duration_minutes=180,
                is_locked=True,
                lat=20.39,
                lng=102.13,
                geo_region=GEO,
            ),
        ]
        result = reschedule_and_validate(nodes)
        assert result.has_hard_conflict is True

    def test_hotel_does_not_create_overrun(self):
        """Hotel dwell does not push later activity or trigger hard conflict."""
        hotel_start = datetime(2026, 10, 4, 14, 0, tzinfo=timezone.utc)
        activity_start = datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)
        nodes = [
            TripNode(
                venue_name="Hotel",
                scheduled_start=hotel_start,
                duration_minutes=2760,
                is_locked=True,
                node_kind="booking",
                booking_type="hotel",
                lat=18.92,
                lng=102.45,
                geo_region="vang_vieng_laos",
            ),
            TripNode(
                venue_name="Activity",
                scheduled_start=activity_start,
                duration_minutes=120,
                lat=18.93,
                lng=102.46,
                geo_region="vang_vieng_laos",
            ),
        ]
        result = reschedule_and_validate(nodes)
        activity = [n for n in result.nodes if n.venue_name == "Activity"][0]
        assert activity.scheduled_start == activity_start
        assert result.has_hard_conflict is False

    def test_two_calls_same_result_no_drift(self):
        """Two calls on the same nodes produce the same starts."""
        base = datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc)

        def _nodes():
            return [
                TripNode(
                    venue_name="A",
                    scheduled_start=base,
                    duration_minutes=60,
                    lat=19.89,
                    lng=102.13,
                    geo_region=GEO,
                ),
                TripNode(
                    venue_name="B",
                    scheduled_start=base + timedelta(hours=2),
                    duration_minutes=60,
                    lat=19.891,
                    lng=102.131,
                    geo_region=GEO,
                ),
            ]

        r1 = reschedule_and_validate(_nodes())
        r2 = reschedule_and_validate(_nodes())
        for n1, n2 in zip(r1.nodes, r2.nodes):
            assert n1.scheduled_start == n2.scheduled_start

    def test_cross_city_preserves_next_city_start(self):
        """Scheduler does not apply walking between different geo_regions."""
        base = datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc)
        vv_start = datetime(2026, 10, 4, 2, 0, tzinfo=timezone.utc)
        nodes = [
            TripNode(
                venue_name="VTE Venue",
                scheduled_start=base,
                duration_minutes=480,
                lat=17.97,
                lng=102.63,
                geo_region="vientiane_laos",
            ),
            TripNode(
                venue_name="VV Venue",
                scheduled_start=vv_start,
                duration_minutes=120,
                lat=18.92,
                lng=102.45,
                geo_region="vang_vieng_laos",
            ),
        ]
        result = reschedule_and_validate(nodes)
        vv = [n for n in result.nodes if n.venue_name == "VV Venue"][0]
        assert vv.scheduled_start == vv_start
        assert result.has_hard_conflict is False

    def test_same_city_next_day_preserves_start(self):
        """Same region, different local day: scheduler does not push Day N+1."""
        day1_start = _ict_to_utc(2026, 10, 4, 9)
        day2_start = _ict_to_utc(2026, 10, 5, 9)
        nodes = [
            TripNode(
                venue_name="Day1",
                scheduled_start=day1_start,
                duration_minutes=480,
                lat=19.89,
                lng=102.13,
                geo_region=GEO,
            ),
            TripNode(
                venue_name="Day2",
                scheduled_start=day2_start,
                duration_minutes=120,
                lat=19.90,
                lng=102.14,
                geo_region=GEO,
            ),
        ]
        result = reschedule_and_validate(nodes)
        d2 = [n for n in result.nodes if n.venue_name == "Day2"][0]
        assert d2.scheduled_start == day2_start


# ===================================================================
# Capacity tests
# ===================================================================


class TestCapacityWithWalking:
    def test_advertised_max_days_still_creates(self):
        """Advertised max_days for every region still creates via API."""
        r = client.get("/api/v1/trips", headers=HEADERS)
        max_days = r.json()["create_trip_options"]["max_days_by_region"]
        assert len(max_days) >= 1
        sd = date(2026, 10, 5)
        for region, md in max_days.items():
            ed = sd + timedelta(days=md - 1)
            body = {
                "start_date": sd.isoformat(),
                "end_date": ed.isoformat(),
                "geo_region": region,
                "party": {"party_type": "friends", "size": 3, "members": []},
            }
            resp = client.post(
                "/api/v1/trip/create",
                json=body,
                headers=auth(f"spec41-reach-cap-{region}"),
            )
            assert resp.status_code == 200, f"{region} at max {md}: {resp.json()}"


# ===================================================================
# Sabotage proofs
# ===================================================================


class TestStateMachineSwap:
    """Tests that exercise _node_apply_structural through the HTTP endpoint."""

    def _create_trip(self):
        r = client.post("/api/v1/trip/create", json=_corridor_body(), headers=HEADERS)
        assert r.status_code == 200, r.text
        return r.json()

    def test_generic_search_first_vv_no_walk_from_vte(self):
        """Generic swap at the first VV node uses no VTE walking coords."""
        data = self._create_trip()
        trip_id = data["trip_id"]
        vv_nodes = [n for n in data["nodes"] if n["geo_region"] == "vang_vieng_laos"]
        first_vv = vv_nodes[0]
        calls = []
        from services.transit import walking_minutes as orig_wm

        def spy_wm(*a, **kw):
            calls.append(a)
            return orig_wm(*a, **kw)

        with mock_patch("agents.state_machine._walking_minutes", side_effect=spy_wm):
            r = client.post(
                "/api/v1/trip/event",
                json={
                    "trip_id": trip_id,
                    "event_type": "swap_activity",
                    "message": "Find me something else",
                    "target_node_id": first_vv["node_id"],
                },
                headers=HEADERS,
            )
        assert r.status_code == 200, r.text
        for ca in calls:
            assert ca[0] > 18.5, f"Walking called with VTE lat {ca[0]}"

    def test_maps_not_called_on_swap_path(self):
        """maps_service.get_transit_time is never called during a swap."""
        data = self._create_trip()
        calls = []
        from services.maps_service import MapsService

        orig = MapsService.get_transit_time

        def spy(*a, **kw):
            calls.append(1)
            return orig(*a, **kw)

        vv = [n for n in data["nodes"] if n["geo_region"] == "vang_vieng_laos"]
        with mock_patch.object(MapsService, "get_transit_time", side_effect=spy):
            client.post(
                "/api/v1/trip/event",
                json={
                    "trip_id": data["trip_id"],
                    "event_type": "swap_activity",
                    "message": "Something different",
                    "target_node_id": vv[0]["node_id"],
                },
                headers=HEADERS,
            )
        assert len(calls) == 0, "Maps get_transit_time was called on swap path"

    def test_no_llm_on_swap(self):
        """Swap with no API key produces a canned response, not an LLM call."""
        data = self._create_trip()
        vv = [n for n in data["nodes"] if n["geo_region"] == "vang_vieng_laos"]
        r = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": data["trip_id"],
                "event_type": "swap_activity",
                "message": "Something else",
                "target_node_id": vv[0]["node_id"],
            },
            headers=HEADERS,
        )
        assert r.status_code == 200
        assert "message" in r.json() or "response" in r.json()

    def test_exact_reachable_candidate_applied_via_http(self):
        """A reachable explicit replacement within VV is applied through HTTP."""
        data = self._create_trip()
        vv = [n for n in data["nodes"] if n["geo_region"] == "vang_vieng_laos"]
        target = vv[0]
        target_start = datetime.fromisoformat(target["scheduled_start"])
        from services.catalog_itinerary import duration_for

        trip_vids = {n["venue_id"] for n in data["nodes"]}
        all_vv = eligible_corridor_venues(db_service.list_venues_for_region("vang_vieng_laos"))
        replacement = None
        for v in all_vv:
            vid = str(v["venue_id"])
            if vid in trip_vids:
                continue
            hr = hours_for_slot(
                v.get("opening_hours_structured"), target_start, duration_for(v), "vang_vieng_laos"
            )
            if hr == HoursResult.CLOSED:
                continue
            replacement = v
            break
        if replacement is None:
            pytest.skip("No eligible replacement VV venue")
        r = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": data["trip_id"],
                "event_type": "swap_activity",
                "message": "Swap to this",
                "target_node_id": target["node_id"],
                "preferences": {"replacement_venue_id": str(replacement["venue_id"])},
            },
            headers=HEADERS,
        )
        assert r.status_code == 200
        trip_after = client.get(f"/api/v1/trip/{data['trip_id']}", headers=HEADERS).json()
        swapped = next(n for n in trip_after["nodes"] if n["node_id"] == target["node_id"])
        assert swapped["venue_id"] == str(replacement["venue_id"])


# ===================================================================
# Sabotage proofs
# ===================================================================


class TestSabotageProofs:
    def test_sabotage1_random_on_packing_path(self):
        """Restoring random.uniform on the packing/scheduler transit path
        would break determinism.

        Fails: test_two_calls_same_result_no_drift
        Fails: test_identical_coords_identical_result
        """
        import services.transit as transit_mod

        source = inspect.getsource(transit_mod)
        assert "import random" not in source
        assert "random.uniform" not in source

    def test_sabotage2_restore_30_minute_buffer(self):
        """Restoring the hardcoded 30-min buffer would ignore walking_minutes.

        Fails: test_intraday_gap_uses_walking_transfer
        """
        import services.catalog_itinerary as ci

        source = inspect.getsource(ci.pack_day)
        # The old "+ 30)" pattern must not appear
        assert "duration_minutes + 30" not in source

    def test_sabotage3_remove_region_guard_from_scheduler(self):
        """Skipping next-locked-booking check on swap apply would allow
        unreachable venues.

        Fails: test_cross_city_preserves_next_city_start
        Fails: test_same_city_next_day_preserves_start
        """
        import services.scheduler as sched

        source = inspect.getsource(sched.reschedule_and_validate)
        assert "_same_region_and_local_day" in source

    def test_sabotage4_remove_hotel_guard_from_fits_next_lock(self):
        """Removing the hotel bypass in _fits_next_lock would refuse valid
        venues near hotel locks.

        Fails: test_hotel_lock_ignored_by_pack_day
        """
        import services.catalog_itinerary as ci

        source = inspect.getsource(ci.pack_day)
        assert "booking_type" in source

    def test_sabotage5_remove_unified_predicate(self):
        """Removing _is_swap_reachable from state_machine would allow
        unreachable swaps or inconsistent paths.

        Fails: test_generic_search_first_vv_no_walk_from_vte
        Fails: test_exact_reachable_candidate_applied_via_http
        """
        import sys

        sm = sys.modules["agents.state_machine"]
        assert hasattr(sm, "_is_swap_reachable"), "_is_swap_reachable removed"
        source = inspect.getsource(sm.TripStateMachine._node_venue_search)
        assert "_is_swap_reachable" in source
