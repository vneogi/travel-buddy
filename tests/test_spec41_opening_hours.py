"""SPEC-41 Phase A1: Structured opening-hours evaluator + provider parity tests.

Covers:
  - Evaluator: weekday, closed, split, overnight, boundaries, unknown
  - Real Laos golden cases: split-window, evening, closed weekday
  - Provider parity: in-memory and mocked Supabase
  - Sabotage proofs (run manually, recorded in commit message)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from services.opening_hours import HoursResult, check_slot

# ---------------------------------------------------------------------------
# Timezone fixtures
# ---------------------------------------------------------------------------

_ICT = ZoneInfo("Asia/Vientiane")  # UTC+7, no DST
_GST = ZoneInfo("Asia/Dubai")  # UTC+4, no DST


def _ict(year, month, day, hour, minute=0):
    """Shorthand for a Vientiane-local aware datetime."""
    return datetime(year, month, day, hour, minute, tzinfo=_ICT)


# ---------------------------------------------------------------------------
# Structured hours fixtures
# ---------------------------------------------------------------------------

# Royal Palace Museum style: split windows, closed Tuesday
_SPLIT_HOURS = {
    "mon": [["08:00", "11:30"], ["13:30", "16:00"]],
    "tue": [],
    "wed": [["08:00", "11:30"], ["13:30", "16:00"]],
    "thu": [["08:00", "11:30"], ["13:30", "16:00"]],
    "fri": [["08:00", "11:30"], ["13:30", "16:00"]],
    "sat": [["08:00", "11:30"], ["13:30", "16:00"]],
    "sun": [["08:00", "11:30"], ["13:30", "16:00"]],
}

# Simple all-week venue
_SIMPLE_HOURS = {
    "mon": [["09:00", "17:00"]],
    "tue": [["09:00", "17:00"]],
    "wed": [["09:00", "17:00"]],
    "thu": [["09:00", "17:00"]],
    "fri": [["09:00", "17:00"]],
    "sat": [["09:00", "17:00"]],
    "sun": [["09:00", "17:00"]],
}

# Overnight bar: opens 20:00, closes 02:00
_OVERNIGHT_HOURS = {
    "mon": [["20:00", "02:00"]],
    "tue": [["20:00", "02:00"]],
    "wed": [["20:00", "02:00"]],
    "thu": [["20:00", "02:00"]],
    "fri": [["20:00", "02:00"]],
    "sat": [["20:00", "03:00"]],  # later on Saturday
    "sun": [],  # closed Sunday
}

# Evening-only: 17:00-22:00 every day
_EVENING_HOURS = {
    "mon": [["17:00", "22:00"]],
    "tue": [["17:00", "22:00"]],
    "wed": [["17:00", "22:00"]],
    "thu": [["17:00", "22:00"]],
    "fri": [["17:00", "22:00"]],
    "sat": [["17:00", "22:00"]],
    "sun": [["17:00", "22:00"]],
}


# =========================================================================
# 1. Evaluator unit tests
# =========================================================================


class TestOrdinaryWeekday:
    def test_monday_morning_fits(self):
        # Monday 10:00, 60 min -> 10:00-11:00 inside 09:00-17:00
        start = _ict(2026, 9, 14, 10)  # Monday
        assert check_slot(_SIMPLE_HOURS, start, 60) == HoursResult.FITS

    def test_closed_weekday(self):
        # Tuesday on split hours -> explicitly closed (empty list)
        start = _ict(2026, 9, 15, 10)  # Tuesday
        assert check_slot(_SPLIT_HOURS, start, 60) == HoursResult.CLOSED


class TestSplitWindows:
    def test_first_split_window_fits(self):
        # Monday 08:30, 60 min -> 08:30-09:30 inside [08:00, 11:30]
        start = _ict(2026, 9, 14, 8, 30)  # Monday
        assert check_slot(_SPLIT_HOURS, start, 60) == HoursResult.FITS

    def test_second_split_window_fits(self):
        # Monday 14:00, 90 min -> 14:00-15:30 inside [13:30, 16:00]
        start = _ict(2026, 9, 14, 14)  # Monday
        assert check_slot(_SPLIT_HOURS, start, 90) == HoursResult.FITS

    def test_lunch_gap_is_closed(self):
        # Monday 11:00, 180 min -> 11:00-14:00 crosses gap
        start = _ict(2026, 9, 14, 11)  # Monday
        assert check_slot(_SPLIT_HOURS, start, 180) == HoursResult.CLOSED

    def test_dwell_extends_beyond_close(self):
        # Monday 15:30, 60 min -> 15:30-16:30, but window closes 16:00
        start = _ict(2026, 9, 14, 15, 30)  # Monday
        assert check_slot(_SPLIT_HOURS, start, 60) == HoursResult.CLOSED


class TestExactBoundaries:
    def test_start_at_open_end_at_close(self):
        # Monday 09:00, 480 min (8h) -> exactly 09:00-17:00
        start = _ict(2026, 9, 14, 9)  # Monday
        assert check_slot(_SIMPLE_HOURS, start, 480) == HoursResult.FITS

    def test_exact_split_boundaries(self):
        # Monday 08:00, 210 min (3h30) -> exactly 08:00-11:30
        start = _ict(2026, 9, 14, 8)  # Monday
        assert check_slot(_SPLIT_HOURS, start, 210) == HoursResult.FITS


class TestOvernight:
    def test_monday_evening_overnight_fits(self):
        # Monday 21:00, 240 min (4h) -> 21:00-01:00, window 20:00-02:00
        start = _ict(2026, 9, 14, 21)  # Monday
        assert check_slot(_OVERNIGHT_HOURS, start, 240) == HoursResult.FITS

    def test_tuesday_early_morning_from_monday_overnight(self):
        # Tuesday 00:30, 60 min -> 00:30-01:30
        # Monday's overnight window extends to 02:00 Tuesday
        start = _ict(2026, 9, 15, 0, 30)  # Tuesday
        assert check_slot(_OVERNIGHT_HOURS, start, 60) == HoursResult.FITS

    def test_early_morning_without_previous_overnight(self):
        # Monday 00:30, 60 min -> Sunday is closed (no overnight)
        start = _ict(2026, 9, 14, 0, 30)  # Monday (Sunday is [])
        assert check_slot(_OVERNIGHT_HOURS, start, 60) == HoursResult.CLOSED


class TestUnknownAndMalformed:
    def test_null_data_returns_unknown(self):
        start = _ict(2026, 9, 14, 10)
        assert check_slot(None, start, 60) == HoursResult.UNKNOWN

    def test_string_data_returns_unknown(self):
        start = _ict(2026, 9, 14, 10)
        assert check_slot("09:00-17:00", start, 60) == HoursResult.UNKNOWN

    def test_malformed_window_returns_unknown_or_closed(self):
        # Windows that are not [str, str] -- skip malformed, exhaust list
        hours = {
            "mon": [[123, 456]],
            **{d: [["09:00", "17:00"]] for d in _SPLIT_HOURS if d != "mon"},
        }
        start = _ict(2026, 9, 14, 10)  # Monday
        # Only malformed windows on Monday -> no match -> CLOSED
        assert check_slot(hours, start, 60) == HoursResult.CLOSED

    def test_missing_weekday_key_returns_unknown(self):
        # Hours dict that has no "mon" key
        hours = {"tue": [["09:00", "17:00"]]}
        start = _ict(2026, 9, 14, 10)  # Monday
        assert check_slot(hours, start, 60) == HoursResult.UNKNOWN

    def test_list_as_hours_returns_unknown(self):
        start = _ict(2026, 9, 14, 10)
        assert check_slot([["09:00", "17:00"]], start, 60) == HoursResult.UNKNOWN


class TestProgrammerInputErrors:
    def test_naive_datetime_raises(self):
        naive = datetime(2026, 9, 14, 10)
        with pytest.raises(ValueError, match="timezone-aware"):
            check_slot(_SIMPLE_HOURS, naive, 60)

    def test_zero_duration_raises(self):
        start = _ict(2026, 9, 14, 10)
        with pytest.raises(ValueError, match="positive"):
            check_slot(_SIMPLE_HOURS, start, 0)

    def test_negative_duration_raises(self):
        start = _ict(2026, 9, 14, 10)
        with pytest.raises(ValueError, match="positive"):
            check_slot(_SIMPLE_HOURS, start, -30)


# =========================================================================
# 2. Real Laos golden cases
# =========================================================================


def _load_laos_venues(filename: str) -> list:
    path = Path(__file__).resolve().parent.parent / "data" / filename
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("venues", [])


def _find_venue(venues: list, name_substring: str) -> Optional[dict]:
    for v in venues:
        if name_substring.lower() in (v.get("name") or "").lower():
            return v
    return None


class TestLaosGoldenCases:
    """Tests against committed catalog data using destination-local datetimes."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.lp_venues = _load_laos_venues("laos_luang_prabang.json")

    def test_royal_palace_split_window_morning(self):
        """Royal Palace Museum: Mon 08:00-11:30, 13:30-16:00. Closed Tue."""
        v = _find_venue(self.lp_venues, "Royal Palace Museum")
        assert v is not None, "Royal Palace Museum not found in catalog"
        hours = v["opening_hours"]
        assert isinstance(hours, dict)
        # Wednesday 09:00, 90 min -> fits first window
        start = _ict(2026, 9, 16, 9)  # Wednesday
        assert check_slot(hours, start, 90) == HoursResult.FITS

    def test_royal_palace_closed_tuesday(self):
        """Royal Palace Museum: Tuesday is explicitly closed."""
        v = _find_venue(self.lp_venues, "Royal Palace Museum")
        hours = v["opening_hours"]
        # Tuesday 10:00 -> closed
        start = _ict(2026, 9, 15, 10)  # Tuesday
        assert check_slot(hours, start, 60) == HoursResult.CLOSED

    def test_night_market_evening_fits(self):
        """Luang Prabang Night Market: 17:00-22:00 every day."""
        v = _find_venue(self.lp_venues, "Night Market")
        assert v is not None, "Night Market not found in catalog"
        hours = v["opening_hours"]
        assert isinstance(hours, dict)
        # Thursday 18:00, 120 min -> 18:00-20:00 fits 17:00-22:00
        start = _ict(2026, 9, 17, 18)  # Thursday
        assert check_slot(hours, start, 120) == HoursResult.FITS

    def test_night_market_morning_is_closed(self):
        """Night Market at 10:00 -> closed (evening only)."""
        v = _find_venue(self.lp_venues, "Night Market")
        hours = v["opening_hours"]
        start = _ict(2026, 9, 17, 10)  # Thursday
        assert check_slot(hours, start, 60) == HoursResult.CLOSED


# =========================================================================
# 3. Provider parity: in-memory
# =========================================================================


class TestInMemoryParity:
    """Prove the in-memory store preserves opening_hours_structured."""

    @pytest.fixture(autouse=True)
    def _seed(self):
        from services.database_service import DatabaseService

        self.db = DatabaseService()
        from models.schemas import VenueRAG

        self.db.add_venue(
            VenueRAG(
                venue_id="parity-lp-1",
                name="Parity Test Venue",
                description="test",
                micro_location="test",
                lat=19.8,
                lng=102.1,
                opening_hours="08:00-16:00",
                opening_hours_structured=_SPLIT_HOURS,
                geo_region="luang_prabang_laos",
            )
        )
        # Legacy Dubai venue: no structured hours
        self.db.add_venue(
            VenueRAG(
                venue_id="parity-dxb-1",
                name="Legacy Dubai Venue",
                description="test",
                micro_location="test",
                lat=25.2,
                lng=55.3,
                opening_hours="10:00-22:00",
                geo_region="dubai_uae",
            )
        )

    def test_get_venue_preserves_structured_hours(self):
        v = self.db.get_venue_by_id("parity-lp-1")
        assert v is not None
        assert v.opening_hours_structured == _SPLIT_HOURS

    def test_list_venues_preserves_structured_hours(self):
        rows = self.db.list_venues_for_region("luang_prabang_laos")
        assert len(rows) >= 1
        found = [r for r in rows if r["venue_id"] == "parity-lp-1"]
        assert len(found) == 1
        assert found[0]["opening_hours_structured"] == _SPLIT_HOURS

    def test_legacy_venue_has_null_structured_hours(self):
        v = self.db.get_venue_by_id("parity-dxb-1")
        assert v is not None
        assert v.opening_hours_structured is None

    def test_no_invented_defaults(self):
        """Legacy venue must not have 09:00-23:00 in structured form."""
        v = self.db.get_venue_by_id("parity-dxb-1")
        assert v.opening_hours_structured is None


# =========================================================================
# 4. Provider parity: mocked Supabase
# =========================================================================


class TestSupabaseParity:
    """Prove SupabaseService projections include opening_hours_structured."""

    def _make_svc(self):
        """Create a SupabaseService with a mocked client."""
        from services.supabase_service import SupabaseService

        svc = object.__new__(SupabaseService)
        svc._client = MagicMock()
        return svc

    def test_list_venues_selects_structured_hours(self):
        svc = self._make_svc()
        mock_table = MagicMock()
        svc.client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data=[
                {
                    "venue_id": "v1",
                    "name": "Test",
                    "opening_hours": "08:00-16:00",
                    "opening_hours_structured": _SPLIT_HOURS,
                    "geo_region": "luang_prabang_laos",
                }
            ]
        )
        rows = svc.list_venues_for_region("luang_prabang_laos")
        # Verify the select string includes opening_hours_structured
        select_call = mock_table.select.call_args
        select_str = select_call[0][0] if select_call[0] else ""
        assert "opening_hours_structured" in select_str
        assert rows[0]["opening_hours_structured"] == _SPLIT_HOURS

    def test_get_venue_selects_structured_hours(self):
        svc = self._make_svc()
        mock_table = MagicMock()
        svc.client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data=[
                {
                    "venue_id": "v1",
                    "name": "Test",
                    "description": "d",
                    "micro_location": "m",
                    "lat": 19.8,
                    "lng": 102.1,
                    "vibe_tags": [],
                    "audience": [],
                    "category": "experience",
                    "is_sponsored": False,
                    "bid_weight": 0.0,
                    "opening_hours": "08:00-16:00",
                    "opening_hours_structured": _SPLIT_HOURS,
                    "geo_region": "luang_prabang_laos",
                    "names_local": None,
                    "landmarks_local": None,
                    "nearest_landmark": None,
                }
            ]
        )
        v = svc.get_venue_by_id("v1")
        select_call = mock_table.select.call_args
        select_str = select_call[0][0] if select_call[0] else ""
        assert "opening_hours_structured" in select_str
        assert v is not None
        assert v.opening_hours_structured == _SPLIT_HOURS

    def test_legacy_row_without_structured_hours(self):
        """A Supabase row missing the column still parses."""
        svc = self._make_svc()
        mock_table = MagicMock()
        svc.client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data=[
                {
                    "venue_id": "legacy-1",
                    "name": "Old Dubai Place",
                    "description": "d",
                    "micro_location": "m",
                    "lat": 25.2,
                    "lng": 55.3,
                    "vibe_tags": [],
                    "audience": [],
                    "category": "experience",
                    "is_sponsored": False,
                    "bid_weight": 0.0,
                    "opening_hours": "10:00-22:00",
                    # NOTE: no opening_hours_structured key at all
                    "geo_region": "dubai_uae",
                    "names_local": None,
                    "landmarks_local": None,
                    "nearest_landmark": None,
                }
            ]
        )
        v = svc.get_venue_by_id("legacy-1")
        assert v is not None
        assert v.opening_hours_structured is None


# =========================================================================
# 5. Seeded data integration
# =========================================================================


class TestSeededData:
    """Verify seed_venues preserves structured hours for Laos venues."""

    @pytest.fixture(autouse=True)
    def _seed(self):
        from services.database_service import DatabaseService

        self.db = DatabaseService()
        # Temporarily replace the singleton so seed_venues uses our instance
        import seed_data
        import services.database_service as db_mod

        original = db_mod.db_service
        db_mod.db_service = self.db
        seed_data.db_service = self.db
        try:
            seed_data.seed_venues()
        finally:
            db_mod.db_service = original
            seed_data.db_service = original

    def test_laos_venue_has_structured_hours(self):
        rows = self.db.list_venues_for_region("luang_prabang_laos")
        assert len(rows) > 0
        # Royal Palace Museum should have structured hours
        palace = [r for r in rows if "Royal Palace" in r.get("name", "")]
        assert len(palace) == 1
        sh = palace[0].get("opening_hours_structured")
        assert sh is not None
        assert isinstance(sh, dict)
        assert "mon" in sh
        assert "tue" in sh
        # Tuesday is closed
        assert sh["tue"] == []

    def test_dubai_venue_has_null_structured_hours(self):
        rows = self.db.list_venues_for_region("dubai_uae")
        assert len(rows) > 0
        for row in rows:
            assert row.get("opening_hours_structured") is None, (
                f"Dubai venue {row['name']} should not have structured hours"
            )
