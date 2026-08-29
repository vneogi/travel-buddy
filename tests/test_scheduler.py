from datetime import datetime, timedelta

import services.scheduler as scheduler_mod
from services.scheduler import reschedule_and_validate
from models.schemas import TripNode, NodeStatus


def _fixed_transit(minutes):
    def _f(o_lat, o_lng, d_lat, d_lng, mode="driving"):
        return {
            "distance_km": 1.0,
            "duration_minutes": minutes,
            "mode": mode,
            "traffic_condition": "light",
        }

    return _f


def _always_open(monkeypatch):
    monkeypatch.setattr(scheduler_mod.maps_service, "check_venue_open", lambda hours, t=None: True)


def test_unreachable_locked_reservation_flagged(monkeypatch):
    monkeypatch.setattr(scheduler_mod.maps_service, "get_transit_time", _fixed_transit(90))
    _always_open(monkeypatch)
    base = datetime(2026, 8, 5, 9, 0)
    nodes = [
        TripNode(venue_name="A", scheduled_start=base, duration_minutes=60, lat=25.2, lng=55.2),
        TripNode(
            venue_name="LOCKED",
            scheduled_start=base + timedelta(hours=2),
            duration_minutes=60,
            is_locked=True,
            lat=25.3,
            lng=55.3,
        ),
    ]
    result = reschedule_and_validate(nodes)
    # A ends 10:00, +90 transit = 11:30 > locked 11:00 -> unreachable.
    assert result.has_hard_conflict is True
    # D3: synthetic transit no longer surfaces in warnings; only internal flag.
    assert result.has_hard_conflict is True


def test_feasible_keeps_planned_times(monkeypatch):
    monkeypatch.setattr(scheduler_mod.maps_service, "get_transit_time", _fixed_transit(10))
    _always_open(monkeypatch)
    base = datetime(2026, 8, 5, 9, 0)
    nodes = [
        TripNode(venue_name="A", scheduled_start=base, duration_minutes=60, lat=25.2, lng=55.2),
        TripNode(
            venue_name="B",
            scheduled_start=base + timedelta(hours=2),
            duration_minutes=60,
            lat=25.21,
            lng=55.21,
        ),
    ]
    result = reschedule_and_validate(nodes)
    assert result.has_hard_conflict is False
    assert result.nodes[1].scheduled_start == base + timedelta(hours=2)


def test_skipped_node_excluded(monkeypatch):
    monkeypatch.setattr(scheduler_mod.maps_service, "get_transit_time", _fixed_transit(10))
    _always_open(monkeypatch)
    base = datetime(2026, 8, 5, 9, 0)
    nodes = [
        TripNode(
            venue_name="A",
            scheduled_start=base,
            duration_minutes=60,
            status=NodeStatus.SKIPPED,
            lat=25.2,
            lng=55.2,
        ),
        TripNode(
            venue_name="B",
            scheduled_start=base + timedelta(hours=2),
            duration_minutes=60,
            lat=25.21,
            lng=55.21,
        ),
    ]
    result = reschedule_and_validate(nodes)
    active = [n for n in result.nodes if n.status != NodeStatus.SKIPPED]
    assert active[0].venue_name == "B"
    assert active[0].scheduled_start == base + timedelta(hours=2)


# ============================================================
# B1: Hotel occupancy -- hotels are background anchors
# ============================================================


def test_hotel_booking_does_not_push_later_activity(monkeypatch):
    """Mad Monkey-scale hotel (2760 min / 46 hours) must not shift Oct 5 activity.

    Sabotage proof S1: removing the _is_background_anchor gate causes
    prev_active_end = Oct 4 14:00 + 2760 min = Oct 6 12:00, pushing
    the Oct 5 09:00 activity to Oct 6 12:00+transit.
    """
    monkeypatch.setattr(scheduler_mod.maps_service, "get_transit_time", _fixed_transit(30))
    _always_open(monkeypatch)

    hotel_start = datetime(2026, 10, 4, 14, 0)
    activity_start = datetime(2026, 10, 5, 9, 0)

    nodes = [
        TripNode(
            venue_name="Mad Monkey Vang Vieng",
            scheduled_start=hotel_start,
            duration_minutes=2760,  # 46 hours (2 nights)
            is_locked=True,
            node_kind="booking",
            booking_type="hotel",
            lat=18.92,
            lng=102.45,
        ),
        TripNode(
            venue_name="Blue Lagoon",
            scheduled_start=activity_start,
            duration_minutes=120,
            lat=18.93,
            lng=102.46,
        ),
    ]
    result = reschedule_and_validate(nodes)

    # The activity must stay at Oct 5 09:00 -- NOT pushed to Oct 6.
    blue_lagoon = [n for n in result.nodes if n.venue_name == "Blue Lagoon"][0]
    assert blue_lagoon.scheduled_start == activity_start
    assert result.has_hard_conflict is False


def test_flight_booking_still_occupies_timeline(monkeypatch):
    """Control: a 180-minute locked flight still pushes a later unlocked node.

    Sabotage proof S2: if flights also become background anchors,
    a flight ending after the planned start of the next activity
    would no longer push it.
    """
    monkeypatch.setattr(scheduler_mod.maps_service, "get_transit_time", _fixed_transit(30))
    _always_open(monkeypatch)

    flight_start = datetime(2026, 10, 5, 9, 0)
    # Flight ends at 12:00. Next activity at 11:00 must be pushed.
    activity_start = datetime(2026, 10, 5, 11, 0)

    nodes = [
        TripNode(
            venue_name="Flight QV101",
            scheduled_start=flight_start,
            duration_minutes=180,
            is_locked=True,
            node_kind="booking",
            booking_type="flight",
            lat=18.92,
            lng=102.45,
        ),
        TripNode(
            venue_name="Afternoon Walk",
            scheduled_start=activity_start,
            duration_minutes=60,
            lat=18.93,
            lng=102.46,
        ),
    ]
    result = reschedule_and_validate(nodes)

    afternoon = [n for n in result.nodes if n.venue_name == "Afternoon Walk"][0]
    # Flight ends 12:00 + 30 transit = 12:30. Activity pushed from 11:00 to 12:30.
    expected = flight_start + timedelta(minutes=180 + 30)
    assert afternoon.scheduled_start == expected


def test_hotel_does_not_trigger_hard_conflict_for_later_locked_node(monkeypatch):
    """A hotel's checkout time must not create a hard conflict with a later locked node."""
    monkeypatch.setattr(scheduler_mod.maps_service, "get_transit_time", _fixed_transit(0))
    _always_open(monkeypatch)

    nodes = [
        TripNode(
            venue_name="Hotel",
            scheduled_start=datetime(2026, 10, 4, 14, 0),
            duration_minutes=2760,
            is_locked=True,
            node_kind="booking",
            booking_type="hotel",
            lat=18.92,
            lng=102.45,
        ),
        TripNode(
            venue_name="Locked Tour",
            scheduled_start=datetime(2026, 10, 5, 8, 0),
            duration_minutes=120,
            is_locked=True,
            lat=18.93,
            lng=102.46,
        ),
    ]
    result = reschedule_and_validate(nodes)
    assert result.has_hard_conflict is False


def test_hotel_checkin_anchors_transit_origin(monkeypatch):
    """Transit from hotel uses check-in time, not the previous activity's end.

    Setup: activity 09:00-10:00, hotel check-in 14:00 (2760 min), next 14:10.
    Hotel->next transit = 30 min. Next must land at 14:00+30 = 14:30,
    not 10:00+30 = 10:30 (stale prev_active_end) and not checkout-derived.
    """
    monkeypatch.setattr(scheduler_mod.maps_service, "get_transit_time", _fixed_transit(30))
    _always_open(monkeypatch)

    nodes = [
        TripNode(
            venue_name="Morning Cafe",
            scheduled_start=datetime(2026, 10, 4, 9, 0),
            duration_minutes=60,
            lat=18.90,
            lng=102.40,
        ),
        TripNode(
            venue_name="Mad Monkey",
            scheduled_start=datetime(2026, 10, 4, 14, 0),
            duration_minutes=2760,
            is_locked=True,
            node_kind="booking",
            booking_type="hotel",
            lat=18.92,
            lng=102.45,
        ),
        TripNode(
            venue_name="Afternoon Walk",
            scheduled_start=datetime(2026, 10, 4, 14, 10),
            duration_minutes=60,
            lat=18.93,
            lng=102.46,
        ),
    ]
    result = reschedule_and_validate(nodes)

    walk = [n for n in result.nodes if n.venue_name == "Afternoon Walk"][0]
    # Hotel check-in 14:00 + 30 transit = 14:30
    assert walk.scheduled_start == datetime(2026, 10, 4, 14, 30)
