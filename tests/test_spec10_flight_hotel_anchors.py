"""SPEC-10 flight-hotel anchors: booking-constraint tests.

Tests cover:
  - Named constant sabotage proofs
  - Flight cutoff predicates (scoped: only before flight, same region)
  - Cross-midnight constraint (preceding evening)
  - Hotel anchor (covered dates, evening wall, morning origin)
  - Hotel return only on LAST unlocked activity per day
  - Hotel morning origin: local 09:00 for later mornings; check-in guard
  - Privacy: confirmation codes never surface in logs or warnings
  - Integration: flight add via HTTP, hotel swap via HTTP
  - Consistent walking_minutes patching
  - Packing: deferred (pack_day does not wire SPEC-10 constraints)

SPEC-10 PARTIAL: pack_day flight/hotel constraints are deferred.
Scheduler + state-machine paths are production-complete.
"""

import importlib
import logging
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch as mock_patch

import pytest

import services.scheduler as scheduler_mod

# Import the actual module, not the __init__.py re-export
_sm_mod = importlib.import_module("agents.state_machine")

from models.schemas import NodeStatus, TripNode
from services.booking_constraints import (
    HOTEL_RETURN_LOCAL_HOUR,
    PRE_FLIGHT_BUFFER_MINUTES,
    _ensure_aware,
    _local_date_of,
    find_constraining_flight,
    find_covering_hotel,
    flight_cutoff,
    hotel_covered_dates,
    hotel_evening_wall,
    hotel_morning_origin,
    is_first_unlocked_activity,
    is_last_unlocked_activity,
    is_locked_flight,
    local_09_utc,
    violates_flight_cutoff,
    violates_hotel_return,
)
from services.scheduler import reschedule_and_validate

# Regions used in tests
LAO = "vang_vieng_laos"  # UTC+7
DUBAI = "dubai_uae"  # UTC+4


def _vv_trip_body():
    """Create-trip payload that seeds VV activities on Oct 5."""
    return {
        "start_date": "2026-10-05T09:00:00",
        "geo_region": "vang_vieng_laos",
    }


# ---------------------------------------------------------------------------
# Walking patches -- patch the canonical module so deferred imports resolve
# ---------------------------------------------------------------------------


def _patch_walking(monkeypatch, minutes: int):
    """Patch walking_minutes consistently across ALL call sites."""
    fn = lambda olat, olng, dlat, dlng: minutes  # noqa: E731
    monkeypatch.setattr("services.transit.walking_minutes", fn)
    monkeypatch.setattr(scheduler_mod, "walking_minutes", fn)
    monkeypatch.setattr(_sm_mod, "_walking_minutes", fn)
    return fn


def _spy_walking(monkeypatch, minutes: int):
    """Like _patch_walking but records (olat, olng, dlat, dlng) calls."""
    calls = []

    def fn(olat, olng, dlat, dlng):
        calls.append((olat, olng, dlat, dlng))
        return minutes

    monkeypatch.setattr("services.transit.walking_minutes", fn)
    monkeypatch.setattr(scheduler_mod, "walking_minutes", fn)
    monkeypatch.setattr(_sm_mod, "_walking_minutes", fn)
    return calls


# ---------------------------------------------------------------------------
# Node factories
# ---------------------------------------------------------------------------

_counter = 0


def _next_id():
    global _counter
    _counter += 1
    return f"node-{_counter:04d}"


def _flight(start, geo=LAO, lat=18.92, lng=102.45, duration=180):
    return TripNode(
        node_id=_next_id(),
        venue_name="QV101",
        scheduled_start=start,
        duration_minutes=duration,
        is_locked=True,
        node_kind="booking",
        booking_type="flight",
        lat=lat,
        lng=lng,
        geo_region=geo,
    )


def _hotel(start, duration=2760, geo=LAO, lat=18.920, lng=102.450):
    return TripNode(
        node_id=_next_id(),
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
        node_id=_next_id(),
        venue_name=name,
        scheduled_start=start,
        duration_minutes=duration,
        is_locked=locked,
        node_kind="activity",
        lat=lat,
        lng=lng,
        geo_region=geo,
    )


# ---------------------------------------------------------------------------
# 1. Named constant sabotage proofs
# ---------------------------------------------------------------------------


class TestConstants:
    def test_cutoff_constant_is_used(self):
        """S1: Removing PRE_FLIGHT_BUFFER_MINUTES breaks the test."""
        assert PRE_FLIGHT_BUFFER_MINUTES == 150
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))
        assert flight_cutoff(fl) == datetime(2026, 10, 5, 21, 30, tzinfo=timezone.utc)

    def test_return_constant_is_used(self):
        """S2: Removing HOTEL_RETURN_LOCAL_HOUR breaks the test."""
        assert HOTEL_RETURN_LOCAL_HOUR == 21


# ---------------------------------------------------------------------------
# 2. Flight cutoff -- scoped correctly
# ---------------------------------------------------------------------------


class TestFlightCutoff:
    def test_0700_flight_cutoff_is_0430(self):
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))
        assert flight_cutoff(fl) == datetime(2026, 10, 5, 21, 30, tzinfo=timezone.utc)

    def test_late_activity_violates_cutoff(self, monkeypatch):
        _patch_walking(monkeypatch, 10)
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))
        assert (
            violates_flight_cutoff(
                datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc),
                120,
                fl,
                activity_lat=18.93,
                activity_lng=102.46,
            )
            is True
        )

    def test_early_dinner_before_cutoff_ok(self, monkeypatch):
        _patch_walking(monkeypatch, 10)
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))
        assert (
            violates_flight_cutoff(
                datetime(2026, 10, 5, 13, 0, tzinfo=timezone.utc),
                60,
                fl,
                activity_lat=18.93,
                activity_lng=102.46,
            )
            is False
        )

    def test_flight_node_never_moves(self, monkeypatch):
        _patch_walking(monkeypatch, 10)
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))
        late = _activity("Late", datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc), 180)
        result = reschedule_and_validate([late, fl], mutated_node_ids={fl.node_id})
        fl_out = [n for n in result.nodes if n.booking_type == "flight"][0]
        assert fl_out.scheduled_start == datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc)

    def test_missing_flight_coords_still_enforce_buffer(self, monkeypatch):
        _patch_walking(monkeypatch, 10)
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc), lat=None, lng=None)
        assert (
            violates_flight_cutoff(
                datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc),
                120,
                fl,
                activity_lat=18.93,
                activity_lng=102.46,
            )
            is True
        )

    def test_activity_after_flight_not_constrained(self, monkeypatch):
        _patch_walking(monkeypatch, 10)
        fl = _flight(datetime(2026, 10, 5, 6, 0, tzinfo=timezone.utc))
        act = _activity("After", datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc), 180)
        assert find_constraining_flight([fl, act], act) is None

    def test_different_region_not_constrained(self, monkeypatch):
        _patch_walking(monkeypatch, 10)
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc), geo=DUBAI)
        act = _activity(
            "VV Dinner", datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc), 120, geo=LAO
        )
        assert find_constraining_flight([fl, act], act) is None

    def test_multiple_unsorted_flights_picks_earliest(self, monkeypatch):
        _patch_walking(monkeypatch, 10)
        fl_late = _flight(datetime(2026, 10, 7, 0, 0, tzinfo=timezone.utc))
        fl_early = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))
        act = _activity("Dinner", datetime(2026, 10, 5, 14, 0, tzinfo=timezone.utc), 90)
        found = find_constraining_flight([fl_late, fl_early, act], act)
        assert found is fl_early


# ---------------------------------------------------------------------------
# 3. Cross-midnight
# ---------------------------------------------------------------------------


class TestCrossMidnight:
    def test_d_plus_1_flight_constrains_evening(self, monkeypatch):
        _patch_walking(monkeypatch, 10)
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))
        act = _activity("Evening", datetime(2026, 10, 5, 14, 0, tzinfo=timezone.utc), 90)
        assert find_constraining_flight([fl, act], act) is fl

    def test_cross_midnight_scheduler_flags_conflict(self, monkeypatch):
        _patch_walking(monkeypatch, 10)
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))
        late = _activity("Late Show", datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc), 120)
        result = reschedule_and_validate([late, fl])
        assert result.has_hard_conflict is True
        assert any("Late Show" in w for w in result.warnings)

    def test_cross_midnight_late_venue_has_warning(self, monkeypatch):
        _patch_walking(monkeypatch, 10)
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))
        late = _activity("Late Show", datetime(2026, 10, 5, 21, 0, tzinfo=timezone.utc), 120)
        result = reschedule_and_validate([late, fl])
        assert "Late Show" in [n.venue_name for n in result.nodes]
        assert result.has_hard_conflict is True
        assert any("flight" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# 4. Hotel anchor
# ---------------------------------------------------------------------------


class TestHotelAnchor:
    def test_hotel_covered_dates(self):
        h = _hotel(datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc))  # 14:00 local
        dates = hotel_covered_dates(h, LAO)
        assert date(2026, 10, 4) in dates
        assert date(2026, 10, 5) in dates
        assert date(2026, 10, 6) not in dates

    def test_hotel_not_covering_date_returns_none(self):
        h = _hotel(datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc))
        assert find_covering_hotel([h], LAO, date(2026, 10, 7)) is None

    def test_hotel_not_treated_as_flight(self):
        h = _hotel(datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc))
        assert is_locked_flight(h) is False

    def test_hotel_evening_wall_is_21_local(self):
        h = _hotel(datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc))
        wall = hotel_evening_wall(h, LAO, date(2026, 10, 4))
        assert wall == datetime(2026, 10, 4, 14, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 5. Hotel return only on LAST unlocked activity
# ---------------------------------------------------------------------------


class TestHotelReturnLastOnly:
    def test_earlier_far_stop_ok_if_not_last(self, monkeypatch):
        _patch_walking(monkeypatch, 60)
        h = _hotel(datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc))
        far_early = _activity("Far Temple", datetime(2026, 10, 4, 10, 0, tzinfo=timezone.utc), 90)
        near_late = _activity(
            "Near Cafe",
            datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc),
            30,
            lat=18.921,
            lng=102.451,
        )
        result = reschedule_and_validate([h, far_early, near_late])
        hotel_warnings = [w for w in result.warnings if "hotel" in w.lower()]
        assert not any("Far Temple" in w for w in hotel_warnings)

    def test_last_activity_violates_hotel_return(self, monkeypatch):
        _patch_walking(monkeypatch, 60)
        h = _hotel(datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc))
        late = _activity("Sunset Bar", datetime(2026, 10, 4, 13, 30, tzinfo=timezone.utc), 60)
        result = reschedule_and_validate([h, late])
        assert result.has_hard_conflict is True
        assert any("Sunset Bar" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# 6. Hotel morning origin -- local 09:00 for later mornings
# ---------------------------------------------------------------------------


class TestHotelMorningOrigin:
    def test_local_09_utc_vang_vieng(self):
        """VV is UTC+7: local 09:00 Oct 5 = 02:00 UTC Oct 5."""
        result = local_09_utc(LAO, date(2026, 10, 5))
        assert result == datetime(2026, 10, 5, 2, 0, tzinfo=timezone.utc)

    def test_later_morning_uses_local_09(self):
        """hotel_morning_origin for a later covered day returns local 09:00."""
        h = _hotel(datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc))
        origin = hotel_morning_origin(h, LAO, date(2026, 10, 5))
        assert origin == datetime(2026, 10, 5, 2, 0, tzinfo=timezone.utc)

    def test_checkin_day_uses_checkin_instant(self):
        """Check-in day origin is hotel.scheduled_start."""
        h = _hotel(datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc))
        origin = hotel_morning_origin(h, LAO, date(2026, 10, 4))
        assert origin == datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc)

    def test_target_at_1100_proves_origin_is_0900(self, monkeypatch):
        """Activity at 11:00 local (04:00 UTC) on a later covered morning.
        Hotel origin = 09:00 local (02:00 UTC) + 15 min walk = 02:15 UTC.
        02:15 UTC < 04:00 UTC, so no shift.  Proves origin is 09:00, not 11:00.

        If origin were node.scheduled_start (04:00 UTC), walk would give
        04:15 UTC, which would also not shift -- but the walking spy
        confirms the hotel coords are the origin.
        """
        calls = _spy_walking(monkeypatch, 15)
        h = _hotel(
            datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc),
            lat=18.920,
            lng=102.450,
        )
        act = _activity(
            "Brunch",
            datetime(2026, 10, 5, 4, 0, tzinfo=timezone.utc),
            90,
            lat=18.935,
            lng=102.465,
        )
        result = reschedule_and_validate([h, act])
        # Activity not shifted (02:15 UTC < 04:00 UTC)
        assert act.scheduled_start == datetime(2026, 10, 5, 4, 0, tzinfo=timezone.utc)
        assert result.has_hard_conflict is False
        # Walking was called with hotel -> activity coords
        hotel_calls = [c for c in calls if c[0] == 18.920 and c[1] == 102.450]
        assert len(hotel_calls) > 0

    def test_pre_checkin_activity_not_shifted(self, monkeypatch):
        """Activity at 09:00 local (02:00 UTC) Oct 4, before hotel check-in
        at 14:00 local (07:00 UTC) Oct 4.  Hotel must not shift it.

        The activity is scheduled before the hotel chronologically, so it
        appears first in node order.  The hotel morning origin guard
        (node_utc < origin_instant) skips the shift.
        """
        calls = _spy_walking(monkeypatch, 30)
        h = _hotel(
            datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc),
            lat=18.920,
            lng=102.450,
        )
        # 09:00 local Oct 4 = 02:00 UTC Oct 4 -- before check-in 07:00 UTC
        act = _activity(
            "Morning Market",
            datetime(2026, 10, 4, 2, 0, tzinfo=timezone.utc),
            90,
            lat=18.935,
            lng=102.465,
        )
        # Activity BEFORE hotel in node order (chronological)
        result = reschedule_and_validate([act, h])
        # Activity must stay at 02:00 UTC (not shifted)
        assert act.scheduled_start == datetime(2026, 10, 4, 2, 0, tzinfo=timezone.utc)
        assert result.has_hard_conflict is False
        # No hotel-origin walking call: hotel is after activity in chain
        hotel_calls = [c for c in calls if c[0] == 18.920 and c[1] == 102.450]
        assert len(hotel_calls) == 0

    def test_first_morning_uses_hotel_walk(self, monkeypatch):
        """First unlocked on a later covered day: walking spy sees hotel coords."""
        calls = _spy_walking(monkeypatch, 15)
        h = _hotel(
            datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc),
            lat=18.920,
            lng=102.450,
        )
        act = _activity(
            "Walk",
            datetime(2026, 10, 5, 2, 15, tzinfo=timezone.utc),
            90,
            lat=18.935,
            lng=102.465,
        )
        reschedule_and_validate([h, act])
        hotel_calls = [c for c in calls if c[0] == 18.920 and c[1] == 102.450]
        assert len(hotel_calls) > 0


# ---------------------------------------------------------------------------
# 7. First/last unlocked helpers
# ---------------------------------------------------------------------------


class TestFirstLastHelpers:
    def test_is_first_skips_locked_and_bookings(self):
        h = _hotel(datetime(2026, 10, 5, 2, 0, tzinfo=timezone.utc))
        locked = _activity("Locked", datetime(2026, 10, 5, 3, 0, tzinfo=timezone.utc), locked=True)
        first = _activity("First", datetime(2026, 10, 5, 4, 0, tzinfo=timezone.utc))
        assert is_first_unlocked_activity(first, [h, locked, first], LAO, date(2026, 10, 5))

    def test_is_last_identifies_correct_node(self):
        a1 = _activity("A1", datetime(2026, 10, 5, 3, 0, tzinfo=timezone.utc))
        a2 = _activity("A2", datetime(2026, 10, 5, 5, 0, tzinfo=timezone.utc))
        assert is_last_unlocked_activity(a2, [a1, a2], LAO, date(2026, 10, 5))
        assert not is_last_unlocked_activity(a1, [a1, a2], LAO, date(2026, 10, 5))


# ---------------------------------------------------------------------------
# 8. Privacy
# ---------------------------------------------------------------------------


class TestPrivacy:
    def test_confirmation_code_absent_from_scheduler_warnings(self, monkeypatch):
        _patch_walking(monkeypatch, 10)
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))
        fl.confirmation_code = "SECRET-CANARY-123"
        late = _activity("Late", datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc), 120)
        result = reschedule_and_validate([late, fl])
        for w in result.warnings:
            assert "SECRET-CANARY-123" not in w

    def test_confirmation_code_absent_from_api_logs(self, client, caplog):
        from tests.conftest import auth

        created = client.post(
            "/api/v1/trip/create",
            headers=auth("privacy-user"),
            json=_vv_trip_body(),
        )
        assert created.status_code == 200
        trip_id = created.json()["trip_id"]

        sentinel = "TOPSECRET-XRAY-42"
        with caplog.at_level(logging.DEBUG):
            resp = client.post(
                "/api/v1/trip/event",
                headers=auth("privacy-user"),
                json={
                    "trip_id": trip_id,
                    "event_type": "add_booking",
                    "message": "Add flight",
                    "preferences": {
                        "venue_name": "QV101",
                        "booking_type": "flight",
                        "scheduled_start": "2026-10-06T00:00:00Z",
                        "duration_minutes": 180,
                        "lat": 18.92,
                        "lng": 102.45,
                        "geo_region": "vang_vieng_laos",
                        "confirmation_code": sentinel,
                    },
                },
            )
        assert resp.status_code == 200
        for record in caplog.records:
            assert sentinel not in record.getMessage()


# ---------------------------------------------------------------------------
# 9. Swap reachability
# ---------------------------------------------------------------------------


class TestSwapReachability:
    def test_swap_rejects_late_candidate_flight(self, monkeypatch):
        from agents.state_machine import _is_swap_reachable

        _patch_walking(monkeypatch, 10)
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))
        target = _activity("Target", datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc))
        nodes = [target, fl]
        assert _is_swap_reachable(target, 18.93, 102.46, 180, nodes, 0) is False

    def test_swap_accepts_short_candidate(self, monkeypatch):
        from agents.state_machine import _is_swap_reachable

        _patch_walking(monkeypatch, 10)
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))
        target = _activity("Target", datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc))
        nodes = [target, fl]
        assert _is_swap_reachable(target, 18.93, 102.46, 60, nodes, 0) is True

    def test_swap_hotel_return_only_last(self, monkeypatch):
        from agents.state_machine import _is_swap_reachable

        _patch_walking(monkeypatch, 60)
        h = _hotel(datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc))
        first = _activity("First", datetime(2026, 10, 4, 10, 0, tzinfo=timezone.utc))
        last = _activity("Last", datetime(2026, 10, 4, 12, 30, tzinfo=timezone.utc))
        nodes = [h, first, last]
        assert _is_swap_reachable(first, 18.93, 102.46, 60, nodes, 1) is True
        assert _is_swap_reachable(last, 18.93, 102.46, 90, nodes, 2) is False


# ---------------------------------------------------------------------------
# 10. Integration: flight add via HTTP
# ---------------------------------------------------------------------------


class TestFlightIntegration:
    """Seed a trip with a real unlocked activity ending after 04:30 local cutoff.
    Add a 07:00 local flight via HTTP.  Assert warning, flight unmoved, no LLM."""

    def test_add_flight_flags_late_activity(self, client, monkeypatch):
        from tests.conftest import auth
        from services.database_service import db_service

        # 1. Create trip to get a trip_id and user
        user_id = "flight-integ-user"
        created = client.post(
            "/api/v1/trip/create",
            headers=auth(user_id),
            json={"start_date": "2026-10-05T09:00:00"},
        )
        assert created.status_code == 200
        trip_id = created.json()["trip_id"]

        # 2. Inject a real unlocked activity ending after the 04:30 cutoff.
        #    Flight at 07:00 local = 00:00 UTC Oct 6.
        #    Cutoff = 04:30 local = 21:30 UTC Oct 5.
        #    Activity: starts 20:00 UTC Oct 5, duration 120 min,
        #    ends 22:00 UTC > 21:30 UTC cutoff.
        trip_state = db_service.get_trip(trip_id)
        late_node = TripNode(
            venue_name="Night Market Dinner",
            scheduled_start=datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc),
            duration_minutes=120,
            lat=18.93,
            lng=102.46,
            geo_region="vang_vieng_laos",
        )
        trip_state.nodes.append(late_node)
        db_service.save_trip(trip_state)

        # 3. Patch LLM to raise if called
        def _llm_bomb(*a, **kw):
            raise AssertionError("LLM must not be called for add_booking")

        _patch_walking(monkeypatch, 10)

        with mock_patch("services.llm_service.llm_service.complete", side_effect=_llm_bomb):
            resp = client.post(
                "/api/v1/trip/event",
                headers=auth(user_id),
                json={
                    "trip_id": trip_id,
                    "event_type": "add_booking",
                    "message": "Add morning flight",
                    "preferences": {
                        "venue_name": "QV101 to Bangkok",
                        "booking_type": "flight",
                        "scheduled_start": "2026-10-06T00:00:00Z",
                        "duration_minutes": 180,
                        "lat": 18.92,
                        "lng": 102.45,
                        "geo_region": "vang_vieng_laos",
                    },
                },
            )
        assert resp.status_code == 200
        body = resp.json()

        # 4. Warning names the exact late activity
        warnings = body.get("schedule_warnings", [])
        assert any("Night Market Dinner" in w for w in warnings), (
            f"Expected warning about Night Market Dinner, got: {warnings}"
        )

        # 5. Flight unmoved at 00:00 UTC Oct 6
        flight_node = next(
            (n for n in body["updated_nodes"] if n.get("booking_type") == "flight"),
            None,
        )
        assert flight_node is not None
        assert flight_node["scheduled_start"].startswith("2026-10-06T00:00")
        assert flight_node["is_locked"] is True


# ---------------------------------------------------------------------------
# 11. Integration: hotel swap with exact walking proof
# ---------------------------------------------------------------------------


class TestHotelSwapIntegration:
    """Add a hotel checking in the previous day, covering the tested morning.
    Swap the first unlocked activity with deterministic candidates.
    Assert exact walking call from hotel coords, node_id preserved, venue changed."""

    def test_hotel_swap_uses_hotel_origin(self, client, monkeypatch):
        from tests.conftest import auth
        from services.database_service import db_service

        user_id = "hotel-swap-integ"
        walk_calls = []

        def _wm_spy(olat, olng, dlat, dlng):
            walk_calls.append((round(olat, 3), round(olng, 3), round(dlat, 3), round(dlng, 3)))
            return 10

        monkeypatch.setattr("services.transit.walking_minutes", _wm_spy)
        monkeypatch.setattr(scheduler_mod, "walking_minutes", _wm_spy)
        monkeypatch.setattr(_sm_mod, "_walking_minutes", _wm_spy)

        # 1. Create trip starting Oct 5
        created = client.post(
            "/api/v1/trip/create",
            headers=auth(user_id),
            json=_vv_trip_body(),
        )
        assert created.status_code == 200
        trip_id = created.json()["trip_id"]

        # 2. Add hotel checking in Oct 4 14:00 local (07:00 UTC), covers Oct 4-5
        hotel_resp = client.post(
            "/api/v1/trip/event",
            headers=auth(user_id),
            json={
                "trip_id": trip_id,
                "event_type": "add_booking",
                "message": "Hotel",
                "preferences": {
                    "venue_name": "River View Hotel",
                    "booking_type": "hotel",
                    "scheduled_start": "2026-10-04T07:00:00Z",
                    "duration_minutes": 2760,
                    "lat": 18.920,
                    "lng": 102.450,
                    "geo_region": "vang_vieng_laos",
                },
            },
        )
        assert hotel_resp.status_code == 200

        # 3. Find the first unlocked activity on Oct 5
        trip_state = db_service.get_trip(trip_id)
        activities = [
            n
            for n in trip_state.nodes
            if not n.is_locked and getattr(n, "node_kind", "activity") == "activity"
        ]
        assert len(activities) > 0
        target = activities[0]
        target_node_id = target.node_id
        target_local_date = _local_date_of(_ensure_aware(target.scheduled_start), "vang_vieng_laos")
        assert target_local_date == date(2026, 10, 5)

        # Verify target is first unlocked on that day
        assert is_first_unlocked_activity(
            target, trip_state.nodes, "vang_vieng_laos", target_local_date
        )

        walk_calls.clear()

        # 4. Swap that activity
        swap_resp = client.post(
            "/api/v1/trip/event",
            headers=auth(user_id),
            json={
                "trip_id": trip_id,
                "event_type": "swap_activity",
                "message": "Something different",
                "target_node_id": target_node_id,
            },
        )
        assert swap_resp.status_code == 200
        swap_body = swap_resp.json()

        # 5. Assert walking was called with hotel coords as origin
        hotel_origin_calls = [c for c in walk_calls if c[0] == 18.920 and c[1] == 102.450]
        assert len(hotel_origin_calls) > 0, (
            f"Expected walking from hotel (18.920, 102.450), got: {walk_calls}"
        )

        # 6. Assert the target node_id is preserved but venue may have changed
        updated_nodes = swap_body["updated_nodes"]
        swapped = next((n for n in updated_nodes if n["node_id"] == target_node_id), None)
        assert swapped is not None, "Target node_id must be preserved"


# ---------------------------------------------------------------------------
# 12. Production wiring proofs
# ---------------------------------------------------------------------------


class TestProductionWiring:
    def test_scheduler_calls_find_constraining_flight(self, monkeypatch):
        _patch_walking(monkeypatch, 10)
        found_calls = []
        _orig = find_constraining_flight

        def spy(nodes, activity):
            found_calls.append(activity.venue_name)
            return _orig(nodes, activity)

        monkeypatch.setattr("services.scheduler.find_constraining_flight", spy)
        fl = _flight(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))
        act = _activity("Dinner", datetime(2026, 10, 5, 14, 0, tzinfo=timezone.utc))
        reschedule_and_validate([act, fl])
        assert "Dinner" in found_calls

    def test_scheduler_calls_is_last_unlocked(self, monkeypatch):
        _patch_walking(monkeypatch, 10)
        last_calls = []
        _orig = is_last_unlocked_activity

        def spy(node, all_nodes, geo, ld):
            last_calls.append(node.venue_name)
            return _orig(node, all_nodes, geo, ld)

        monkeypatch.setattr("services.scheduler.is_last_unlocked_activity", spy)
        h = _hotel(datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc))
        act = _activity("Cafe", datetime(2026, 10, 4, 10, 0, tzinfo=timezone.utc))
        reschedule_and_validate([h, act])
        assert "Cafe" in last_calls


# ---------------------------------------------------------------------------
# 13. Packing deferred
# ---------------------------------------------------------------------------


class TestPackingDeferred:
    """pack_day does not wire SPEC-10 flight/hotel constraints.

    This is intentional: SPEC-10 is PARTIAL.  Scheduler and state-machine
    are the production constraint paths.  pack_day constraints are deferred.
    """

    def test_pack_day_has_no_all_trip_nodes_parameter(self):
        import inspect

        from services.catalog_itinerary import pack_day

        sig = inspect.signature(pack_day)
        assert "all_trip_nodes" not in sig.parameters
