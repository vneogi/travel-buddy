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
