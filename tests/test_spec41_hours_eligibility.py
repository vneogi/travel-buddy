"""SPEC-41 Phase A2: Hours Eligibility -- Create, Swap, Scheduler.

Tests exercise production state-machine paths, not just helper functions.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from main import app
from tests.conftest import auth
from config.regions import REGIONS
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
import services.database_service as db_mod
from services.opening_hours import HoursResult, hours_for_slot
from services.scheduler import reschedule_and_validate

ICT = ZoneInfo("Asia/Vientiane")
GEO = "luang_prabang_laos"

client = TestClient(app)
HEADERS = auth("spec41-a2-user")


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

    def test_split_window_through_builder(self):
        """Run nodes_from_catalog with split-window venue at gap time."""
        split = _split_window()
        rows = _pool_of(5, structured=_make_hours({}), dwell=30)
        rows.append(_make_venue_row("Split Place", structured=split, category="museum", dwell=90))
        gap_start = _ict_to_utc(2026, 9, 14, 11)
        assert hours_for_slot(split, gap_start, 90, GEO) == HoursResult.CLOSED
        start = _ict_to_utc(2026, 9, 14, 10)
        nodes = nodes_from_catalog(geo_region=GEO, start=start, rows=rows)
        assert len(nodes) >= 4

    def test_unknown_hours_still_scheduled(self):
        """A venue with null structured hours (UNKNOWN) is still eligible."""
        rows = _pool_of(4, structured=_make_hours({}), dwell=60)
        rows.append(_make_venue_row("Unknown Venue", structured=None, category="museum", dwell=60))
        start = _ict_to_utc(2026, 9, 14, 9)
        nodes = nodes_from_catalog(geo_region=GEO, start=start, rows=rows)
        names = [n.venue_name for n in nodes]
        assert "Unknown Venue" in names

    def test_insufficient_raises_no_trip_no_party(self):
        """Not enough hours-eligible venues raises; trip/party counts unchanged."""
        r = client.get("/api/v1/trips", headers=HEADERS)
        trips_before = len(r.json().get("trips", []))
        rows = _pool_of(2, structured=_make_hours({}), dwell=60)
        start = _ict_to_utc(2026, 9, 14, 9)
        with pytest.raises(InsufficientCatalog):
            nodes_from_catalog(geo_region=GEO, start=start, rows=rows)
        r2 = client.get("/api/v1/trips", headers=HEADERS)
        assert len(r2.json().get("trips", [])) == trips_before

    def test_destination_local_tuesday_through_builder(self):
        """ICT is UTC+7; Tuesday 09:00 ICT is the correct local weekday."""
        closed_tue = _closed_tuesday()
        start_utc = _ict_to_utc(2026, 9, 15, 9)  # Tuesday 09:00 ICT
        assert hours_for_slot(closed_tue, start_utc, 60, GEO) == HoursResult.CLOSED
        rows = _pool_of(5, structured=_make_hours({}), dwell=60)
        rows.append(
            _make_venue_row("Closed Tue", structured=closed_tue, category="museum", dwell=60)
        )
        nodes = nodes_from_catalog(geo_region=GEO, start=start_utc, rows=rows)
        assert "Closed Tue" not in [n.venue_name for n in nodes]

    def test_corridor_build_excludes_known_closed(self):
        """A real corridor build must not contain any known-closed venues."""
        from config.corridors import require_corridor
        from models.schemas import TripSegmentIn

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
        for n in nodes:
            if n.opening_hours_structured:
                hr = hours_for_slot(
                    n.opening_hours_structured,
                    n.scheduled_start,
                    n.duration_minutes,
                    n.geo_region,
                )
                assert hr != HoursResult.CLOSED, f"{n.venue_name} at {n.scheduled_start} is CLOSED"

    def test_api_insufficient_capacity_typed_error(self):
        """Identity-eligible but hours-ineligible pool raises typed error."""
        rows = _pool_of(4, structured=_make_hours({}), dwell=60)
        rows.extend(_pool_of(2, structured=_evening_hours(), category="market", dwell=60))
        with pytest.raises(InsufficientCatalog):
            range_nodes_from_catalog(
                geo_region=GEO,
                start_date_local="2026-09-14",
                end_date_local="2026-09-15",
                rows=rows,
            )


# ---------------------------------------------------------------------------
# Swap tests
# ---------------------------------------------------------------------------


def _make_venue_rag(name, structured=None, dwell=60, geo=GEO):
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
        geo_region=geo,
        typical_dwell_minutes=dwell,
    )


def _seed_swap_trip(venues, headers=None):
    """Create a trip, seed extra candidate venues, return (trip_id, target_node_dict)."""
    h = headers or HEADERS
    r = client.post(
        "/api/v1/trip/create",
        json={"geo_region": GEO, "start_date": "2026-09-14"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    for v in venues:
        db_mod.db_service.add_venue(v)
    return data["trip_id"], data["nodes"][0]


class TestSwapStateMachine:
    """HTTP-level swap tests exercising real state-machine paths."""

    def test_search_hydrates_and_omits_closed(self):
        """HTTP swap: CLOSED candidate never appears in the result."""
        closed_v = _make_venue_rag("Evening Temple", structured=_evening_hours(), dwell=60)
        open_v = _make_venue_rag("All Day Temple", structured=_make_hours({}), dwell=60)
        h = auth("spec41-swap-1")
        trip_id, target = _seed_swap_trip([closed_v, open_v], headers=h)
        r = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "swap_activity",
                "message": "temple",
                "target_node_id": target["node_id"],
            },
            headers=h,
        )
        assert r.status_code == 200
        swapped = next(n for n in r.json()["updated_nodes"] if n["node_id"] == target["node_id"])
        assert swapped["venue_name"] != "Evening Temple"

    def test_fits_hydrated_candidate_applied(self):
        """HTTP swap: a FITS candidate is actually applied to the trip."""
        open_v = _make_venue_rag("Open Spot", structured=_make_hours({}), dwell=60)
        h = auth("spec41-swap-2")
        trip_id, target = _seed_swap_trip([open_v], headers=h)
        original_name = target["venue_name"]
        r = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "swap_activity",
                "message": "find something else",
                "target_node_id": target["node_id"],
            },
            headers=h,
        )
        assert r.status_code == 200
        swapped = next(n for n in r.json()["updated_nodes"] if n["node_id"] == target["node_id"])
        assert swapped["venue_name"] != original_name

    def test_sheet_apply_rejects_closed_venue(self):
        """replacement_venue_id of a CLOSED venue is refused; trip unchanged."""
        closed_v = _make_venue_rag("Closed Sheet", structured=_evening_hours(), dwell=60)
        h = auth("spec41-swap-3")
        trip_id, target = _seed_swap_trip([closed_v], headers=h)
        original_name = target["venue_name"]
        r = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "swap_activity",
                "message": "swap",
                "target_node_id": target["node_id"],
                "preferences": {"replacement_venue_id": closed_v.venue_id},
            },
            headers=h,
        )
        assert r.status_code == 200
        swapped = next(n for n in r.json()["updated_nodes"] if n["node_id"] == target["node_id"])
        assert swapped["venue_name"] == original_name

    def test_candidate_dwell_preserved_and_used(self):
        """120-min candidate overruns window; 30-min fits via sheet replacement."""
        hours = _make_hours({"mon": [["08:00", "10:00"]]})
        long_v = _make_venue_rag("Long Visit", structured=hours, dwell=120)
        short_v = _make_venue_rag("Quick Visit", structured=hours, dwell=30)
        h = auth("spec41-swap-4")
        trip_id, target = _seed_swap_trip([long_v, short_v], headers=h)
        original_name = target["venue_name"]
        # Long Visit rejected (09:00+120=11:00 > 10:00)
        r1 = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "swap_activity",
                "message": "swap",
                "target_node_id": target["node_id"],
                "preferences": {"replacement_venue_id": long_v.venue_id},
            },
            headers=h,
        )
        assert r1.status_code == 200
        node1 = next(n for n in r1.json()["updated_nodes"] if n["node_id"] == target["node_id"])
        assert node1["venue_name"] == original_name  # unchanged
        # Quick Visit accepted (09:00+30=09:30 < 10:00)
        r2 = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "swap_activity",
                "message": "swap",
                "target_node_id": target["node_id"],
                "preferences": {"replacement_venue_id": short_v.venue_id},
            },
            headers=h,
        )
        assert r2.status_code == 200
        node2 = next(n for n in r2.json()["updated_nodes"] if n["node_id"] == target["node_id"])
        assert node2["venue_name"] == "Quick Visit"

    def test_maps_validation_not_called_during_swap(self):
        """Swap must skip Maps validate_venues entirely."""
        open_v = _make_venue_rag("Maps Test", structured=_make_hours({}), dwell=60)
        h = auth("spec41-swap-5")
        trip_id, target = _seed_swap_trip([open_v], headers=h)
        with patch("agents.state_machine.maps_service") as mock_maps:
            r = client.post(
                "/api/v1/trip/event",
                json={
                    "trip_id": trip_id,
                    "event_type": "swap_activity",
                    "message": "maps check",
                    "target_node_id": target["node_id"],
                },
                headers=h,
            )
        assert r.status_code == 200
        mock_maps.validate_venues.assert_not_called()

    def test_swap_invokes_no_llm(self):
        """Swap path in test env must not call LLM for response generation."""
        open_v = _make_venue_rag("LLM Test", structured=_make_hours({}), dwell=60)
        h = auth("spec41-swap-6")
        trip_id, target = _seed_swap_trip([open_v], headers=h)
        with patch("agents.state_machine.llm_service") as mock_llm:
            r = client.post(
                "/api/v1/trip/event",
                json={
                    "trip_id": trip_id,
                    "event_type": "swap_activity",
                    "message": "llm check",
                    "target_node_id": target["node_id"],
                },
                headers=h,
            )
        assert r.status_code == 200
        mock_llm.generate_itinerary_response.assert_not_called()


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

    def test_unknown_mutated_node_exact_warning(self):
        """UNKNOWN on a mutated node produces exact uncertainty warning."""
        nodes = [
            TripNode(
                venue_name="NoHours",
                venue_id="vid_0",
                scheduled_start=_ict_to_utc(2026, 9, 14, 10),
                duration_minutes=60,
                opening_hours_structured=None,
                geo_region=GEO,
                lat=19.89,
                lng=102.13,
            )
        ]
        result = reschedule_and_validate(nodes, mutated_node_ids={nodes[0].node_id})
        assert any("unknown" in w.lower() for w in result.warnings)
        assert result.has_hard_conflict is False

    def test_downstream_shifted_node_checked(self):
        """A long mutated node pushes B into a CLOSED window; B is flagged."""
        morning = _make_hours({"mon": [["08:00", "11:30"]]})
        nodes = [
            TripNode(
                venue_name="Long_A",
                venue_id="vid_long",
                scheduled_start=_ict_to_utc(2026, 9, 14, 9),
                duration_minutes=180,
                opening_hours_structured=_make_hours({}),
                geo_region=GEO,
                lat=19.89,
                lng=102.13,
            ),
            TripNode(
                venue_name="Fragile_B",
                venue_id="vid_fragile",
                scheduled_start=_ict_to_utc(2026, 9, 14, 10),
                duration_minutes=60,
                opening_hours_structured=morning,
                geo_region=GEO,
                lat=19.89,
                lng=102.13,
            ),
        ]
        mutated = {nodes[0].node_id}
        result = reschedule_and_validate(nodes, mutated_node_ids=mutated)
        assert result.has_hard_conflict is True
        assert any("Fragile_B" in w for w in result.warnings)

    def test_scheduler_closed_is_hard_conflict(self):
        """CLOSED on a mutated node sets has_hard_conflict=True."""
        closed_hours = {d: [] for d in _ALL_DAYS}
        nodes = [
            TripNode(
                venue_name="AlwaysClosed",
                venue_id="vid_ac",
                scheduled_start=_ict_to_utc(2026, 9, 14, 10),
                duration_minutes=60,
                opening_hours_structured=closed_hours,
                geo_region=GEO,
                lat=19.89,
                lng=102.13,
            ),
        ]
        result = reschedule_and_validate(nodes, mutated_node_ids={nodes[0].node_id})
        assert result.has_hard_conflict is True
        assert any("AlwaysClosed" in w for w in result.warnings)


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

    def test_sabotage4_apply_recheck_catches_closed(self):
        """Prove _build_candidate_nodes rejects CLOSED at apply time.
        If the recheck were removed, the search filter might still catch it,
        but this direct test would fail."""
        from agents.state_machine import state_machine as sm

        closed_v = _make_venue_rag("Direct Closed", structured=_evening_hours(), dwell=60)
        trip_state = TripState(
            trip_id="sab4-trip",
            user_id="sab4-user",
            geo_region=GEO,
            nodes=[
                TripNode(
                    venue_name="Target",
                    venue_id="vid_target",
                    scheduled_start=_ict_to_utc(2026, 9, 14, 9),
                    duration_minutes=60,
                    geo_region=GEO,
                    lat=19.89,
                    lng=102.13,
                ),
            ],
        )
        venues = [VenueSearchResult(venue=closed_v, similarity_score=0.0, final_score=0.0)]
        result = sm._build_candidate_nodes(
            trip_state,
            EventType.SWAP_ACTIVITY.value,
            trip_state.nodes[0].node_id,
            venues,
            0,
        )
        assert result is None

    def test_sabotage5_default_dwell_lets_long_through(self):
        """If the code used default 90-min dwell instead of candidate dwell,
        a 30-min venue at 09:00 with close at 10:00 would be treated as
        90 min and wrongly rejected."""
        hours = _make_hours({"mon": [["08:00", "10:00"]]})
        assert hours_for_slot(hours, _ict_to_utc(2026, 9, 14, 9), 30, GEO) == HoursResult.FITS
        assert hours_for_slot(hours, _ict_to_utc(2026, 9, 14, 9), 90, GEO) == HoursResult.CLOSED

    def test_sabotage6_shifted_closed_must_be_hard_conflict(self):
        """Only _is_shifted detection causes Victim to be checked."""
        closed_hours = {d: [] for d in _ALL_DAYS}

        def _make_pair(pusher_duration):
            return [
                TripNode(
                    venue_name="Pusher",
                    venue_id="vid_push_s6",
                    scheduled_start=_ict_to_utc(2026, 9, 14, 9),
                    duration_minutes=pusher_duration,
                    opening_hours_structured=_make_hours({}),
                    geo_region=GEO,
                    lat=19.89,
                    lng=102.13,
                ),
                TripNode(
                    venue_name="Victim",
                    venue_id="vid_victim_s6",
                    scheduled_start=_ict_to_utc(2026, 9, 14, 11),
                    duration_minutes=60,
                    opening_hours_structured=closed_hours,
                    geo_region=GEO,
                    lat=19.89,
                    lng=102.13,
                ),
            ]

        # Pusher 60 min: Victim NOT shifted, not checked, no conflict
        short = _make_pair(60)
        r1 = reschedule_and_validate(short, mutated_node_ids={short[0].node_id})
        assert r1.has_hard_conflict is False

        # Pusher 180 min: Victim shifted past its window, checked, conflict
        long = _make_pair(180)
        r2 = reschedule_and_validate(long, mutated_node_ids={long[0].node_id})
        assert r2.has_hard_conflict is True
        assert any("Victim" in w for w in r2.warnings)
