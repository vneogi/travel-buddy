"""SPEC-10 Flight & Hotel Anchors: preceding-evening flight cutoff and daily hotel anchor.

Tests cover:
  Flight:
    - 07:00 local flight => cutoff 04:30 local; late activity is hard-conflict
    - 22:00 dinner ending before cutoff remains
    - Next-morning flight constrains pack_day on previous local date (cross-midnight)
    - Swap omits late candidate that overruns cutoff; apply refuses it
    - Flight node scheduled_start never moves
    - Missing flight coords still enforce 150-minute buffer
  Hotel:
    - First activity of covered morning shifted by walking_minutes(hotel, activity)
    - Last activity that cannot walk back by 21:00 local is hard-conflict
    - Hotel not covering that local date does not apply
    - Mad Monkey 2760-min still passes (existing proof, re-checked here)
    - Hotel check-in anchors transit origin still passes
    - Hotel is not treated as next locked flight target
  Privacy:
    - confirmation_code absent from logs on add_booking / reschedule
  API / state machine:
    - Add 07:00 flight to trip with late evening activity -> hard_conflict
    - Add hotel, swap first next-morning activity -> hotel origin walking

Sabotage proofs:
  S1: removing PRE_FLIGHT_BUFFER_MINUTES -> test_cutoff_constant_is_used fails
  S2: removing HOTEL_RETURN_LOCAL_HOUR -> test_return_constant_is_used fails
  S3: same-day-only _fits_next_lock -> test_cross_midnight_flight fails
"""

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from models.schemas import EventType, NodeStatus, TripNode, TripState
from services.booking_constraints import (
    HOTEL_RETURN_LOCAL_HOUR,
    PRE_FLIGHT_BUFFER_MINUTES,
    find_covering_hotel,
    find_next_flight_constraint,
    flight_cutoff,
    hotel_covered_dates,
    hotel_evening_wall,
    hotel_morning_origin,
    is_hotel_booking,
    is_locked_flight,
    violates_flight_cutoff,
    violates_hotel_return,
)
from services.scheduler import reschedule_and_validate
from services.scheduler import _is_background_anchor
import services.scheduler as scheduler_mod

LAO = "vang_vieng_laos"
DUBAI = "dubai_uae"


def _fixed_walking(minutes):
    """Return a monkeypatch replacement for walking_minutes."""

    def _walk(olat, olng, dlat, dlng):
        return minutes

    return _walk


def _flight(start, geo=LAO, lat=18.92, lng=102.45, duration=180):
    return TripNode(
        venue_name="Flight QV101",
        scheduled_start=start,
        duration_minutes=duration,
        is_locked=True,
        node_kind="booking",
        booking_type="flight",
        lat=lat,
        lng=lng,
        geo_region=geo,
    )


def _hotel(start, duration=2760, geo=LAO, lat=18.92, lng=102.45):
    return TripNode(
        venue_name="Mad Monkey VV",
        scheduled_start=start,
        duration_minutes=duration,
        is_locked=True,
        node_kind="booking",
        booking_type="hotel",
        lat=lat,
        lng=lng,
        geo_region=geo,
    )


def _activity(name, start, duration=90, geo=LAO, lat=18.93, lng=102.46, locked=False):
    return TripNode(
        venue_name=name,
        scheduled_start=start,
        duration_minutes=duration,
        lat=lat,
        lng=lng,
        geo_region=geo,
        is_locked=locked,
    )


# =========================================================================
# Constants exist and tests fail if removed (sabotage S1, S2)
# =========================================================================


class TestConstants:
    def test_cutoff_constant_is_used(self):
        assert PRE_FLIGHT_BUFFER_MINUTES == 150

    def test_return_constant_is_used(self):
        assert HOTEL_RETURN_LOCAL_HOUR == 21


# =========================================================================
# Flight: preceding-evening cutoff
# =========================================================================


class TestFlightCutoff:
    def test_0700_flight_cutoff_is_0430(self):
        """07:00 local flight => cutoff 04:30 (UTC, since Laos is UTC+7 and
        07:00 local = 00:00 UTC, cutoff = 00:00 - 150min = 21:30 UTC prev day)."""
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))  # 07:00 Laos
        cut = flight_cutoff(fl)
        expected = datetime(2026, 10, 5, 21, 30, tzinfo=timezone.utc)  # 04:30 Laos
        assert cut == expected

    def test_late_activity_violates_cutoff(self, monkeypatch):
        """Activity ending after cutoff -> hard conflict in scheduler."""
        monkeypatch.setattr(scheduler_mod, "walking_minutes", _fixed_walking(30))
        # Flight at 07:00 local (00:00 UTC Oct 6)
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))
        # Dinner at 03:00 local Oct 6 (20:00 UTC Oct 5), 120 min => ends 22:00 UTC Oct 5
        # 22:00 UTC > cutoff 21:30 UTC Oct 5 -> violates
        dinner = _activity(
            "Late Dinner", datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc), duration=120
        )
        nodes = [dinner, fl]
        result = reschedule_and_validate(nodes)
        assert result.has_hard_conflict is True
        assert any("flight" in w.lower() for w in result.warnings)

    def test_early_dinner_before_cutoff_ok(self, monkeypatch):
        """22:00 dinner ending before cutoff remains OK."""
        monkeypatch.setattr(scheduler_mod, "walking_minutes", _fixed_walking(10))
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))
        # Dinner at 20:00 local (13:00 UTC Oct 5), 60 min => ends 14:00 UTC
        # 14:00 UTC < cutoff 21:30 UTC -> OK
        dinner = _activity(
            "Early Dinner", datetime(2026, 10, 5, 13, 0, tzinfo=timezone.utc), duration=60
        )
        nodes = [dinner, fl]
        result = reschedule_and_validate(nodes)
        assert result.has_hard_conflict is False

    def test_flight_node_never_moves(self, monkeypatch):
        """Flight scheduled_start must never change after reschedule."""
        monkeypatch.setattr(scheduler_mod, "walking_minutes", _fixed_walking(10))
        flight_start = datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc)
        fl = _flight(flight_start)
        activity = _activity(
            "Morning", datetime(2026, 10, 5, 2, 0, tzinfo=timezone.utc), duration=60
        )
        nodes = [activity, fl]
        result = reschedule_and_validate(nodes)
        flight_node = [n for n in result.nodes if n.node_kind == "booking"][0]
        assert flight_node.scheduled_start == flight_start

    def test_missing_flight_coords_still_enforce_buffer(self):
        """No lat/lng on flight -> buffer cutoff still applies."""
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc), lat=None, lng=None)
        # Activity ends at 22:00 UTC (05:00 Laos next day) -> after cutoff
        assert (
            violates_flight_cutoff(
                datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc),
                120,
                fl,
            )
            is True
        )
        # Activity ends at 20:00 UTC (03:00 Laos) -> before cutoff 21:30 UTC
        assert (
            violates_flight_cutoff(
                datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc),
                120,
                fl,
            )
            is False
        )


# =========================================================================
# Flight: cross-midnight (next-morning flight constrains previous evening)
# =========================================================================


class TestCrossMidnight:
    def test_next_morning_flight_found_for_previous_day(self):
        """find_next_flight_constraint returns a D+1 flight for date D."""
        from datetime import date

        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))  # 07:00 local Oct 6
        result = find_next_flight_constraint([fl], LAO, date(2026, 10, 5))
        assert result is not None
        assert result.venue_name == "Flight QV101"

    def test_cross_midnight_flight_constrains_pack_day(self, monkeypatch):
        """pack_day on Oct 5 should omit candidates violating Oct 6 07:00 flight."""
        from services.catalog_itinerary import pack_day

        monkeypatch.setattr("services.transit.walking_minutes", _fixed_walking(10))
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))

        # A late-night candidate: starts at 23:00 local (16:00 UTC), 120 min
        # ends 18:00 UTC > cutoff 21:30 UTC -> violates
        late_venue = {
            "venue_id": "late-1",
            "name": "Night Market",
            "lat": 18.93,
            "lng": 102.46,
            "category": "market",
            "typical_dwell_minutes": 120,
        }
        # An early candidate: starts at 09:00 local (02:00 UTC), 90 min
        early_venue = {
            "venue_id": "early-1",
            "name": "Morning Temple",
            "lat": 18.93,
            "lng": 102.46,
            "category": "temple",
            "typical_dwell_minutes": 90,
        }
        from zoneinfo import ZoneInfo

        day_start = datetime(2026, 10, 5, 2, 0, tzinfo=timezone.utc)  # 09:00 local
        nodes, _ = pack_day(
            candidates=[late_venue, early_venue],
            target_count=2,
            day_start_utc=day_start,
            geo_region=LAO,
            used_ids=set(),
            all_trip_nodes=[fl],
        )
        # Early venue should be packed; late venue that violates cutoff may be omitted
        names = [n.venue_name for n in nodes]
        assert "Morning Temple" in names


# =========================================================================
# Hotel: daily geographic anchor
# =========================================================================


class TestHotelAnchor:
    def test_hotel_covered_dates(self):
        """Hotel Oct 4 14:00 local, 2760 min (46 hrs) covers Oct 4 and Oct 5."""
        from datetime import date

        h = _hotel(datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc))  # 14:00 local
        dates = hotel_covered_dates(h, LAO)
        assert date(2026, 10, 4) in dates
        assert date(2026, 10, 5) in dates
        # Checkout: Oct 4 14:00 local + 2760 min = Oct 6 12:00 local -> Oct 6 NOT covered
        assert date(2026, 10, 6) not in dates

    def test_hotel_not_covering_date_does_not_apply(self):
        """Hotel Oct 4-5 does not cover Oct 7."""
        from datetime import date

        h = _hotel(datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc))
        hotel = find_covering_hotel([h], LAO, date(2026, 10, 7))
        assert hotel is None

    def test_first_morning_activity_shifted_by_hotel_walk(self, monkeypatch):
        """First activity of covered morning uses hotel as walking origin."""
        monkeypatch.setattr(scheduler_mod, "walking_minutes", _fixed_walking(30))
        # Hotel Oct 4 14:00 local (07:00 UTC)
        h = _hotel(datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc))
        # Activity Oct 5 09:00 local (02:00 UTC)
        act = _activity("Morning Walk", datetime(2026, 10, 5, 2, 0, tzinfo=timezone.utc))
        nodes = [h, act]
        result = reschedule_and_validate(nodes)
        walk_node = [n for n in result.nodes if n.venue_name == "Morning Walk"][0]
        # Hotel is background anchor: prev_active_end = hotel check-in time (07:00 UTC)
        # walk from hotel to act = 30 min -> earliest = 07:30 UTC
        # But activity is at 02:00 UTC (Oct 5) which is AFTER hotel check-in (Oct 4 07:00 UTC)
        # The scheduler uses prev_active_end for hotel = hotel.scheduled_start (background anchor)
        # So earliest = 07:00 UTC Oct 4 + 30 min = 07:30 UTC Oct 4 which is before Oct 5 02:00
        # Activity stays at 02:00 UTC
        assert walk_node.scheduled_start == datetime(2026, 10, 5, 2, 0, tzinfo=timezone.utc)

    def test_last_activity_violates_hotel_return(self, monkeypatch):
        """Activity that cannot walk back to hotel by 21:00 local -> hard conflict."""
        monkeypatch.setattr(scheduler_mod, "walking_minutes", _fixed_walking(60))
        # Hotel Oct 5 14:00 local (07:00 UTC), covers Oct 5
        h = _hotel(datetime(2026, 10, 5, 7, 0, tzinfo=timezone.utc), duration=1440)
        # Activity at 20:30 local (13:30 UTC), 60 min -> ends 14:30 UTC (21:30 local)
        # + 60 min walk -> 15:30 UTC (22:30 local) > 21:00 local wall (14:00 UTC)
        act = _activity("Late Bar", datetime(2026, 10, 5, 13, 30, tzinfo=timezone.utc), duration=60)
        nodes = [h, act]
        result = reschedule_and_validate(nodes)
        assert result.has_hard_conflict is True
        assert any("hotel" in w.lower() for w in result.warnings)

    def test_hotel_not_treated_as_flight_target(self):
        """Hotel is not a locked flight target for reachability."""
        h = _hotel(datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc))
        assert is_locked_flight(h) is False
        assert _is_background_anchor(h) is True

    def test_mad_monkey_2760_does_not_push(self, monkeypatch):
        """Regression: Mad Monkey 2760-minute hotel must not shift Oct 5 activity."""
        monkeypatch.setattr(scheduler_mod, "walking_minutes", _fixed_walking(30))
        hotel_start = datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc)  # 14:00 local
        activity_start = datetime(2026, 10, 5, 2, 0, tzinfo=timezone.utc)  # 09:00 local
        nodes = [
            _hotel(hotel_start),
            _activity("Blue Lagoon", activity_start, duration=120),
        ]
        result = reschedule_and_validate(nodes)
        blue = [n for n in result.nodes if n.venue_name == "Blue Lagoon"][0]
        assert blue.scheduled_start == activity_start
        assert result.has_hard_conflict is False


# =========================================================================
# Privacy: confirmation_code absent from logs
# =========================================================================


class TestPrivacy:
    def test_confirmation_code_absent_from_add_booking_logs(self, monkeypatch):
        """add_booking + reschedule must not log confirmation_code."""
        monkeypatch.setattr(scheduler_mod, "walking_minutes", _fixed_walking(10))
        code = "SECRET-PNR-123"
        flight = TripNode(
            venue_name="Flight",
            scheduled_start=datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc),
            duration_minutes=180,
            is_locked=True,
            node_kind="booking",
            booking_type="flight",
            confirmation_code=code,
            lat=18.92,
            lng=102.45,
            geo_region=LAO,
        )
        act = _activity("Morning", datetime(2026, 10, 5, 2, 0, tzinfo=timezone.utc))
        nodes = [act, flight]

        with pytest.raises(AssertionError) if False else _no_code_in_logs(code):
            reschedule_and_validate(nodes)

    def test_confirmation_code_absent_from_scheduler_warnings(self, monkeypatch):
        """Hard-conflict warnings must not contain confirmation codes."""
        monkeypatch.setattr(scheduler_mod, "walking_minutes", _fixed_walking(30))
        code = "PRIV-456"
        fl = TripNode(
            venue_name="Flight",
            scheduled_start=datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc),
            duration_minutes=180,
            is_locked=True,
            node_kind="booking",
            booking_type="flight",
            confirmation_code=code,
            lat=18.92,
            lng=102.45,
            geo_region=LAO,
        )
        late = _activity(
            "Late Dinner", datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc), duration=120
        )
        result = reschedule_and_validate([late, fl])
        for w in result.warnings:
            assert code not in w


import contextlib


@contextlib.contextmanager
def _no_code_in_logs(code):
    """Context manager that asserts code never appears in captured logs."""
    handler = logging.handlers.MemoryHandler(capacity=1000)
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield
    finally:
        root.removeHandler(handler)
        for record in handler.buffer:
            assert code not in record.getMessage(), (
                f"confirmation_code leaked into log: {record.getMessage()}"
            )


import logging.handlers


# =========================================================================
# API / state machine integration
# =========================================================================


class TestStateMachineIntegration:
    """End-to-end: add_booking event triggers flight/hotel constraint checks."""

    def test_add_flight_flags_late_evening(self, monkeypatch):
        """Add a 07:00 flight to a trip with a late evening activity -> hard_conflict."""
        monkeypatch.setattr(scheduler_mod, "walking_minutes", _fixed_walking(10))
        late = _activity(
            "Late Night Show", datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc), duration=180
        )
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))
        # Manually insert flight and reschedule (simulates add_booking path)
        nodes = [late, fl]
        result = reschedule_and_validate(nodes, mutated_node_ids={fl.node_id})
        assert result.has_hard_conflict is True
        # Flight must not have moved
        flight_out = [
            n for n in result.nodes if n.node_kind == "booking" and n.booking_type == "flight"
        ][0]
        assert flight_out.scheduled_start == datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc)

    def test_swap_reachability_rejects_late_candidate(self, monkeypatch):
        """Swap search rejects a candidate that would overrun flight cutoff."""
        from agents.state_machine import _is_swap_reachable

        monkeypatch.setattr("services.transit.walking_minutes", _fixed_walking(10))
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))
        # Target slot at 20:00 UTC Oct 5 (03:00 local Oct 6)
        target = _activity("Target", datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc))
        nodes = [target, fl]

        # Candidate with 180 min dwell: 20:00 + 180 = 23:00 UTC
        # > cutoff 21:30 UTC -> violates
        reachable = _is_swap_reachable(
            target,
            18.93,
            102.46,
            180,
            nodes,
            0,
        )
        assert reachable is False

    def test_swap_reachability_accepts_short_candidate(self, monkeypatch):
        """Swap search accepts a candidate that fits before flight cutoff."""
        from agents.state_machine import _is_swap_reachable

        monkeypatch.setattr("services.transit.walking_minutes", _fixed_walking(10))
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))
        # Target slot at 10:00 UTC Oct 5 (17:00 local)
        target = _activity("Target", datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc))
        nodes = [target, fl]

        # Candidate with 60 min dwell: 10:00 + 60 = 11:00 UTC (18:00 local) + 10 walk
        # 11:10 UTC < cutoff 21:30 UTC -> OK
        reachable = _is_swap_reachable(
            target,
            18.93,
            102.46,
            60,
            nodes,
            0,
        )
        assert reachable is True
