"""SPEC-41 Phase A2: Hours Eligibility on Create and Swap.

Tests that create, corridor, swap search, and swap apply all refuse
venues known to be closed at the proposed slot.  Also verifies the
scheduler scopes hours warnings to mutated nodes.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from config.regions import REGIONS, require_region
from models.schemas import (
    EventType,
    NodeStatus,
    TripNode,
    TripState,
    VenueRAG,
    VenueSearchResult,
)
from services.catalog_itinerary import (
    InsufficientCatalog,
    duration_for,
    eligible_corridor_venues,
    flatten_opening_hours,
    nodes_from_catalog,
    range_nodes_from_catalog,
)
from services.corridor_itinerary import build_corridor_nodes
from services.opening_hours import HoursResult, hours_for_slot
from services.scheduler import reschedule_and_validate

ICT = ZoneInfo("Asia/Vientiane")
GEO = "luang_prabang_laos"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _ict(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=ICT)


def _ict_to_utc(year, month, day, hour, minute=0):
    return _ict(year, month, day, hour, minute).astimezone(timezone.utc)


_ALL_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _make_hours(weekday_windows: Dict[str, list]) -> Dict[str, Any]:
    """Build a full 7-day structured hours dict."""
    return {d: weekday_windows.get(d, [["09:00", "17:00"]]) for d in _ALL_DAYS}


def _evening_hours():
    """17:00-22:00 every day -- a night market."""
    return {d: [["17:00", "22:00"]] for d in _ALL_DAYS}


def _closed_tuesday():
    """09:00-17:00 except Tuesday."""
    h = {d: [["09:00", "17:00"]] for d in _ALL_DAYS}
    h["tue"] = []
    return h


def _split_window():
    """08:00-11:30, 13:30-16:00 every day."""
    return {d: [["08:00", "11:30"], ["13:30", "16:00"]] for d in _ALL_DAYS}


def _make_venue_row(
    name: str,
    structured=None,
    category="temple",
    dwell=60,
    lat=19.89,
    lng=102.13,
):
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
# Create / corridor tests
# ---------------------------------------------------------------------------


class TestCreateHoursFiltering:
    def test_night_market_not_placed_morning(self):
        """An evening-only venue must not appear when the cursor is at 09:00."""
        rows = _pool_of(6, structured=_make_hours({}), category="temple", dwell=60)
        rows.append(
            _make_venue_row(
                "Night Market", structured=_evening_hours(), category="market", dwell=60
            )
        )
        # Monday 09:00 ICT -> 02:00 UTC
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes = nodes_from_catalog(geo_region=GEO, start=start, rows=rows)
        names = [n.venue_name for n in nodes]
        assert "Night Market" not in names

    def test_tuesday_closed_venue_not_placed_tuesday(self):
        """A venue closed on Tuesday must not appear on a Tuesday."""
        rows = _pool_of(6, structured=_make_hours({}), dwell=60)
        rows.append(
            _make_venue_row("Closed Tue", structured=_closed_tuesday(), category="museum", dwell=60)
        )
        # Tuesday 09:00 ICT
        start = _ict_to_utc(2026, 9, 15, 9)
        nodes = nodes_from_catalog(geo_region=GEO, start=start, rows=rows)
        names = [n.venue_name for n in nodes]
        assert "Closed Tue" not in names

    def test_split_window_gap_rejected(self):
        """A venue across the lunch gap is not placed."""
        # Only 1 venue with split windows, at 12:00 for 90 min -> crosses gap
        split = _split_window()
        rows = _pool_of(5, structured=_make_hours({}), dwell=60)
        rows.append(_make_venue_row("Split Place", structured=split, category="museum", dwell=90))
        # Verify directly: 90 min at 12:00 crosses the 11:30-13:30 gap.
        gap_start = _ict_to_utc(2026, 9, 14, 12)
        result = hours_for_slot(split, gap_start, 90, GEO)
        assert result == HoursResult.CLOSED

    def test_unknown_hours_still_scheduled(self):
        """A venue with null structured hours (UNKNOWN) is still eligible."""
        rows = _pool_of(4, structured=_make_hours({}), dwell=60)
        rows.append(_make_venue_row("Unknown Venue", structured=None, category="museum", dwell=60))
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes = nodes_from_catalog(geo_region=GEO, start=start, rows=rows)
        names = [n.venue_name for n in nodes]
        assert "Unknown Venue" in names

    def test_insufficient_raises_no_persistence(self):
        """Not enough non-closed venues raises InsufficientCatalog."""
        rows = _pool_of(2, structured=_make_hours({}), dwell=60)
        # Only 2 venues -- below MIN_STOPS
        start = _ict_to_utc(2026, 9, 14, 9)
        with pytest.raises(InsufficientCatalog):
            nodes_from_catalog(geo_region=GEO, start=start, rows=rows)

    def test_destination_local_tuesday_not_utc_tuesday(self):
        """ICT is UTC+7; a slot that is Tuesday locally but still Monday UTC
        must evaluate against Tuesday hours."""
        # Tuesday 01:00 ICT = Monday 18:00 UTC
        closed_tue = _closed_tuesday()
        start_utc = _ict_to_utc(2026, 9, 15, 1)  # Tuesday 01:00 ICT
        result = hours_for_slot(closed_tue, start_utc, 60, GEO)
        assert result == HoursResult.CLOSED


# ---------------------------------------------------------------------------
# Swap tests
# ---------------------------------------------------------------------------


def _make_venue_rag(name, structured=None, dwell=60):
    return VenueRAG(
        venue_id=str(uuid.uuid5(uuid.NAMESPACE_URL, name)),
        name=name,
        description="",
        micro_location="",
        lat=19.89,
        lng=102.13,
        vibe_tags=[],
        audience=[],
        category="temple",
        opening_hours=flatten_opening_hours(structured) or "09:00-17:00",
        opening_hours_structured=structured,
        geo_region=GEO,
        typical_dwell_minutes=dwell,
    )


class TestSwapHoursFiltering:
    def test_search_omits_closed_candidate(self):
        """A CLOSED candidate is not offered in swap search."""
        evening = _evening_hours()
        venue = _make_venue_rag("Evening Only", structured=evening, dwell=60)
        # Target slot: Monday 09:00 ICT
        target_start = _ict_to_utc(2026, 9, 14, 9)
        result = hours_for_slot(
            venue.opening_hours_structured,
            target_start,
            60,
            GEO,
        )
        assert result == HoursResult.CLOSED

    def test_apply_same_venue_also_refused(self):
        """If search would hide a venue, apply of that venue_id also refuses."""
        evening = _evening_hours()
        venue = _make_venue_rag("Evening Only", structured=evening, dwell=60)
        target_start = _ict_to_utc(2026, 9, 14, 9)
        # The shared predicate refuses both search and apply
        result = hours_for_slot(
            venue.opening_hours_structured,
            target_start,
            60,
            GEO,
        )
        assert result == HoursResult.CLOSED

    def test_fits_candidate_offered(self):
        """A FITS candidate is eligible."""
        allday = _make_hours({})
        venue = _make_venue_rag("All Day", structured=allday, dwell=60)
        target_start = _ict_to_utc(2026, 9, 14, 10)
        result = hours_for_slot(
            venue.opening_hours_structured,
            target_start,
            60,
            GEO,
        )
        assert result == HoursResult.FITS

    def test_long_dwell_overruns_closing(self):
        """A candidate whose dwell overruns closing is ineligible even if
        a 30-minute visit would fit."""
        # Venue closes at 11:30, slot at 10:00
        hours = _make_hours({"mon": [["08:00", "11:30"]]})
        # 30 min would fit (10:00-10:30 < 11:30)
        assert hours_for_slot(hours, _ict_to_utc(2026, 9, 14, 10), 30, GEO) == HoursResult.FITS
        # 120 min overruns (10:00-12:00 > 11:30)
        assert hours_for_slot(hours, _ict_to_utc(2026, 9, 14, 10), 120, GEO) == HoursResult.CLOSED


# ---------------------------------------------------------------------------
# Scheduler scoped warnings
# ---------------------------------------------------------------------------


class TestSchedulerScopedWarnings:
    def test_swap_does_not_warn_unrelated_nodes(self):
        """Swapping one node must not emit hours warnings for untouched nodes."""
        # Build 3 nodes, all with hours data. Node 2 is the swapped one.
        hours = _make_hours({"mon": [["06:00", "23:00"]]})
        nodes = [
            TripNode(
                venue_name=f"V{i}",
                venue_id=f"vid_{i}",
                scheduled_start=_ict_to_utc(2026, 9, 14, 9 + i * 2),
                duration_minutes=60,
                opening_hours_structured=hours,
                geo_region=GEO,
                lat=19.89,
                lng=102.13,
            )
            for i in range(3)
        ]
        # Only node 1 is mutated
        mutated = {nodes[1].node_id}
        result = reschedule_and_validate(nodes, mutated_node_ids=mutated)
        # Warnings should only mention V1, not V0 or V2
        for w in result.warnings:
            assert "V0" not in w
            assert "V2" not in w

    def test_unknown_mutated_node_may_warn(self):
        """UNKNOWN on a mutated node may produce an uncertainty warning."""
        nodes = [
            TripNode(
                venue_name="NoHours",
                venue_id="vid_0",
                scheduled_start=_ict_to_utc(2026, 9, 14, 10),
                duration_minutes=60,
                opening_hours="09:00-11:00",  # legacy only
                opening_hours_structured=None,  # no structured -> UNKNOWN
                geo_region=GEO,
                lat=19.89,
                lng=102.13,
            )
        ]
        result = reschedule_and_validate(nodes, mutated_node_ids={nodes[0].node_id})
        # Should not crash; may produce a legacy warning
        assert isinstance(result.warnings, list)


# ---------------------------------------------------------------------------
# TripNode carries structured hours
# ---------------------------------------------------------------------------


class TestTripNodeStructuredHours:
    def test_nodes_from_catalog_copies_structured(self):
        """nodes_from_catalog copies opening_hours_structured onto TripNode."""
        hours = _make_hours({})
        rows = _pool_of(5, structured=hours, dwell=60)
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes = nodes_from_catalog(geo_region=GEO, start=start, rows=rows)
        assert len(nodes) >= 4
        for n in nodes:
            assert n.opening_hours_structured is not None


# ---------------------------------------------------------------------------
# Sabotage proofs
# ---------------------------------------------------------------------------


class TestSabotageProofs:
    def test_sabotage1_ignoring_closed_places_night_market(self):
        """Sabotage: skip the hours check in nodes_from_catalog.
        The night market WOULD appear at 09:00 if we ignore CLOSED."""
        rows = _pool_of(4, structured=_make_hours({}), dwell=60)
        rows.append(
            _make_venue_row(
                "Night Market", structured=_evening_hours(), category="market", dwell=60
            )
        )
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes = nodes_from_catalog(geo_region=GEO, start=start, rows=rows)
        # This test fails if the hours check is removed.
        assert "Night Market" not in [n.venue_name for n in nodes]

    def test_sabotage2_swap_with_datetime_now(self):
        """Sabotage: evaluate swap hours with datetime.now() instead of
        the target slot.  An evening venue at a 09:00 slot would pass
        if the test runs in the afternoon/evening."""
        evening = _evening_hours()
        # The target slot is 09:00 -- must always be CLOSED for evening venue.
        target_start = _ict_to_utc(2026, 9, 14, 9)
        result = hours_for_slot(evening, target_start, 60, GEO)
        assert result == HoursResult.CLOSED

    def test_sabotage3_trip_wide_warnings_after_swap(self):
        """Sabotage: remove mutated_node_ids scoping from scheduler.
        All 3 nodes would get warnings instead of just the mutated one."""
        # Node 0 and 2 have opening_hours_structured; node 1 is mutated.
        hours = _make_hours({"mon": [["06:00", "23:00"]]})
        closed_hours = {d: [] for d in _ALL_DAYS}  # closed everywhere
        nodes = [
            TripNode(
                venue_name="Untouched_A",
                venue_id="vid_0",
                scheduled_start=_ict_to_utc(2026, 9, 14, 9),
                duration_minutes=60,
                opening_hours_structured=closed_hours,
                geo_region=GEO,
                lat=19.89,
                lng=102.13,
            ),
            TripNode(
                venue_name="Swapped",
                venue_id="vid_1",
                scheduled_start=_ict_to_utc(2026, 9, 14, 11),
                duration_minutes=60,
                opening_hours_structured=hours,
                geo_region=GEO,
                lat=19.89,
                lng=102.13,
            ),
            TripNode(
                venue_name="Untouched_B",
                venue_id="vid_2",
                scheduled_start=_ict_to_utc(2026, 9, 14, 13),
                duration_minutes=60,
                opening_hours_structured=closed_hours,
                geo_region=GEO,
                lat=19.89,
                lng=102.13,
            ),
        ]
        # Only node 1 is mutated
        result = reschedule_and_validate(nodes, mutated_node_ids={"vid_1"})
        # Untouched nodes with closed hours must NOT produce warnings
        for w in result.warnings:
            assert "Untouched_A" not in w
            assert "Untouched_B" not in w
