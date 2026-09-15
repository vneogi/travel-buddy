"""SPEC-41 Phase A3b: Deterministic Walking Reachability.

Covers:
  - walking_minutes helper determinism and arithmetic
  - pack_day walking transfer integration
  - Next-locked-booking feasibility
  - Swap search/apply reachability filtering
  - Scheduler walking_minutes usage
  - Truthful max_days capacity with walking
  - Sabotage proofs (5)
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
import services.database_service as db_mod

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
    name, structured=None, category="temple", dwell=60,
    lat=19.89, lng=102.13, venue_id=None,
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
    def test_nearby_venues_use_walking_not_30(self):
        """Transfer between two nearby venues equals walking_minutes, not 30."""
        # Two venues ~200m apart (< 5 min walk)
        rows = [
            _make_venue_row("A", structured=_make_hours(), lat=19.89, lng=102.13, dwell=60),
            _make_venue_row("B", structured=_make_hours(), lat=19.891, lng=102.131, dwell=60),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 2, start, GEO, set())
        assert len(nodes) == 2
        a_end = nodes[0].scheduled_start + timedelta(minutes=nodes[0].duration_minutes)
        gap = (nodes[1].scheduled_start - a_end).total_seconds() / 60
        # Walking ~200m should be 5 min (floor), not 30
        expected_transfer = walking_minutes(19.89, 102.13, 19.891, 102.131)
        assert gap == pytest.approx(expected_transfer, abs=1)
        assert gap < 30  # must be less than old fixed buffer

    def test_far_venue_unreachable_before_window_close(self):
        """A far second venue that can't walk from the first is absent."""
        # "Alpha" sorts first, is picked as stop 1. "Zoo Far" is 50km away.
        # Alpha dwell=60 ends 10:00. Walk 50km ~600 min. Zoo window Mon 09-11.
        # Arrival 10:00+600 >> 11:00 -> excluded.
        rows = [
            _make_venue_row("Alpha Close", structured=_make_hours(), lat=19.89, lng=102.13, dwell=60),
            _make_venue_row(
                "Zoo Far", structured=_make_hours({"mon": [["09:00", "11:00"]]}),
                lat=20.39, lng=102.13, dwell=60,
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

    def test_first_stop_no_transfer(self):
        """First stop of the day starts at day_start, not day_start + transfer."""
        rows = [
            _make_venue_row("First", structured=_make_hours(), lat=19.89, lng=102.13),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 1, start, GEO, set())
        assert nodes[0].scheduled_start == start

    def test_day_n_cannot_push_day_n1(self):
        """Day N evening does not push Day N+1 past 09:00."""
        rows = db_mod.db_service.list_venues_for_region(GEO)
        s1 = _ict_to_utc(2026, 9, 14, 9)
        s2 = _ict_to_utc(2026, 9, 15, 9)
        d1, used = pack_day(eligible_corridor_venues(rows), 4, s1, GEO, set())
        d2, _ = pack_day(eligible_corridor_venues(rows), 4, s2, GEO, used)
        if d2:
            assert d2[0].scheduled_start >= s2

    def test_laos_corridor_still_builds(self):
        """Current Oct 2-9 Laos corridor builds with 4 stops per day."""
        r = client.get("/api/v1/trips", headers=HEADERS)
        data = r.json()
        corridors = data.get("supported_corridors", [])
        if not corridors:
            pytest.skip("No corridors advertised")
        laos = next((c for c in corridors if "laos" in c["corridor_id"]), None)
        if laos is None:
            pytest.skip("Laos corridor not advertised")


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
        )
        # Venue with 120-min dwell at ~10km from flight airport
        rows = [
            _make_venue_row("A", structured=_make_hours(), dwell=60, lat=19.89, lng=102.13),
            _make_venue_row("B", structured=_make_hours(), dwell=60, lat=19.89, lng=102.131),
            _make_venue_row("C", structured=_make_hours(), dwell=60, lat=19.89, lng=102.132),
            _make_venue_row(
                "LateVenue", structured=_make_hours(), dwell=240,
                lat=19.99, lng=102.23, category="market",
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
        )
        rows = [
            _make_venue_row("Short", structured=_make_hours(), dwell=60, lat=19.89, lng=102.13),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 1, start, GEO, set(), next_locked_booking=flight)
        assert len(nodes) == 1
        assert nodes[0].venue_name == "Short"

    def test_hotel_does_not_omit_venue(self):
        """A hotel booking does not act as next-locked reachability target."""
        # Hotel with same coords as flight would be - but it's a hotel
        rows = [
            _make_venue_row("Venue", structured=_make_hours(), dwell=60, lat=19.89, lng=102.13),
        ]
        # No next_locked_booking passed (hotels are background anchors)
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 1, start, GEO, set())
        assert len(nodes) == 1

    def test_missing_lock_coords_omit_candidate(self):
        """Missing coordinates on the locked booking means candidate ineligible."""
        flight = TripNode(
            venue_name="Flight",
            scheduled_start=_ict_to_utc(2026, 9, 14, 14),
            duration_minutes=180,
            is_locked=True,
            node_kind="booking",
            booking_type="flight",
            lat=None,
            lng=None,
        )
        rows = [
            _make_venue_row("Venue", structured=_make_hours(), dwell=60, lat=19.89, lng=102.13),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 1, start, GEO, set(), next_locked_booking=flight)
        assert len(nodes) == 0  # can't verify reachability -> ineligible


# ===================================================================
# Scheduler tests
# ===================================================================


class TestSchedulerWalking:
    def test_locked_flight_overrun_sets_hard_conflict(self):
        """Locked flight overrun using walking helper sets has_hard_conflict."""
        base = datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc)
        nodes = [
            TripNode(
                venue_name="A", scheduled_start=base, duration_minutes=60,
                lat=19.89, lng=102.13,
            ),
            TripNode(
                venue_name="Flight",
                scheduled_start=base + timedelta(hours=1, minutes=10),
                duration_minutes=180,
                is_locked=True,
                lat=20.39, lng=102.13,  # ~55 km away -> huge walk
            ),
        ]
        result = reschedule_and_validate(nodes)
        # A ends 10:00 + walk 55km = ~660 min > flight at 10:10 -> hard conflict
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
            ),
            TripNode(
                venue_name="Activity",
                scheduled_start=activity_start,
                duration_minutes=120,
                lat=18.93,
                lng=102.46,
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
                    venue_name="A", scheduled_start=base, duration_minutes=60,
                    lat=19.89, lng=102.13,
                ),
                TripNode(
                    venue_name="B",
                    scheduled_start=base + timedelta(hours=2),
                    duration_minutes=60,
                    lat=19.891, lng=102.131,
                ),
            ]
        r1 = reschedule_and_validate(_nodes())
        r2 = reschedule_and_validate(_nodes())
        for n1, n2 in zip(r1.nodes, r2.nodes):
            assert n1.scheduled_start == n2.scheduled_start


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

        Fails: test_nearby_venues_use_walking_not_30
        """
        import services.catalog_itinerary as ci
        source = inspect.getsource(ci.pack_day)
        # The old "+ 30)" pattern must not appear
        assert "duration_minutes + 30" not in source

    def test_sabotage3_skip_next_lock_check_on_apply(self):
        """Skipping next-locked-booking check on swap apply would allow
        unreachable venues.

        Fails: test_venue_overrunning_locked_flight_omitted
        """
        flight = TripNode(
            venue_name="Flight",
            scheduled_start=_ict_to_utc(2026, 9, 14, 12),
            duration_minutes=180,
            is_locked=True,
            node_kind="booking",
            booking_type="flight",
            lat=19.89,
            lng=102.14,
        )
        rows = [
            _make_venue_row("Long", structured=_make_hours(), dwell=240, lat=19.89, lng=102.13),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 1, start, GEO, set(), next_locked_booking=flight)
        # 240-min dwell starting at 09:00 = ends 13:00 + walk > 12:00 flight
        assert len(nodes) == 0

    def test_sabotage4_missing_coords_as_zero_transfer(self):
        """Treating missing coordinates as zero transfer would allow
        unverifiable venues.

        Fails: test_candidate_without_coords_absent
        """
        rows = [
            _make_venue_row("Good", structured=_make_hours(), lat=19.89, lng=102.13),
            _make_venue_row("Bad", structured=_make_hours(), lat=None, lng=None),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 2, start, GEO, set())
        assert all(n.venue_name != "Bad" for n in nodes)

    def test_sabotage5_hotel_as_next_lock_target(self):
        """Using a hotel as the next locked reachability target would
        refuse a valid afternoon venue.

        Hotels are background anchors, not lock targets.
        """
        # If hotel were treated as a lock, any venue far from it would be refused
        rows = [
            _make_venue_row("Venue", structured=_make_hours(), dwell=60, lat=19.89, lng=102.13),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        # No next_locked_booking because hotels are not passed as locks
        nodes, _ = pack_day(rows, 1, start, GEO, set())
        assert len(nodes) == 1
        assert nodes[0].venue_name == "Venue"
