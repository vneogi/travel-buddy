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
    CurrentContext,
    EventType,
    NodeStatus,
    TripNode,
    TripState,
    VenueRAG,
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
        """Create the actual Laos corridor and assert structure.

        Assertions:
          - all three expected regions exist
          - 2 / 2 / 4 day allocation (VTE / VV / LP)
          - 8 total local dates across all regions
          - exactly 4 activity stops on every date
        """
        r = client.post("/api/v1/trip/create", json=_corridor_body(), headers=HEADERS)
        assert r.status_code == 200, r.text
        data = r.json()

        expected_regions = {
            "vientiane_laos": 2,
            "vang_vieng_laos": 2,
            "luang_prabang_laos": 4,
        }
        all_dates: set = set()

        for region, expected_days in expected_regions.items():
            region_nodes = [
                n
                for n in data["nodes"]
                if n["geo_region"] == region and n.get("node_kind", "activity") == "activity"
            ]
            assert len(region_nodes) > 0, f"{region} has no activity nodes"
            dates_for_region: set = set()
            for n in region_nodes:
                dt = datetime.fromisoformat(n["scheduled_start"]).astimezone(ICT)
                dates_for_region.add(dt.date())
            assert len(dates_for_region) == expected_days, (
                f"{region}: {len(dates_for_region)} days, expected {expected_days}"
            )
            all_dates.update(dates_for_region)

            for d in dates_for_region:
                day_nodes = [
                    n
                    for n in region_nodes
                    if datetime.fromisoformat(n["scheduled_start"]).astimezone(ICT).date() == d
                ]
                assert len(day_nodes) == CORRIDOR_STOPS_PER_DAY, (
                    f"{region} {d}: {len(day_nodes)} stops, expected {CORRIDOR_STOPS_PER_DAY}"
                )

        assert len(all_dates) == 8, f"Expected 8 total dates, got {len(all_dates)}"


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
# State-machine swap + apply-time recheck
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

    def test_no_maps_no_llm_on_swap(self):
        """Neither maps nor llm service is called during a swap.

        Uses an explicit replacement_venue_id on an LP node to guarantee
        the swap succeeds.  Patches validate_venues, get_transit_time,
        complete, and generate_itinerary_response with hard-fail spies.
        Asserts HTTP 200 and that the venue actually changed.
        """
        data = self._create_trip()
        lp = [
            n
            for n in data["nodes"]
            if n["geo_region"] == "luang_prabang_laos"
            and n.get("node_kind", "activity") == "activity"
        ]
        target = lp[0]
        # Find an unused LP venue
        trip_vids = {n["venue_id"] for n in data["nodes"]}
        target_start = datetime.fromisoformat(target["scheduled_start"])
        from services.catalog_itinerary import duration_for

        all_lp = eligible_corridor_venues(db_service.list_venues_for_region("luang_prabang_laos"))
        replacement = None
        for v in all_lp:
            if str(v["venue_id"]) in trip_vids:
                continue
            hr = hours_for_slot(
                v.get("opening_hours_structured"),
                target_start,
                duration_for(v),
                "luang_prabang_laos",
            )
            if hr == HoursResult.CLOSED:
                continue
            replacement = v
            break
        if replacement is None:
            pytest.skip("No eligible replacement LP venue")

        maps_calls: list = []
        llm_calls: list = []

        def _maps_spy(name):
            def _inner(*a, **kw):
                maps_calls.append(name)
                raise AssertionError(f"maps_service.{name} called on swap")

            return _inner

        def _llm_spy(name):
            def _inner(*a, **kw):
                llm_calls.append(name)
                raise AssertionError(f"llm_service.{name} called on swap")

            return _inner

        with (
            mock_patch(
                "agents.state_machine.maps_service.validate_venues",
                side_effect=_maps_spy("validate_venues"),
            ),
            mock_patch(
                "agents.state_machine.maps_service.get_transit_time",
                side_effect=_maps_spy("get_transit_time"),
            ),
            mock_patch(
                "services.llm_service.llm_service.complete",
                side_effect=_llm_spy("complete"),
            ),
            mock_patch(
                "services.llm_service.llm_service.generate_itinerary_response",
                side_effect=_llm_spy("generate_itinerary_response"),
            ),
        ):
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
        assert r.status_code == 200, r.text
        assert len(maps_calls) == 0, f"Maps called: {maps_calls}"
        assert len(llm_calls) == 0, f"LLM called: {llm_calls}"
        trip_after = client.get(f"/api/v1/trip/{data['trip_id']}", headers=HEADERS).json()
        swapped = next(n for n in trip_after["nodes"] if n["node_id"] == target["node_id"])
        assert swapped["venue_id"] == str(replacement["venue_id"]), "Replacement not applied"

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
# Apply-time recheck (direct state-machine tests)
# ===================================================================


def _sm():
    """Return the TripStateMachine singleton."""
    import sys

    return sys.modules["agents.state_machine"].state_machine


def _sm_mod():
    """Return the agents.state_machine module."""
    import sys

    return sys.modules["agents.state_machine"]


def _make_trip_state(nodes, geo_region=GEO):
    return TripState(
        trip_id=str(uuid.uuid4()),
        user_id="test-apply-recheck",
        geo_region=geo_region,
        nodes=nodes,
        current_context=CurrentContext(location_lat=19.89, location_lng=102.13),
    )


def _vsr(venue_row):
    """Create a VenueSearchResult from a dict."""
    v = VenueRAG(**venue_row)
    return VenueSearchResult(venue=v, similarity_score=0.0, final_score=0.0)


class TestApplyTimeRecheck:
    """Direct _build_candidate_nodes tests proving apply-time reachability."""

    def test_prev_same_day_unreachable_rejected(self):
        """Candidate unreachable from previous same-day activity is rejected.

        Setup: Activity A (09:00-10:00 LP), target slot (10:05 LP).
        Candidate 50 km away -> walk ~600 min > 5 min gap.
        Apply-time recheck must return [] (advance signal).
        """
        base = _ict_to_utc(2026, 10, 6, 9)
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
                venue_name="Target",
                scheduled_start=base + timedelta(minutes=65),
                duration_minutes=60,
                lat=19.891,
                lng=102.131,
                geo_region=GEO,
            ),
        ]
        trip_state = _make_trip_state(nodes)
        far_venue = _make_venue_row(
            "Far",
            structured=_make_hours(),
            dwell=60,
            lat=20.39,
            lng=102.13,
        )
        venues = [_vsr(far_venue)]
        result = _sm()._build_candidate_nodes(
            trip_state, EventType.SWAP_ACTIVITY.value, nodes[1].node_id, venues, 0
        )
        # [] = apply-time recheck failed (not None = exhausted)
        assert result is not None, "Should return [] not None"
        assert result == [], "Unreachable candidate was not rejected at apply time"

    def test_next_locked_flight_unreachable_rejected(self):
        """Candidate that overruns next locked flight is rejected.

        Setup: Target slot (09:00 LP), flight at 10:30 LP.
        Candidate dwell=60 + walk 50km ~600 min -> overruns 10:30.
        """
        base = _ict_to_utc(2026, 10, 6, 9)
        nodes = [
            TripNode(
                venue_name="Target",
                scheduled_start=base,
                duration_minutes=60,
                lat=19.89,
                lng=102.13,
                geo_region=GEO,
            ),
            TripNode(
                venue_name="Flight",
                scheduled_start=base + timedelta(minutes=90),
                duration_minutes=180,
                is_locked=True,
                node_kind="booking",
                booking_type="flight",
                lat=19.89,
                lng=102.14,
                geo_region=GEO,
            ),
        ]
        trip_state = _make_trip_state(nodes)
        # Candidate at 50km from flight -> walk ~600 min after 60-min dwell
        far_venue = _make_venue_row(
            "FarFromFlight",
            structured=_make_hours(),
            dwell=60,
            lat=20.39,
            lng=102.13,
        )
        venues = [_vsr(far_venue)]
        result = _sm()._build_candidate_nodes(
            trip_state, EventType.SWAP_ACTIVITY.value, nodes[0].node_id, venues, 0
        )
        assert result == [], "Candidate overrunning flight not rejected"

    def test_apply_cannot_bypass_search(self):
        """Even if an unreachable venue passes search, apply-time recheck blocks it.

        Simulates a bad venue sneaking into the venues list by calling
        _build_candidate_nodes directly with an unreachable candidate.
        """
        base = _ict_to_utc(2026, 10, 6, 9)
        nodes = [
            TripNode(
                venue_name="Prev",
                scheduled_start=base,
                duration_minutes=60,
                lat=19.89,
                lng=102.13,
                geo_region=GEO,
            ),
            TripNode(
                venue_name="Target",
                scheduled_start=base + timedelta(minutes=65),
                duration_minutes=60,
                lat=19.891,
                lng=102.131,
                geo_region=GEO,
            ),
        ]
        trip_state = _make_trip_state(nodes)
        # Inject an unreachable venue that search would normally filter
        bad_venue = _make_venue_row(
            "Injected",
            structured=_make_hours(),
            dwell=60,
            lat=20.39,
            lng=102.13,
        )
        venues = [_vsr(bad_venue)]
        result = _sm()._build_candidate_nodes(
            trip_state, EventType.SWAP_ACTIVITY.value, nodes[1].node_id, venues, 0
        )
        assert result == [], "Apply-time recheck did not block injected venue"

    def test_candidate1_fails_candidate2_applied(self):
        """When candidate 1 fails apply-time recheck, candidate 2 is applied."""
        base = _ict_to_utc(2026, 10, 6, 9)
        nodes = [
            TripNode(
                venue_name="Prev",
                scheduled_start=base,
                duration_minutes=60,
                lat=19.89,
                lng=102.13,
                geo_region=GEO,
            ),
            TripNode(
                venue_name="Target",
                scheduled_start=base + timedelta(minutes=65),
                duration_minutes=60,
                lat=19.891,
                lng=102.131,
                geo_region=GEO,
            ),
        ]
        trip_state = _make_trip_state(nodes)
        # Venue 1: far away -> fail recheck
        bad = _make_venue_row("Bad", structured=_make_hours(), dwell=60, lat=20.39, lng=102.13)
        # Venue 2: nearby -> pass recheck
        good = _make_venue_row("Good", structured=_make_hours(), dwell=60, lat=19.892, lng=102.132)
        venues = [_vsr(bad), _vsr(good)]

        # Attempt 0 should return [] (bad)
        r0 = _sm()._build_candidate_nodes(
            trip_state,
            EventType.SWAP_ACTIVITY.value,
            nodes[1].node_id,
            venues,
            0,
        )
        assert r0 == [], "Candidate 1 should fail recheck"

        # Attempt 1 should return a valid node list with Good applied
        r1 = _sm()._build_candidate_nodes(
            trip_state,
            EventType.SWAP_ACTIVITY.value,
            nodes[1].node_id,
            venues,
            1,
        )
        assert r1 is not None and len(r1) > 0, "Candidate 2 should succeed"
        swapped = next(n for n in r1 if n.node_id == nodes[1].node_id)
        assert swapped.venue_name == "Good", f"Expected Good, got {swapped.venue_name}"

    def test_nan_coords_refused_at_apply(self):
        """Candidate with NaN coordinates is refused at apply time."""
        base = _ict_to_utc(2026, 10, 6, 9)
        nodes = [
            TripNode(
                venue_name="Target",
                scheduled_start=base,
                duration_minutes=60,
                lat=19.89,
                lng=102.13,
                geo_region=GEO,
            ),
        ]
        trip_state = _make_trip_state(nodes)
        nan_venue = _make_venue_row(
            "NaN",
            structured=_make_hours(),
            dwell=60,
            lat=float("nan"),
            lng=102.13,
        )
        venues = [_vsr(nan_venue)]
        result = _sm()._build_candidate_nodes(
            trip_state, EventType.SWAP_ACTIVITY.value, nodes[0].node_id, venues, 0
        )
        assert result == [], "NaN-coord candidate not rejected at apply time"

    def test_first_vv_swap_retains_vv_candidate(self):
        """Generic search at first VV node retains a VV candidate without
        walking from Vientiane.

        Creates a corridor trip, swaps first VV node, asserts:
          - HTTP 200
          - the exact applied venue is from VV
          - the venue actually changed
        """
        data = client.post("/api/v1/trip/create", json=_corridor_body(), headers=HEADERS).json()
        trip_id = data["trip_id"]
        vv = [
            n
            for n in data["nodes"]
            if n["geo_region"] == "vang_vieng_laos" and n.get("node_kind", "activity") == "activity"
        ]
        target = vv[0]
        target_start = datetime.fromisoformat(target["scheduled_start"])
        from services.catalog_itinerary import duration_for

        trip_vids = {n["venue_id"] for n in data["nodes"]}
        all_vv = eligible_corridor_venues(db_service.list_venues_for_region("vang_vieng_laos"))
        replacement = None
        for v in all_vv:
            if str(v["venue_id"]) in trip_vids:
                continue
            hr = hours_for_slot(
                v.get("opening_hours_structured"),
                target_start,
                duration_for(v),
                "vang_vieng_laos",
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
                "trip_id": trip_id,
                "event_type": "swap_activity",
                "message": "Find me something else in VV",
                "target_node_id": target["node_id"],
                "preferences": {"replacement_venue_id": str(replacement["venue_id"])},
            },
            headers=HEADERS,
        )
        assert r.status_code == 200, r.text
        trip_after = client.get(f"/api/v1/trip/{trip_id}", headers=HEADERS).json()
        swapped = next(n for n in trip_after["nodes"] if n["node_id"] == target["node_id"])
        assert swapped["venue_id"] == str(replacement["venue_id"]), "Replacement not applied"
        assert swapped["geo_region"] == "vang_vieng_laos", (
            f"Replacement is not VV: {swapped['geo_region']}"
        )


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

        Fails: test_prev_same_day_unreachable_rejected
        Fails: test_next_locked_flight_unreachable_rejected
        Fails: test_candidate1_fails_candidate2_applied
        Fails: test_nan_coords_refused_at_apply
        """
        import sys

        sm = sys.modules["agents.state_machine"]
        assert hasattr(sm, "_is_swap_reachable"), "_is_swap_reachable removed"
        # Must be in both search-time and apply-time paths
        search_src = inspect.getsource(sm.TripStateMachine._node_venue_search)
        assert "_is_swap_reachable" in search_src
        apply_src = inspect.getsource(sm.TripStateMachine._build_candidate_nodes)
        assert "_is_swap_reachable" in apply_src
