"""SPEC-42 amendment 2026-11-24 (with brief Amendment 1): plain stops on busy days.

A plain stop is trip-private with no coordinates. It places with no travel
check; anything with coordinates whose walk leg touches it fails closed; What
Now labels the walk unknown; nothing raises. Reuses the SPEC-42 fixtures.
"""

from datetime import date, timedelta

import pytest

from agents.state_machine import _is_swap_reachable
from models.schemas import EventType, NodeStatus
from services.ask_service import WhatNowRequest, _compute_walking_minutes, handle_what_now
from services.booking_constraints import fits_next_lock, violates_hotel_return
from services.database_service import db_service
from services.direct_add_service import apply_direct_add
from services.move_service import apply_move
from services.scheduler import reschedule_and_validate
from services.uncatalogued_add_service import apply_uncatalogued_add
from tests.conftest import auth
from tests.test_spec42_direct_add import BASE, FOOD, VTE, FakeDb, base_trip, local, node
from tests.test_spec42_uncatalogued_add import CATALOG, prefs

D12, D13, D14 = "2026-10-12", "2026-10-13", "2026-10-14"


def _plain(nid, start, *, slot=None, dur=60):
    return node(nid, f"Plain {nid}", start, slot=slot, dur=dur, at=None).model_copy(
        update={"venue_id": None, "place_source": "trip_private"}
    )


def _lock(nid, start, *, kind="tour", dur=60, at=BASE):
    return node(
        nid,
        f"{kind} booking",
        start,
        dur=dur,
        at=at,
        is_locked=True,
        node_kind="booking",
        booking_type=kind,
    )


def _add_plain(trip, day, slot, dwell=60):
    return apply_uncatalogued_add(
        trip,
        prefs(target_date=day, target_slot=slot, typical_dwell_minutes=dwell, lat=..., lng=...),
        FakeDb(CATALOG),
    )


def _with(trip, *extra):
    return trip.model_copy(update={"nodes": list(trip.nodes) + list(extra)})


def _move(trip, node_id, day, slot):
    return apply_move(
        trip, node_id, {"mode": "move", "target_date": day, "target_slot": slot}, None
    )


# 1 ---------------------------------------------------------------------------
def test_plain_stop_on_busy_day_starts_at_later_of_floor_and_previous_end():
    r = _add_plain(base_trip(), D12, "dinner")  # afternoon stop ends 15:30
    assert r.ok, r.code
    assert r.added.scheduled_start == local(2026, 10, 12, 17)
    assert r.added.lat is None and r.added.lng is None
    assert r.added.venue_id is None and r.added.place_source == "trip_private"

    trip = base_trip()
    long_aft = [
        n.model_copy(update={"duration_minutes": 240}) if n.node_id == "aft" else n
        for n in trip.nodes
    ]
    r = _add_plain(trip.model_copy(update={"nodes": long_aft}), D12, "dinner")  # ends 18:00
    assert r.ok, r.code
    assert r.added.scheduled_start == local(2026, 10, 12, 18)


# 2 ---------------------------------------------------------------------------
def test_plain_stop_overlapping_an_existing_stop_is_refused():
    trip = _with(base_trip(), node("late", "Late Stop", local(2026, 10, 12, 17, 30)))
    r = _add_plain(trip, D12, "dinner")
    assert not r.ok and r.code == "reachability"


# 3 ---------------------------------------------------------------------------
def test_plain_stop_before_locks_uses_time_only_and_flight_cutoff():
    ok = _add_plain(
        _with(base_trip(), _lock("tour", local(2026, 10, 12, 18), at=None)), D12, "dinner", 60
    )
    assert ok.ok, ok.code  # ends 18:00 == lock start, no walk checked
    late = _add_plain(
        _with(base_trip(), _lock("tour", local(2026, 10, 12, 18), at=None)), D12, "dinner", 90
    )
    assert not late.ok and late.code == "reachability"
    inside = _add_plain(
        _with(base_trip(), _lock("fl", local(2026, 10, 12, 19, 30), kind="flight")), D12, "dinner"
    )
    assert not inside.ok and inside.code == "reachability"  # ends 18:00 > 19:30 - 150 min
    clear = _add_plain(
        _with(base_trip(), _lock("fl", local(2026, 10, 12, 21), kind="flight")), D12, "dinner"
    )
    assert clear.ok, clear.code  # ends 18:00 <= 21:00 - 150 min


def _catalog_add(trip, day, slot):
    return apply_direct_add(
        trip,
        {"mode": "direct_add", "venue_id": "f0", "target_date": day, "target_slot": slot},
        FakeDb(FOOD),
    )


# 4 ---------------------------------------------------------------------------
def test_catalog_stop_before_a_plain_stop_is_refused_reachability():
    trip = _with(base_trip(), _plain("p13", local(2026, 10, 13, 17), slot="dinner"))
    r = _catalog_add(trip, D13, "lunch")
    assert not r.ok and r.code == "reachability"


# 5 ---------------------------------------------------------------------------
def test_catalog_stop_after_a_plain_stop_is_refused_reachability():
    trip = _with(base_trip(), _plain("p13", local(2026, 10, 13, 12), slot="lunch"))
    r = _catalog_add(trip, D13, "dinner")
    assert not r.ok and r.code == "reachability"


# 6 ---------------------------------------------------------------------------
def test_move_catalog_next_to_plain_refused_and_plain_move_places():
    trip = _with(base_trip(), _plain("p13", local(2026, 10, 13, 17), slot="dinner"))
    r = _move(trip, "temple", D13, "afternoon_evening_tour")
    assert not r.ok and r.code == "neighbour_unreachable"
    r = _move(trip, "lunch", D13, "dinner")
    assert not r.ok  # dinner already holds the plain stop
    trip2 = _with(base_trip(), _plain("p13", local(2026, 10, 13, 12), slot="lunch"))
    r = _move(trip2, "p13", D12, "dinner")
    assert r.ok, r.code
    moved = next(n for n in r.nodes if n.node_id == "p13")
    assert moved.scheduled_start == local(2026, 10, 12, 17) and moved.slot_name == "dinner"


# 7 ---------------------------------------------------------------------------
def test_swap_and_ask_builders_omit_unknown_legs_without_raising():
    plain = _plain("p", local(2026, 10, 12, 10), slot="morning_tour")
    target = node("t", "Target", local(2026, 10, 12, 12), slot="lunch")
    nodes = [plain, target]
    assert _is_swap_reachable(target, BASE[0], BASE[1], 60, nodes, 1) is False
    assert (
        _compute_walking_minutes(plain.model_dump(mode="json"), {"lat": BASE[0], "lng": BASE[1]})
        is None
    )


def test_what_now_plain_origin_labels_unknown_walk():
    from datetime import datetime, timezone

    now = datetime(2026, 10, 2, 4, 0, tzinfo=timezone.utc)
    origin = {
        "node_id": "p1",
        "venue_name": "Plain origin",
        "venue_id": None,
        "scheduled_start": (now - timedelta(minutes=30)).isoformat(),
        "duration_minutes": 60,
        "geo_region": VTE,
        "lat": None,
        "lng": None,
        "is_locked": False,
        "node_kind": "activity",
        "place_source": "trip_private",
    }
    rows = [dict(v, opening_hours_structured=None) for v in FOOD[:3]]

    class _Db:
        def list_venues_for_region(self, region):
            return [dict(r) for r in rows]

    resp = handle_what_now(WhatNowRequest(available_minutes=120), [origin], now, VTE, _Db())
    cands = resp.what_now["candidates"]
    assert cands
    for c in cands:
        assert "walking_time" in c["unknown_fields"]
        assert "fits_available_window" not in c["reason_codes"]
        assert "short_walk_from_context" not in c["reason_codes"]


# 8 ---------------------------------------------------------------------------
def test_scheduler_gives_plain_node_zero_transit_and_keeps_later_nodes():
    plain = _plain("p", local(2026, 10, 12, 13), slot=None, dur=30)
    nodes = list(base_trip().nodes) + [plain]
    nodes.sort(key=lambda n: n.scheduled_start)
    result = reschedule_and_validate(nodes, mutated_node_ids={"p"})
    by_id = {n.node_id: n for n in result.nodes}
    assert by_id["p"].scheduled_start == local(2026, 10, 12, 13)
    assert by_id["aft"].scheduled_start >= by_id["p"].scheduled_start + timedelta(minutes=30)


# 9 ---------------------------------------------------------------------------
def test_http_plain_add_on_busy_day_one_node_one_reroute_and_refusal_writes_nothing(client):
    user = "pbd-http"
    created = client.post(
        "/api/v1/trip/create",
        headers=auth(user),
        json={
            "geo_region": "zanzibar_tanzania",
            "start_date": "2026-12-27",
            "end_date": "2026-12-27",
            "start_empty": True,
        },
    )
    assert created.status_code == 200, created.text
    trip_id = created.json()["trip_id"]
    cands = client.get(
        f"/api/v1/trip/{trip_id}/add_candidates",
        headers=auth(user),
        params={"target_date": "2026-12-27", "target_slot": "morning_tour"},
    ).json()["candidates"]

    def event(prefs_):
        return client.post(
            "/api/v1/trip/event",
            headers=auth(user),
            json={
                "trip_id": trip_id,
                "event_type": EventType.ADD_ACTIVITY.value,
                "message": "add",
                "preferences": prefs_,
            },
        )

    assert (
        event(
            {
                "mode": "direct_add",
                "venue_id": cands[0]["venue_id"],
                "target_date": "2026-12-27",
                "target_slot": "morning_tour",
            }
        ).status_code
        == 200
    )
    plain = {
        "mode": "uncatalogued_add",
        "name": "Sunset jetty",
        "target_date": "2026-12-27",
        "target_slot": "dinner",
        "typical_dwell_minutes": 60,
    }
    count0 = db_service.get_or_create_user(user).daily_reroute_count
    n0 = len(db_service.get_trip(trip_id).nodes)
    r = event(plain)
    assert r.status_code == 200, r.text
    assert len(db_service.get_trip(trip_id).nodes) == n0 + 1
    assert db_service.get_or_create_user(user).daily_reroute_count == count0 + 1
    v1 = db_service.get_trip(trip_id).version
    again = event(dict(plain, name="Second jetty"))
    assert again.status_code == 422, again.text
    assert db_service.get_trip(trip_id).version == v1
    assert db_service.get_or_create_user(user).daily_reroute_count == count0 + 1


# 10 --------------------------------------------------------------------------
def _entry_points():
    busy = _with(base_trip(), _plain("p13", local(2026, 10, 13, 12), slot="lunch"))
    plain = _plain("p", local(2026, 10, 12, 10), slot="morning_tour")
    target = node("t", "Target", local(2026, 10, 12, 12), slot="lunch")
    hotel = node(
        "h",
        "Hotel",
        local(2026, 10, 11, 15),
        dur=24 * 60,
        at=None,
        is_locked=True,
        node_kind="booking",
        booking_type="hotel",
    )
    return {
        "uncatalogued_add_plain": lambda: _add_plain(base_trip(), D12, "dinner"),
        "direct_add_after_plain": lambda: _catalog_add(busy, D13, "dinner"),
        "move_catalog_next_to_plain": lambda: _move(busy, "temple", D13, "dinner"),
        "move_plain": lambda: _move(busy, "p13", D12, "dinner"),
        "swap_reachable": lambda: _is_swap_reachable(
            target, BASE[0], BASE[1], 60, [plain, target], 1
        ),
        "ask_walking_minutes": lambda: _compute_walking_minutes(
            plain.model_dump(mode="json"), {"lat": None, "lng": None}
        ),
        "fits_next_lock_plain": lambda: fits_next_lock(
            {"lat": None, "lng": None},
            local(2026, 10, 12, 17),
            60,
            _lock("l", local(2026, 10, 12, 19), at=None),
            VTE,
            plain_time_only=True,
        ),
        "fits_next_lock_catalog": lambda: fits_next_lock(
            {"lat": None, "lng": None},
            local(2026, 10, 12, 17),
            60,
            _lock("l", local(2026, 10, 12, 19), at=None),
            VTE,
        ),
        "hotel_return": lambda: violates_hotel_return(
            local(2026, 10, 12, 20), 60, hotel, VTE, date(2026, 10, 12)
        ),
        "scheduler": lambda: reschedule_and_validate(
            sorted(list(busy.nodes), key=lambda n: n.scheduled_start)
        ),
    }


@pytest.mark.parametrize("name", sorted(_entry_points()))
def test_no_entry_point_raises_on_a_coordinate_less_neighbour(name):
    _entry_points()[name]()  # any exception fails the test


# 11 --------------------------------------------------------------------------
def test_time_window_plain_add_unchanged():
    empty_day = apply_uncatalogued_add(
        base_trip(),
        {
            "mode": "uncatalogued_add",
            "name": "Island trip",
            "target_date": D14,
            "time_window": "afternoon",
        },
        FakeDb(CATALOG),
    )
    assert empty_day.ok, empty_day.code
    assert empty_day.added.time_window == "afternoon"
    busy = apply_uncatalogued_add(
        base_trip(),
        {
            "mode": "uncatalogued_add",
            "name": "Island trip",
            "target_date": D12,
            "time_window": "afternoon",
        },
        FakeDb(CATALOG),
    )
    assert not busy.ok and busy.code == "needs_review"
    assert busy.review["skip_node_ids"] == ["aft"]
