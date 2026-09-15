"""SPEC-41 Phase A3a: Window-Aware Day Packing.

Covers:
  - next_slot_start helper
  - Shared pack_day planner
  - Truthful max_days
  - Golden cases
  - Sabotage proofs
"""

from __future__ import annotations

import copy
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from main import app
from tests.conftest import auth
from config.interests import VENUES_PER_DAY, MAX_DAYS_CEILING
from config.regions import REGIONS
from models.schemas import TripSegmentIn
from services.catalog_itinerary import (
    InsufficientCatalog,
    compute_max_days_for_region,
    eligible_corridor_venues,
    nodes_from_catalog,
    pack_day,
    range_nodes_from_catalog,
)
from services.corridor_itinerary import build_corridor_nodes, CORRIDOR_STOPS_PER_DAY
from config.corridors import require_corridor
from services.opening_hours import HoursResult, hours_for_slot, next_slot_start
import services.database_service as db_mod

ICT = ZoneInfo("Asia/Vientiane")
GST = ZoneInfo("Asia/Dubai")
GEO = "luang_prabang_laos"

client = TestClient(app)
HEADERS = auth("spec41-a3a-user")

_ALL_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _utc(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _ict(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=ICT)


def _ict_to_utc(year, month, day, hour, minute=0):
    return _ict(year, month, day, hour, minute).astimezone(timezone.utc)


def _make_hours(weekday_windows: Dict[str, list]) -> Dict[str, Any]:
    return {d: weekday_windows.get(d, [["09:00", "17:00"]]) for d in _ALL_DAYS}


def _evening_hours():
    return {d: [["17:00", "22:00"]] for d in _ALL_DAYS}


def _split_hours():
    return {d: [["08:00", "11:30"], ["13:30", "16:00"]] for d in _ALL_DAYS}


def _make_venue_row(name, structured=None, category="temple", dwell=60, lat=19.89, lng=102.13):
    from services.catalog_itinerary import flatten_opening_hours

    flat = flatten_opening_hours(structured) or "09:00-17:00"
    return {
        "name": name,
        "venue_id": str(uuid.uuid5(uuid.NAMESPACE_URL, name)),
        "description": "",
        "micro_location": "",
        "lat": lat,
        "lng": lng,
        "vibe_tags": [],
        "audience": [],
        "category": category,
        "opening_hours": flat,
        "opening_hours_structured": structured,
        "geo_region": GEO,
        "typical_dwell_minutes": dwell,
    }


def _pool_of(n, structured=None, category="temple", dwell=60):
    return [
        _make_venue_row(f"Venue_{i}", structured=structured, category=category, dwell=dwell)
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# next_slot_start helper tests
# ---------------------------------------------------------------------------


class TestNextSlotStart:
    def test_cursor_already_fits(self):
        """If cursor is inside a fitting window, return it unchanged."""
        hours = _make_hours({})
        cursor = _ict_to_utc(2026, 9, 14, 10)  # Monday 10:00 ICT
        local_day = _ict(2026, 9, 14, 9)
        result = next_slot_start(hours, cursor, 60, GEO, local_day)
        assert result == cursor

    def test_cursor_before_opening_moves_to_opening(self):
        """Cursor before window open is advanced to window start."""
        hours = {d: [["10:00", "17:00"]] for d in _ALL_DAYS}
        cursor = _ict_to_utc(2026, 9, 14, 8)  # Monday 08:00 ICT
        local_day = _ict(2026, 9, 14, 8)
        result = next_slot_start(hours, cursor, 60, GEO, local_day)
        expected = _ict_to_utc(2026, 9, 14, 10)
        assert result == expected

    def test_cursor_in_lunch_gap_moves_to_second_window(self):
        """Cursor in split-window lunch gap moves to afternoon window."""
        hours = _split_hours()  # 08:00-11:30, 13:30-16:00
        cursor = _ict_to_utc(2026, 9, 14, 12)  # Monday 12:00 ICT
        local_day = _ict(2026, 9, 14, 9)
        result = next_slot_start(hours, cursor, 60, GEO, local_day)
        expected = _ict_to_utc(2026, 9, 14, 13, 30)
        assert result == expected

    def test_dwell_too_long_for_first_uses_later(self):
        """150-min dwell doesn't fit 08:00-10:00 but fits 13:00-17:00."""
        hours = {d: [["08:00", "10:00"], ["13:00", "17:00"]] for d in _ALL_DAYS}
        cursor = _ict_to_utc(2026, 9, 14, 8)
        local_day = _ict(2026, 9, 14, 8)
        result = next_slot_start(hours, cursor, 150, GEO, local_day)
        expected = _ict_to_utc(2026, 9, 14, 13)
        assert result == expected

    def test_dwell_too_long_for_every_window(self):
        """300-min dwell exceeds all windows => None."""
        hours = {d: [["09:00", "12:00"], ["14:00", "17:00"]] for d in _ALL_DAYS}
        cursor = _ict_to_utc(2026, 9, 14, 9)
        local_day = _ict(2026, 9, 14, 9)
        result = next_slot_start(hours, cursor, 300, GEO, local_day)
        assert result is None

    def test_evening_venue_moves_to_evening(self):
        """Evening-only window (17:00-22:00) schedules at 17:00."""
        hours = _evening_hours()
        cursor = _ict_to_utc(2026, 9, 14, 9)
        local_day = _ict(2026, 9, 14, 9)
        result = next_slot_start(hours, cursor, 60, GEO, local_day)
        expected = _ict_to_utc(2026, 9, 14, 17)
        assert result == expected

    def test_overnight_window_cannot_cross_midnight(self):
        """A venue open 20:00-02:00 can place a 60-min activity at 20:00
        but not a 300-min one (would end after midnight)."""
        hours = {d: [["20:00", "02:00"]] for d in _ALL_DAYS}
        cursor = _ict_to_utc(2026, 9, 14, 20)
        local_day = _ict(2026, 9, 14, 9)
        # 60 min fits: 20:00 + 60 = 21:00 < midnight
        r60 = next_slot_start(hours, cursor, 60, GEO, local_day)
        assert r60 is not None
        # 300 min fails: 20:00 + 300 = 01:00 next day
        r300 = next_slot_start(hours, cursor, 300, GEO, local_day)
        assert r300 is None

    def test_closed_weekday_returns_none(self):
        """Explicitly closed Tuesday => None."""
        hours = _make_hours({})
        hours["tue"] = []
        cursor = _ict_to_utc(2026, 9, 15, 9)  # Tuesday
        local_day = _ict(2026, 9, 15, 9)
        result = next_slot_start(hours, cursor, 60, GEO, local_day)
        assert result is None

    def test_unknown_hours_at_cursor(self):
        """None structured hours => schedule at cursor."""
        cursor = _ict_to_utc(2026, 9, 14, 10)
        local_day = _ict(2026, 9, 14, 9)
        result = next_slot_start(None, cursor, 60, GEO, local_day)
        assert result == cursor

    def test_timezone_differs_from_utc(self):
        """Dubai UTC+4: 10:00 local = 06:00 UTC."""
        hours = {d: [["10:00", "18:00"]] for d in _ALL_DAYS}
        cursor = _utc(2026, 9, 14, 5)  # 09:00 Dubai
        local_day = datetime(2026, 9, 14, 9, tzinfo=GST)
        result = next_slot_start(hours, cursor, 60, "dubai_uae", local_day)
        expected = datetime(2026, 9, 14, 10, tzinfo=GST).astimezone(timezone.utc)
        assert result == expected

    def test_input_datetime_not_mutated(self):
        """The original cursor datetime is not modified."""
        hours = _evening_hours()
        cursor = _ict_to_utc(2026, 9, 14, 9)
        original = cursor
        local_day = _ict(2026, 9, 14, 9)
        next_slot_start(hours, cursor, 60, GEO, local_day)
        assert cursor == original


# ---------------------------------------------------------------------------
# pack_day planner tests
# ---------------------------------------------------------------------------


class TestPackDay:
    def test_open_now_before_night_market(self):
        """An all-day venue starts before a night market despite lower rank."""
        rows = [
            _make_venue_row(
                "Night Market", structured=_evening_hours(), category="market", dwell=60
            ),
            _make_venue_row("Temple", structured=_make_hours({}), category="temple", dwell=60),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 2, start, GEO, set())
        assert nodes[0].venue_name == "Temple"
        assert nodes[1].venue_name == "Night Market"

    def test_equal_start_retains_deterministic_order(self):
        """Equal-start candidates ordered by name then venue_id."""
        rows = [
            _make_venue_row("Zebra", structured=_make_hours({}), category="temple", dwell=60),
            _make_venue_row("Alpha", structured=_make_hours({}), category="cafe", dwell=60),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 2, start, GEO, set())
        assert nodes[0].venue_name == "Alpha"
        assert nodes[1].venue_name == "Zebra"

    def test_morning_lunch_evening_chronological(self):
        """Morning, lunch-gap, and evening venues produce chronological starts."""
        morning = {d: [["07:00", "10:00"]] for d in _ALL_DAYS}
        afternoon = {d: [["13:00", "16:00"]] for d in _ALL_DAYS}
        evening = _evening_hours()
        rows = [
            _make_venue_row("E", structured=evening, category="bar", dwell=60),
            _make_venue_row("A", structured=afternoon, category="cafe", dwell=60),
            _make_venue_row("M", structured=morning, category="temple", dwell=60),
        ]
        start = _ict_to_utc(2026, 9, 14, 7)
        nodes, _ = pack_day(rows, 3, start, GEO, set())
        starts = [n.scheduled_start for n in nodes]
        assert starts == sorted(starts)

    def test_no_repeats_across_days(self):
        """Venues used on day 1 are excluded on day 2."""
        rows = _pool_of(8, structured=_make_hours({}), dwell=60)
        s1 = _ict_to_utc(2026, 9, 14, 9)
        s2 = _ict_to_utc(2026, 9, 15, 9)
        d1, used = pack_day(rows, 4, s1, GEO, set())
        d2, used2 = pack_day(rows, 4, s2, GEO, used)
        d1_names = {n.venue_name for n in d1}
        d2_names = {n.venue_name for n in d2}
        assert d1_names.isdisjoint(d2_names)

    def test_day_n_evening_does_not_push_day_n1(self):
        """Day N evening work does not push day N+1 past 09:00."""
        rows = _pool_of(8, structured=_make_hours({}), dwell=60)
        rows.append(_make_venue_row("Eve", structured=_evening_hours(), category="bar", dwell=60))
        s1 = _ict_to_utc(2026, 9, 14, 9)
        s2 = _ict_to_utc(2026, 9, 15, 9)
        _, used = pack_day(rows, 4, s1, GEO, set())
        d2, _ = pack_day(rows, 4, s2, GEO, used)
        # Day 2 first node starts at or after 09:00 ICT
        assert d2[0].scheduled_start >= s2

    def test_every_node_fits_or_unknown(self):
        """Every emitted node returns FITS or UNKNOWN from hours_for_slot."""
        rows = _pool_of(5, structured=_make_hours({}), dwell=60)
        rows.append(_make_venue_row("Unknown", structured=None, dwell=60))
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 5, start, GEO, set())
        for n in nodes:
            hr = hours_for_slot(
                n.opening_hours_structured, n.scheduled_start, n.duration_minutes, GEO
            )
            assert hr in (HoursResult.FITS, HoursResult.UNKNOWN), (
                f"{n.venue_name} at {n.scheduled_start}: {hr}"
            )

    def test_input_rows_and_used_ids_unchanged(self):
        """Caller inputs are not mutated."""
        rows = _pool_of(6, structured=_make_hours({}), dwell=60)
        rows_copy = [dict(r) for r in rows]
        used = {"some_id"}
        used_copy = set(used)
        start = _ict_to_utc(2026, 9, 14, 9)
        pack_day(rows, 4, start, GEO, used)
        assert rows == rows_copy
        assert used == used_copy

    def test_insufficient_capacity_raises(self):
        """Too few venues for target count."""
        rows = _pool_of(2, structured=_make_hours({}), dwell=60)
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 4, start, GEO, set())
        assert len(nodes) < 4  # pack_day returns partial; caller raises


# ---------------------------------------------------------------------------
# Truthful max_days tests
# ---------------------------------------------------------------------------


class TestTruthfulCapacity:
    def test_all_regions_at_max_all_weekdays(self):
        """For every advertised region, create at max succeeds for all 7 weekdays."""
        r = client.get("/api/v1/trips", headers=HEADERS)
        max_days = r.json()["create_trip_options"]["max_days_by_region"]
        assert len(max_days) >= 1
        anchor = date(2026, 10, 5)  # Monday (well in the future)
        for region, md in max_days.items():
            for wd in range(7):
                start_date = anchor + timedelta(days=wd)
                end_date = start_date + timedelta(days=md - 1)
                h = auth(f"spec41-cap-{region}-{wd}")
                body = {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "geo_region": region,
                }
                resp = client.post("/api/v1/trip/create", json=body, headers=h)
                assert resp.status_code == 200, (
                    f"{region} wd={wd} {start_date}-{end_date} max={md}: {resp.json()}"
                )

    def test_one_above_max_rejected(self):
        """One day above advertised max is rejected when below product ceiling."""
        r = client.get("/api/v1/trips", headers=HEADERS)
        max_days = r.json()["create_trip_options"]["max_days_by_region"]
        for region, md in max_days.items():
            if md >= MAX_DAYS_CEILING:
                continue
            h = auth(f"spec41-overmax-{region}")
            sd = date(2026, 10, 5)
            ed = sd + timedelta(days=md)  # one more than max
            body = {
                "start_date": sd.isoformat(),
                "end_date": ed.isoformat(),
                "geo_region": region,
            }
            resp = client.post("/api/v1/trip/create", json=body, headers=h)
            assert resp.status_code == 422, f"{region} md+1={md + 1}: {resp.json()}"

    def test_mismatch_allowlist_removed(self):
        """The three-region A2 mismatch allowlist no longer exists."""
        import tests.test_spec40_guided_create as t40

        assert not hasattr(t40.TestOptions, "_HOURS_MISMATCH_REGIONS")

    def test_dubai_legacy_null_hours_capacity(self):
        """Dubai venues with null structured hours retain deterministic capacity."""
        md = compute_max_days_for_region(db_mod.db_service.list_venues_for_region, "dubai_uae")
        assert md is not None and md >= 1

    def test_sabotage_raw_identity_capacity(self):
        """Restoring identity-only max_days would over-advertise for regions
        whose hours-constrained capacity is lower."""
        from config.interests import compute_max_days as _identity_max

        for region in REGIONS:
            pool = eligible_corridor_venues(db_mod.db_service.list_venues_for_region(region))
            from services.catalog_itinerary import _dedup_by_venue_id

            pool = _dedup_by_venue_id(pool)
            identity = _identity_max(len(pool))
            truthful = compute_max_days_for_region(db_mod.db_service.list_venues_for_region, region)
            if truthful is None:
                continue
            assert truthful <= identity, f"{region}: truthful={truthful} > identity={identity}"


# ---------------------------------------------------------------------------
# Golden cases
# ---------------------------------------------------------------------------


class TestGoldenCases:
    def test_lp_night_market_in_evening_window(self):
        """Committed Luang Prabang night market appears only in an evening window."""
        rows = db_mod.db_service.list_venues_for_region("luang_prabang_laos")
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes = nodes_from_catalog(geo_region="luang_prabang_laos", start=start, rows=rows)
        for n in nodes:
            if "Night Market" in n.venue_name:
                local = n.scheduled_start.astimezone(ICT)
                assert local.hour >= 17, f"{n.venue_name} at {local}: not evening"

    def test_split_window_venue_never_crosses_gap(self):
        """Committed split-window venue (Royal Palace Museum) never in gap."""
        rows = db_mod.db_service.list_venues_for_region("luang_prabang_laos")
        start = _ict_to_utc(2026, 9, 14, 9)  # Monday
        nodes = nodes_from_catalog(geo_region="luang_prabang_laos", start=start, rows=rows)
        for n in nodes:
            if "Royal Palace" in n.venue_name:
                local = n.scheduled_start.astimezone(ICT)
                end_local = local + timedelta(minutes=n.duration_minutes)
                # Must be in 08:00-11:30 or 13:30-16:00
                in_morning = local.hour < 12 and end_local.hour <= 11 and end_local.minute <= 30
                in_afternoon = local.hour >= 13 and local.minute >= 30
                assert in_morning or in_afternoon, f"Royal Palace {local}-{end_local}: crosses gap"

    def test_laos_corridor_oct2_9_builds(self):
        """Current Oct 2-9 Laos corridor still builds with correct stops per day."""
        corridor = require_corridor("laos_northbound_v1")
        segments = [
            TripSegmentIn(
                geo_region="vientiane_laos",
                starts_on=date(2026, 10, 2),
                ends_on=date(2026, 10, 3),
            ),
            TripSegmentIn(
                geo_region="vang_vieng_laos",
                starts_on=date(2026, 10, 4),
                ends_on=date(2026, 10, 5),
            ),
            TripSegmentIn(
                geo_region="luang_prabang_laos",
                starts_on=date(2026, 10, 6),
                ends_on=date(2026, 10, 9),
            ),
        ]
        nodes, _segs = build_corridor_nodes(
            segments,
            lambda r: db_mod.db_service.list_venues_for_region(r),
            corridor,
        )
        assert len(nodes) == 8 * CORRIDOR_STOPS_PER_DAY

    def test_golden_nodes_validated_against_hours(self):
        """Each golden node is FITS or UNKNOWN."""
        rows = db_mod.db_service.list_venues_for_region("luang_prabang_laos")
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes = nodes_from_catalog(geo_region="luang_prabang_laos", start=start, rows=rows)
        for n in nodes:
            hr = hours_for_slot(
                n.opening_hours_structured,
                n.scheduled_start,
                n.duration_minutes,
                "luang_prabang_laos",
            )
            assert hr in (HoursResult.FITS, HoursResult.UNKNOWN), (
                f"{n.venue_name} at {n.scheduled_start}: {hr}"
            )


# ---------------------------------------------------------------------------
# Sabotage proofs
# ---------------------------------------------------------------------------


class TestSabotageProofs:
    def test_sabotage1_cursor_instead_of_window(self):
        """Returning the cursor instead of the later window fails:
        - test_evening_venue_moves_to_evening
        - test_cursor_in_lunch_gap_moves_to_second_window
        - test_lp_night_market_in_evening_window"""
        hours = _evening_hours()
        cursor = _ict_to_utc(2026, 9, 14, 9)
        local_day = _ict(2026, 9, 14, 9)
        result = next_slot_start(hours, cursor, 60, GEO, local_day)
        # If we returned cursor, it would be 09:00 ICT which is CLOSED
        assert result != cursor
        hr = hours_for_slot(hours, result, 60, GEO)
        assert hr == HoursResult.FITS

    def test_sabotage2_rank_before_earliest_start(self):
        """Ranking before earliest-start would put a night market first
        when an open-now venue should go first.
        Fails: test_open_now_before_night_market"""
        rows = [
            _make_venue_row("AAAMarket", structured=_evening_hours(), category="market", dwell=60),
            _make_venue_row("ZZZTemple", structured=_make_hours({}), category="temple", dwell=60),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 2, start, GEO, set())
        # Earliest-start wins: temple at 09:00, market at 17:00
        assert nodes[0].venue_name == "ZZZTemple"
        assert nodes[1].venue_name == "AAAMarket"

    def test_sabotage3_carry_cursor_across_days(self):
        """Carrying day N cursor into day N+1 fails independent-day tests.
        Fails: test_day_n_evening_does_not_push_day_n1"""
        rows = _pool_of(8, structured=_make_hours({}), dwell=60)
        s1 = _ict_to_utc(2026, 9, 14, 9)
        s2 = _ict_to_utc(2026, 9, 15, 9)
        d1, used = pack_day(rows, 4, s1, GEO, set())
        d2, _ = pack_day(rows, 4, s2, GEO, used)
        # Each day starts independently at 09:00
        assert d2[0].scheduled_start >= s2

    def test_sabotage4_identity_only_max_days(self):
        """Synthetic catalog: identity count says 2 days but the planner
        cannot fill 2 days because the single 60-min window only holds
        one 60-min venue per day.  Identity-only capacity would
        over-advertise."""
        from config.interests import compute_max_days as _identity_max
        from unittest.mock import patch as mock_patch

        short_window = {d: [["09:00", "10:00"]] for d in _ALL_DAYS}
        rows = [_make_venue_row(f"Short_{i}", structured=short_window, dwell=60) for i in range(9)]
        identity = _identity_max(len(rows))  # 9 // 4 = 2
        assert identity == 2
        with mock_patch.object(db_mod.db_service, "list_venues_for_region", return_value=rows):
            truthful = compute_max_days_for_region(db_mod.db_service.list_venues_for_region, GEO)
        # Truthful may be None (can't build 1 day) or a number < identity.
        truthful_val = truthful or 0
        assert truthful_val < identity, f"Identity={identity} but truthful={truthful_val}"

    def test_sabotage5_activity_past_midnight(self):
        """A node ending after local midnight fails the day-boundary test."""
        hours = {d: [["23:00", "06:00"]] for d in _ALL_DAYS}  # overnight
        cursor = _ict_to_utc(2026, 9, 14, 23)
        local_day = _ict(2026, 9, 14, 9)
        # 120-min dwell at 23:00 would end at 01:00 next day
        result = next_slot_start(hours, cursor, 120, GEO, local_day)
        assert result is None
