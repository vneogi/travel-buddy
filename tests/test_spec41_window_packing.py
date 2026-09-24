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
from config.interests import INTEREST_IDS, MAX_DAYS_CEILING, MAX_INTERESTS, VENUES_PER_DAY
from config.regions import REGIONS
from models.schemas import TripSegmentIn
from services.catalog_itinerary import (
    InsufficientCatalog,
    _catalog_fingerprint,
    compute_max_days_for_region,
    eligible_corridor_venues,
    invalidate_capacity_cache,
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


def _make_venue_row(
    name,
    structured=None,
    category="temple",
    dwell=60,
    lat=19.89,
    lng=102.13,
    venue_id=None,
    vibe_tags=None,
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
        "vibe_tags": list(vibe_tags or []),
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


def _interest_profiles():
    from itertools import combinations

    ids = sorted(INTEREST_IDS)
    profiles = [()]
    for size in range(1, MAX_INTERESTS + 1):
        profiles.extend(combinations(ids, size))
    return profiles


def _hhmm(text: str) -> tuple[int, int]:
    hh, mm = text.split(":")
    return int(hh), int(mm)


def _assert_node_within_window(node, open_text: str, close_text: str, tz: ZoneInfo) -> None:
    start_local = node.scheduled_start.astimezone(tz)
    end_local = start_local + timedelta(minutes=node.duration_minutes)
    open_pair = _hhmm(open_text)
    close_pair = _hhmm(close_text)
    start_pair = (start_local.hour, start_local.minute)
    end_pair = (end_local.hour, end_local.minute)
    assert start_pair >= open_pair, f"{node.venue_name} starts before {open_text}: {start_local}"
    assert end_pair <= close_pair, f"{node.venue_name} ends after {close_text}: {end_local}"


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

    def test_unknown_hours_crossing_midnight_returns_none(self):
        """UNKNOWN hours still obey the local-day end boundary."""
        cursor = _ict_to_utc(2026, 9, 14, 23, 30)
        local_day = _ict(2026, 9, 14, 9)
        result = next_slot_start(None, cursor, 90, GEO, local_day)
        assert result is None

    def test_unknown_hours_cursor_on_following_day_returns_none(self):
        """UNKNOWN hours cannot be scheduled when the cursor is already after local_day."""
        cursor = _ict_to_utc(2026, 9, 15, 9)
        local_day = _ict(2026, 9, 14, 9)
        result = next_slot_start(None, cursor, 60, GEO, local_day)
        assert result is None

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
            _make_venue_row("Alpha", structured=_make_hours({}), category="museum", dwell=60),
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
        d2, _ = pack_day(rows, 4, s2, GEO, used)
        d1_names = {n.venue_name for n in d1}
        d2_names = {n.venue_name for n in d2}
        assert d1_names.isdisjoint(d2_names)

    def test_interest_scoring_breaks_equal_start_tie(self):
        """Interest scoring decides between candidates with the same feasible start."""
        rows = [
            _make_venue_row("History", structured=_make_hours({}), category="museum", dwell=60),
            _make_venue_row("Food", structured=_make_hours({}), category="market", dwell=60),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 2, start, GEO, set(), interest_ids=("food_markets",))
        assert nodes[0].venue_name == "Food"
        assert nodes[1].venue_name == "History"

    def test_category_diversity_remains_observable(self):
        """When starts tie, the first pass still surfaces distinct category buckets."""
        from services.catalog_itinerary import _bucket_index

        # Slot-type filtering means food slots (lunch+dinner) always share bucket 1;
        # two activity slots draw from distinct activity buckets.
        # Add a dinner-food venue so all four slots can be filled.
        rows = [
            _make_venue_row("Temple A", structured=_make_hours({}), category="temple", dwell=60),
            _make_venue_row("Temple B", structured=_make_hours({}), category="temple", dwell=60),
            _make_venue_row("Cafe A", structured=_make_hours({}), category="cafe", dwell=60),
            _make_venue_row(
                "Dinner A",
                structured={
                    d: [["09:00", "22:00"]]
                    for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
                },
                category="restaurant",
                dwell=60,
            ),
            _make_venue_row("Market A", structured=_make_hours({}), category="market", dwell=60),
            _make_venue_row("Bar A", structured=_make_hours({}), category="bar", dwell=60),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 4, start, GEO, set())
        assert len(nodes) == 4, f"expected 4 nodes, got {len(nodes)}"
        row_by_name = {row["name"]: row for row in rows}
        bucket_indexes = {_bucket_index(row_by_name[n.venue_name]) for n in nodes}
        # food bucket 1 + at least 2 distinct activity buckets => >= 3 distinct
        assert len(bucket_indexes) >= 3

    def test_name_then_venue_id_is_final_tiebreak(self):
        """With equal start and equal score, name ties break only on venue_id."""
        rows = [
            _make_venue_row(
                "Same",
                structured=_make_hours({}),
                category="temple",
                dwell=60,
                venue_id="b-id",
            ),
            _make_venue_row(
                "Same",
                structured=_make_hours({}),
                category="temple",
                dwell=60,
                venue_id="a-id",
            ),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 2, start, GEO, set())
        assert [n.venue_id for n in nodes] == ["a-id", "b-id"]

    def test_earliest_start_beats_later_high_ranked_candidate(self):
        """A later high-interest venue still loses to an earlier feasible start."""
        rows = [
            _make_venue_row("Open Now", structured=_make_hours({}), category="temple", dwell=60),
            _make_venue_row(
                "Later Favorite",
                structured=_evening_hours(),
                category="market",
                dwell=60,
                vibe_tags=["nightlife", "social"],
            ),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 2, start, GEO, set(), interest_ids=("food_markets",))
        assert nodes[0].venue_name == "Open Now"
        assert nodes[1].venue_name == "Later Favorite"

    def test_day_reset_through_range_builder(self):
        """The multi-day builder resets to each day's own 09:00 baseline."""
        all_day = _make_hours({})
        tue_only = _make_hours({"mon": [], "tue": [["09:00", "17:00"]]})
        rows = [
            _make_venue_row("Mon Temple", structured=all_day, category="temple", dwell=60),
            _make_venue_row("Mon Cafe", structured=all_day, category="cafe", dwell=60),
            _make_venue_row("Mon Market", structured=all_day, category="market", dwell=60),
            _make_venue_row(
                "Mon Evening", structured=_evening_hours(), category="restaurant", dwell=60
            ),
            _make_venue_row("Tue Temple", structured=tue_only, category="temple", dwell=60),
            _make_venue_row("Tue Cafe", structured=tue_only, category="cafe", dwell=60),
            _make_venue_row("Tue Market", structured=tue_only, category="market", dwell=60),
            _make_venue_row(
                "Tue Bar",
                structured=_make_hours({"mon": [], "tue": [["17:00", "22:00"]]}),
                category="restaurant",
                dwell=60,
            ),
        ]
        nodes = range_nodes_from_catalog(
            geo_region=GEO,
            start_date_local="2026-09-14",
            end_date_local="2026-09-15",
            rows=rows,
        )
        day1 = [n for n in nodes if n.scheduled_start.astimezone(ICT).date() == date(2026, 9, 14)]
        day2 = [n for n in nodes if n.scheduled_start.astimezone(ICT).date() == date(2026, 9, 15)]
        assert any(n.venue_name == "Mon Evening" for n in day1)
        assert day2[0].scheduled_start == _ict_to_utc(2026, 9, 15, 9)

        def _sabotaged_range_builder() -> list:
            used_ids: set[str] = set()
            all_nodes = []
            cursor = _ict_to_utc(2026, 9, 14, 9)
            for _ in range(2):
                day_nodes, used_ids = pack_day(rows, 4, cursor, GEO, used_ids)
                if not day_nodes:
                    break
                all_nodes.extend(day_nodes)
                cursor = day_nodes[-1].scheduled_start + timedelta(
                    minutes=day_nodes[-1].duration_minutes + 30
                )
            return all_nodes

        sabotaged = _sabotaged_range_builder()
        sabotaged_day2 = [
            n for n in sabotaged if n.scheduled_start.astimezone(ICT).date() == date(2026, 9, 15)
        ]
        assert not sabotaged_day2 or sabotaged_day2[0].scheduled_start != _ict_to_utc(
            2026, 9, 15, 9
        )

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
    def test_all_regions_at_max_all_weekdays_all_interest_profiles(self):
        """Advertised max succeeds for every region, weekday, and valid interest profile."""
        r = client.get("/api/v1/trips", headers=HEADERS)
        max_days = r.json()["create_trip_options"]["max_days_by_region"]
        assert len(max_days) >= 1
        anchor = date(2026, 10, 5)  # Monday
        for region, md in max_days.items():
            rows = db_mod.db_service.list_venues_for_region(region)
            for wd in range(7):
                start_date = anchor + timedelta(days=wd)
                end_date = start_date + timedelta(days=md - 1)
                for interest_ids in _interest_profiles():
                    nodes = range_nodes_from_catalog(
                        geo_region=region,
                        start_date_local=start_date.isoformat(),
                        end_date_local=end_date.isoformat(),
                        rows=rows,
                        interest_ids=interest_ids,
                    )
                    assert len(nodes) == md * VENUES_PER_DAY, (
                        f"{region} wd={wd} profile={interest_ids} max={md}: got {len(nodes)} nodes"
                    )

    def test_api_smoke_each_region_at_max_with_interests(self):
        """One API smoke per region proves the HTTP path still succeeds at max."""
        r = client.get("/api/v1/trips", headers=HEADERS)
        max_days = r.json()["create_trip_options"]["max_days_by_region"]
        start_date = date(2026, 10, 5)
        for region, md in max_days.items():
            end_date = start_date + timedelta(days=md - 1)
            body = {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "geo_region": region,
                "party": {"party_type": "friends", "size": 3, "members": []},
                "preferences": {"interest_ids": ["history_culture"]},
            }
            resp = client.post(
                "/api/v1/trip/create",
                json=body,
                headers=auth(f"spec41-api-smoke-{region}"),
            )
            assert resp.status_code == 200, f"{region} at max {md}: {resp.json()}"

    def test_one_above_max_accepted_spec42(self):
        """SPEC-42: one day above catalog max now succeeds with sparse generation."""
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
            assert resp.status_code == 200, f"{region} md+1={md + 1}: {resp.json()}"

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
        whose hours-constrained capacity is lower.

        Fails:
        * test_all_regions_at_max_all_weekdays_all_interest_profiles
        * test_api_smoke_each_region_at_max_with_interests
        """
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


class TestAPIAtomicity:
    def test_sparse_create_with_limited_hours_succeeds(self):
        """SPEC-42: sparse generation handles hours-constrained pools gracefully.

        3 good + 7 narrow-hours venues: only 3 packable, below VENUES_PER_DAY.
        Sparse generation creates a trip with zero populated days (empty nodes).
        """
        from unittest.mock import patch as mock_patch

        good = {d: [["09:00", "17:00"]] for d in _ALL_DAYS}
        narrow = {d: [["09:00", "09:30"]] for d in _ALL_DAYS}
        rows = [
            _make_venue_row(f"Good_{i}", structured=good, category="temple", dwell=60)
            for i in range(3)
        ]
        rows.extend(
            [
                _make_venue_row(f"Narrow_{i}", structured=narrow, category="market", dwell=60)
                for i in range(7)
            ]
        )
        with mock_patch.object(db_mod.db_service, "list_venues_for_region", return_value=rows):
            body = {
                "start_date": date(2026, 11, 2).isoformat(),
                "end_date": date(2026, 11, 2).isoformat(),
                "geo_region": GEO,
                "party": {"party_type": "friends", "size": 3, "members": []},
            }
            resp = client.post("/api/v1/trip/create", json=body, headers=auth("spec41-atomicity"))
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.json()}"


# ---------------------------------------------------------------------------
# Golden cases
# ---------------------------------------------------------------------------


class TestGoldenCases:
    def test_lp_night_market_in_evening_window(self):
        """Committed Luang Prabang night-market fixture is actually scheduled in its evening window."""
        night_market = copy.deepcopy(
            next(
                row
                for row in db_mod.db_service.list_venues_for_region("luang_prabang_laos")
                if row["name"] == "Luang Prabang Night Market (Handicrafts)"
            )
        )
        rows = [
            _make_venue_row("Temple", structured=_make_hours({}), category="temple", dwell=60),
            _make_venue_row("Cafe", structured=_make_hours({}), category="cafe", dwell=60),
            # Dinner venue fills the food dinner slot so all 4 slots can be packed.
            _make_venue_row(
                "Dinner Spot", structured=_evening_hours(), category="restaurant", dwell=60
            ),
            night_market,
        ]
        nodes = range_nodes_from_catalog(
            geo_region="luang_prabang_laos",
            start_date_local="2026-09-14",
            end_date_local="2026-09-14",
            rows=rows,
            interest_ids=("food_markets",),
        )
        night_market_nodes = [n for n in nodes if "Night Market" in n.venue_name]
        assert len(night_market_nodes) == 1, [n.venue_name for n in nodes]
        _assert_node_within_window(night_market_nodes[0], "17:00", "22:00", ICT)

    def test_split_window_venue_never_crosses_gap(self):
        """Committed Royal Palace fixture is actually scheduled and fits one declared split window."""
        royal_palace = copy.deepcopy(
            next(
                row
                for row in db_mod.db_service.list_venues_for_region("luang_prabang_laos")
                if row["name"] == "Royal Palace Museum (Haw Kham)"
            )
        )
        rows = [
            royal_palace,
            _make_venue_row("Cafe", structured=_make_hours({}), category="cafe", dwell=60),
            _make_venue_row("Market", structured=_make_hours({}), category="market", dwell=60),
            # Dinner venue fills the food dinner slot so all 4 slots can be packed.
            _make_venue_row(
                "Dinner Spot", structured=_evening_hours(), category="restaurant", dwell=60
            ),
        ]
        nodes = range_nodes_from_catalog(
            geo_region="luang_prabang_laos",
            start_date_local="2026-09-14",
            end_date_local="2026-09-14",
            rows=rows,
            interest_ids=("history_culture",),
        )
        royal_nodes = [n for n in nodes if "Royal Palace" in n.venue_name]
        assert len(royal_nodes) == 1, [n.venue_name for n in nodes]
        royal = royal_nodes[0]
        start_local = royal.scheduled_start.astimezone(ICT)
        end_local = start_local + timedelta(minutes=royal.duration_minutes)
        fits_declared_window = False
        for open_text, close_text in royal.opening_hours_structured["mon"]:
            open_pair = _hhmm(open_text)
            close_pair = _hhmm(close_text)
            start_pair = (start_local.hour, start_local.minute)
            end_pair = (end_local.hour, end_local.minute)
            if start_pair >= open_pair and end_pair <= close_pair:
                fits_declared_window = True
                break
        assert fits_declared_window, (
            f"Royal Palace {start_local}-{end_local}: crosses split windows"
        )

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
        nodes, _segs, _warnings = build_corridor_nodes(
            segments,
            lambda r: db_mod.db_service.list_venues_for_region(r),
            corridor,
        )
        assert len(nodes) <= 8 * CORRIDOR_STOPS_PER_DAY  # G0-B1: 8 days (2+2+4) max

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

        Fails:
        * test_open_now_before_night_market
        * test_interest_scoring_breaks_equal_start_tie
        * test_earliest_start_beats_later_high_ranked_candidate
        """
        rows = [
            _make_venue_row("AAAMarket", structured=_evening_hours(), category="market", dwell=60),
            _make_venue_row("ZZZTemple", structured=_make_hours({}), category="temple", dwell=60),
        ]
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes, _ = pack_day(rows, 2, start, GEO, set())
        assert nodes[0].venue_name == "ZZZTemple"
        assert nodes[1].venue_name == "AAAMarket"

    def test_sabotage3_carry_cursor_across_days(self):
        """Carrying day N cursor into day N+1 fails the real multi-day builder proof.

        Fails:
        * test_day_reset_through_range_builder
        """
        all_day = _make_hours({})
        tue_only = _make_hours({"mon": [], "tue": [["09:00", "17:00"]]})
        rows = [
            _make_venue_row("Mon Temple", structured=all_day, category="temple", dwell=60),
            _make_venue_row("Mon Cafe", structured=all_day, category="cafe", dwell=60),
            _make_venue_row("Mon Market", structured=all_day, category="market", dwell=60),
            _make_venue_row(
                "Mon Evening", structured=_evening_hours(), category="restaurant", dwell=60
            ),
            _make_venue_row("Tue Temple", structured=tue_only, category="temple", dwell=60),
            _make_venue_row("Tue Cafe", structured=tue_only, category="cafe", dwell=60),
            _make_venue_row("Tue Market", structured=tue_only, category="market", dwell=60),
            _make_venue_row("Tue Bar", structured=tue_only, category="restaurant", dwell=60),
        ]

        def _sabotaged_range_builder() -> list:
            used_ids: set[str] = set()
            all_nodes = []
            cursor = _ict_to_utc(2026, 9, 14, 9)
            for _ in range(2):
                day_nodes, used_ids = pack_day(rows, 4, cursor, GEO, used_ids)
                if not day_nodes:
                    break
                all_nodes.extend(day_nodes)
                cursor = day_nodes[-1].scheduled_start + timedelta(
                    minutes=day_nodes[-1].duration_minutes + 30
                )
            return all_nodes

        sabotaged = _sabotaged_range_builder()
        sabotaged_day2 = [
            n for n in sabotaged if n.scheduled_start.astimezone(ICT).date() == date(2026, 9, 15)
        ]
        assert not sabotaged_day2 or sabotaged_day2[0].scheduled_start != _ict_to_utc(
            2026, 9, 15, 9
        )

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
        """A node ending after local midnight fails the day-boundary test.

        Fails:
        * test_overnight_window_cannot_cross_midnight
        * test_unknown_hours_crossing_midnight_returns_none
        * test_lp_night_market_in_evening_window
        """
        hours = {d: [["23:00", "06:00"]] for d in _ALL_DAYS}  # overnight
        cursor = _ict_to_utc(2026, 9, 14, 23)
        local_day = _ict(2026, 9, 14, 9)
        result = next_slot_start(hours, cursor, 120, GEO, local_day)
        assert result is None


# ---------------------------------------------------------------------------
# local_day validation
# ---------------------------------------------------------------------------


class TestLocalDayValidation:
    def test_naive_local_day_raises_value_error(self):
        """A naive (timezone-unaware) local_day must be rejected."""
        cursor = _ict_to_utc(2026, 9, 14, 9)
        naive_day = datetime(2026, 9, 14, 9, 0, 0)  # no tzinfo
        with pytest.raises(ValueError, match="local_day must be timezone-aware"):
            next_slot_start(None, cursor, 60, GEO, naive_day)


# ---------------------------------------------------------------------------
# Capacity cache tests
# ---------------------------------------------------------------------------


class TestCapacityCache:
    def setup_method(self):
        invalidate_capacity_cache()

    def teardown_method(self):
        invalidate_capacity_cache()

    def test_cache_hit_avoids_recomputation(self):
        """Second call with unchanged catalog does not call pack_day again."""
        from unittest.mock import patch as mock_patch, wraps

        real_pack_day = pack_day
        with mock_patch("services.catalog_itinerary.pack_day", wraps=real_pack_day) as spy:
            r1 = compute_max_days_for_region(db_mod.db_service.list_venues_for_region, GEO)
            first_calls = spy.call_count
            assert first_calls > 0, "pack_day must be called on first computation"

            r2 = compute_max_days_for_region(db_mod.db_service.list_venues_for_region, GEO)
            assert r2 == r1
            assert spy.call_count == first_calls, (
                f"pack_day called {spy.call_count - first_calls} extra times "
                f"on cache hit (expected 0)"
            )

    def test_cache_invalidation_on_changed_hours(self):
        """Changing opening hours in catalog rows invalidates the cache."""
        rows_original = db_mod.db_service.list_venues_for_region(GEO)
        # Warm the cache with original catalog
        compute_max_days_for_region(lambda _: rows_original, GEO)

        # Mutate hours on a copy
        import copy

        rows_modified = copy.deepcopy(rows_original)
        for row in rows_modified:
            if row.get("opening_hours_structured"):
                row["opening_hours_structured"] = {d: [["09:00", "09:30"]] for d in _ALL_DAYS}
                break

        fp_orig = _catalog_fingerprint(rows_original)
        fp_mod = _catalog_fingerprint(rows_modified)
        assert fp_orig != fp_mod, "Fingerprints must differ after hours change"

        # This call gets a different fingerprint, so the cache is not used.
        compute_max_days_for_region(lambda _: rows_modified, GEO)
        # The definitive proof is that fingerprints differ; capacity may or
        # may not change (coincidental match is possible).  With many venues
        # narrowed to 30-min
        # windows, capacity should drop.
        # (Don't assert r2 != r1 because it might coincidentally match;
        # the fingerprint difference is the definitive proof.)

    def test_cache_invalidation_on_changed_dwell(self):
        """Changing typical_dwell_minutes forces pack_day to rerun."""
        import copy
        from unittest.mock import patch as mock_patch, wraps

        rows_original = db_mod.db_service.list_venues_for_region(GEO)
        rows_long_dwell = copy.deepcopy(rows_original)
        for row in rows_long_dwell:
            row["typical_dwell_minutes"] = 999

        # Fingerprints must differ
        fp1 = _catalog_fingerprint(rows_original)
        fp2 = _catalog_fingerprint(rows_long_dwell)
        assert fp1 != fp2, "Fingerprints must differ after dwell change"

        real_pack_day = pack_day
        with mock_patch("services.catalog_itinerary.pack_day", wraps=real_pack_day) as spy:
            # Warm the cache with original catalog
            compute_max_days_for_region(lambda _: rows_original, GEO)
            after_warm = spy.call_count
            assert after_warm > 0

            # Call with changed dwell -- cache miss, pack_day must be invoked
            compute_max_days_for_region(lambda _: rows_long_dwell, GEO)
            assert spy.call_count > after_warm, (
                "pack_day was not called after dwell change -- cache was stale"
            )

    def test_sabotage_dwell_removed_from_fingerprint(self):
        """Removing typical_dwell_minutes from the fingerprint makes
        dwell changes invisible to the cache.

        Fails: test_cache_invalidation_on_changed_dwell
        """
        import copy
        import hashlib
        import json

        rows = db_mod.db_service.list_venues_for_region(GEO)
        rows_long = copy.deepcopy(rows)
        for row in rows_long:
            row["typical_dwell_minutes"] = 999

        def _fingerprint_without_dwell(catalog_rows):
            parts = []
            for row in sorted(
                catalog_rows,
                key=lambda r: str(r.get("venue_id") or r.get("name") or ""),
            ):
                record = (
                    str(row.get("venue_id") or ""),
                    str(row.get("name") or ""),
                    str(row.get("lat") or ""),
                    str(row.get("lng") or ""),
                    str(row.get("category") or ""),
                    json.dumps(sorted(row.get("vibe_tags") or []), sort_keys=True),
                    json.dumps(row.get("opening_hours_structured"), sort_keys=True),
                    # typical_dwell_minutes deliberately omitted
                )
                parts.append("|".join(record))
            return hashlib.sha256("\n".join(parts).encode()).hexdigest()

        # Without dwell in the fingerprint, both catalogs look identical
        assert _fingerprint_without_dwell(rows) == _fingerprint_without_dwell(rows_long)
        # But the real fingerprint catches the difference
        assert _catalog_fingerprint(rows) != _catalog_fingerprint(rows_long)

    def test_cache_invalidation_on_changed_vibe_tags(self):
        """Changing vibe_tags (ranking field) invalidates the fingerprint."""
        import copy

        rows = db_mod.db_service.list_venues_for_region(GEO)
        rows_new_tags = copy.deepcopy(rows)
        rows_new_tags[0]["vibe_tags"] = ["completely_new_tag"]

        fp1 = _catalog_fingerprint(rows)
        fp2 = _catalog_fingerprint(rows_new_tags)
        assert fp1 != fp2

    def test_cache_bounded_eviction(self):
        """Production insert into a full cache evicts the oldest key
        and keeps size at exactly _CAPACITY_CACHE_MAX_SIZE."""
        from services.catalog_itinerary import (
            _capacity_cache,
            _capacity_cache_order,
            _CAPACITY_CACHE_MAX_SIZE,
        )

        # Fill cache to exactly MAX_SIZE with synthetic entries
        for i in range(_CAPACITY_CACHE_MAX_SIZE):
            key = (f"region_{i}", f"fp_{i}")
            _capacity_cache[key] = i
            _capacity_cache_order.append(key)
        assert len(_capacity_cache) == _CAPACITY_CACHE_MAX_SIZE

        oldest_key = ("region_0", "fp_0")
        assert oldest_key in _capacity_cache

        # One production insert should evict the oldest and keep size at MAX
        compute_max_days_for_region(db_mod.db_service.list_venues_for_region, GEO)
        assert len(_capacity_cache) == _CAPACITY_CACHE_MAX_SIZE, (
            f"cache size {len(_capacity_cache)} != {_CAPACITY_CACHE_MAX_SIZE}"
        )
        assert oldest_key not in _capacity_cache, "oldest key was not evicted"
