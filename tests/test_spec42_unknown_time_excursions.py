"""SPEC-42 unknown-time excursion windows, driven through the API.

Every Add, Move, swap and cancel goes through POST /api/v1/trip/event (or the
swap candidates route). Created trips pack every day, so tests that need an
empty slot clear it in the stored in-memory trip first (setup only). Zanzibar
is UTC+3.
"""

from datetime import datetime, timedelta

import services.db_provider as dbp
from models.schemas import TripState
from services.direct_add_service import day_context
from tests.conftest import auth

GEO = "zanzibar_tanzania"
DAY = "2026-12-27"
SLOTS = ("morning_tour", "lunch", "afternoon_evening_tour", "dinner")


def _trip(client, user):
    r = client.post(
        "/api/v1/trip/create",
        headers=auth(user),
        json={"geo_region": GEO, "start_date": "2026-12-25", "end_date": "2026-12-28"},
    )
    assert r.status_code == 200, r.text
    return r.json()["trip_id"]


def _stored(trip_id):
    return dbp.db_service._trips[trip_id]["nodes"]


def _local_date(node):
    utc = datetime.fromisoformat(node["scheduled_start"].replace("Z", "+00:00"))
    return (utc + timedelta(hours=3)).date().isoformat()


def _day(nodes, day=DAY):
    return {n["slot_name"]: n for n in nodes if n.get("slot_name") and _local_date(n) == day}


def _clear(trip_id, slots, day=DAY):
    """Setup only: mark the packed stops in *slots* on *day* as skipped."""
    for n in _stored(trip_id):
        if _local_date(n) == day and n.get("slot_name") in slots and not n.get("time_window"):
            n["status"] = "skipped"


def _event(client, user, trip_id, event_type, preferences=None, target=None):
    body = {"trip_id": trip_id, "event_type": event_type, "message": event_type}
    if preferences is not None:
        body["preferences"] = preferences
    if target is not None:
        body["target_node_id"] = target
    return client.post("/api/v1/trip/event", headers=auth(user), json=body)


def _window(client, user, trip_id, window, name="Prison Island", day=DAY, **extra):
    prefs = {"mode": "uncatalogued_add", "name": name, "target_date": day, "time_window": window}
    prefs.update(extra)
    return _event(client, user, trip_id, "add_activity", preferences=prefs)


def _code(r):
    return r.json()["detail"]["code"]


def _floor(trip_id, slot, day=DAY):
    """Slot floor from the production day context (no hour constants here)."""
    trip = TripState(**dbp.db_service._trips[trip_id])
    ctx, _code_ = day_context(trip, day, slot)
    assert ctx is not None
    return ctx.floor_utc


def _start(node):
    return datetime.fromisoformat(node["scheduled_start"].replace("Z", "+00:00"))


def _statuses(trip_id):
    return {n["node_id"]: n["status"] for n in _stored(trip_id)}


def _added(r, name="Prison Island"):
    return next(n for n in r.json()["updated_nodes"] if n["venue_name"] == name)


def test_whole_day_on_empty_day_runs_to_dinner_floor(client):
    trip_id = _trip(client, "utx-1")
    _clear(trip_id, ("morning_tour", "lunch", "afternoon_evening_tour"))
    r = _window(client, "utx-1", trip_id, "whole_day")
    assert r.status_code == 200, r.text
    node = _added(r)
    assert node["slot_name"] == "morning_tour"
    assert node["time_window"] == "whole_day"
    assert node["place_source"] == "trip_private"
    assert _start(node) == _floor(trip_id, "morning_tour")
    assert _start(node) + timedelta(minutes=node["duration_minutes"]) == _floor(trip_id, "dinner")
    assert [n for n in r.json()["updated_nodes"] if n.get("time_window")] == [node]


def test_afternoon_on_empty_day(client):
    trip_id = _trip(client, "utx-2")
    _clear(trip_id, ("afternoon_evening_tour",))
    r = _window(client, "utx-2", trip_id, "afternoon")
    assert r.status_code == 200, r.text
    node = _added(r)
    assert node["slot_name"] == "afternoon_evening_tour"
    assert node["time_window"] == "afternoon"
    assert _start(node) + timedelta(minutes=node["duration_minutes"]) == _floor(trip_id, "dinner")


def test_morning_over_pending_lunch_needs_review(client):
    trip_id = _trip(client, "utx-3")
    _clear(trip_id, ("morning_tour",))
    lunch = _day(_stored(trip_id))["lunch"]
    before = _statuses(trip_id)
    count = len(_stored(trip_id))
    r = _window(client, "utx-3", trip_id, "morning")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "needs_review"
    assert body["excursion_review"] == {
        "time_window": "morning",
        "skip_node_ids": [lunch["node_id"]],
    }
    assert len(_stored(trip_id)) == count
    assert _statuses(trip_id) == before
    assert _day(_stored(trip_id))["lunch"]["status"] == "pending"


def test_confirm_skips_lunch_in_place_and_adds(client):
    trip_id = _trip(client, "utx-4")
    _clear(trip_id, ("morning_tour",))
    lunch_id = _day(_stored(trip_id))["lunch"]["node_id"]
    version = client.get(f"/api/v1/trip/{trip_id}", headers=auth("utx-4")).json()["version"]
    r = _window(client, "utx-4", trip_id, "morning", confirm_skip_node_ids=[lunch_id])
    assert r.status_code == 200, r.text
    assert r.json()["version"] == version + 1  # one persisted write
    stored = {n["node_id"]: n for n in _stored(trip_id)}
    assert stored[lunch_id]["status"] == "skipped"
    assert stored[lunch_id]["slot_name"] == "lunch"
    added = [n for n in stored.values() if n.get("time_window") == "morning"]
    assert len(added) == 1 and added[0]["status"] == "pending"


def test_whole_day_review_lists_three_and_dinner_stays(client):
    trip_id = _trip(client, "utx-5")
    day = _day(_stored(trip_id))
    expected = [day[s]["node_id"] for s in ("morning_tour", "lunch", "afternoon_evening_tour")]
    r = _window(client, "utx-5", trip_id, "whole_day")
    assert r.status_code == 200, r.text
    assert r.json()["excursion_review"]["skip_node_ids"] == expected
    r = _window(client, "utx-5", trip_id, "whole_day", confirm_skip_node_ids=expected)
    assert r.status_code == 200, r.text
    after = _day(_stored(trip_id))
    assert after["dinner"]["status"] == "pending"
    assert after["dinner"]["node_id"] == day["dinner"]["node_id"]
    for nid in expected:
        assert _statuses(trip_id)[nid] == "skipped"


def test_confirm_with_stale_ids_is_refused(client):
    trip_id = _trip(client, "utx-6")
    _clear(trip_id, ("morning_tour",))
    dinner_id = _day(_stored(trip_id))["dinner"]["node_id"]
    before = _statuses(trip_id)
    r = _window(client, "utx-6", trip_id, "morning", confirm_skip_node_ids=[dinner_id])
    assert r.status_code == 422, r.text
    assert _code(r) == "stale"
    assert _statuses(trip_id) == before


def test_locked_booking_in_window_is_refused(client):
    trip_id = _trip(client, "utx-7")
    _clear(trip_id, ("morning_tour", "lunch", "afternoon_evening_tour"))
    b = _event(
        client,
        "utx-7",
        trip_id,
        "add_booking",
        preferences={
            "venue_name": "Spice tour",
            "booking_type": "tour",
            "scheduled_start": f"{DAY}T10:00:00",
            "duration_minutes": 120,
        },
    )
    assert b.status_code == 200, b.text
    before = _statuses(trip_id)
    r = _window(client, "utx-7", trip_id, "whole_day")
    assert r.status_code == 422, r.text
    assert _code(r) == "locked_conflict"
    assert _statuses(trip_id) == before


def test_both_slot_and_window_is_invalid_slot(client):
    trip_id = _trip(client, "utx-8")
    r = _window(client, "utx-8", trip_id, "morning", target_slot="morning_tour")
    assert r.status_code == 422, r.text
    assert _code(r) == "invalid_slot"


def test_unknown_window_is_invalid_window(client):
    trip_id = _trip(client, "utx-9")
    r = _window(client, "utx-9", trip_id, "evening")
    assert r.status_code == 422, r.text
    assert _code(r) == "invalid_window"
    assert "Choose morning, afternoon, or whole day." in r.json()["detail"]["message"]


def test_window_with_dwell_is_invalid_dwell(client):
    trip_id = _trip(client, "utx-10")
    r = _window(client, "utx-10", trip_id, "afternoon", typical_dwell_minutes=60)
    assert r.status_code == 422, r.text
    assert _code(r) == "invalid_dwell"


def test_slot_plus_dwell_add_unchanged(client):
    trip_id = _trip(client, "utx-11")
    base = {
        "mode": "uncatalogued_add",
        "name": "Mama Asha Stall",
        "target_date": DAY,
        "target_slot": "lunch",
        "typical_dwell_minutes": 60,
    }
    occupied = _event(client, "utx-11", trip_id, "add_activity", preferences=base)
    assert occupied.status_code == 422, occupied.text
    assert _code(occupied) == "occupied"
    _clear(trip_id, ("lunch",))
    near = _day(_stored(trip_id))["morning_tour"]  # coords needed on a non-empty day
    ok = _event(
        client,
        "utx-11",
        trip_id,
        "add_activity",
        preferences={**base, "lat": near["lat"], "lng": near["lng"]},
    )
    assert ok.status_code == 200, ok.text
    node = _added(ok, "Mama Asha Stall")
    assert node["slot_name"] == "lunch"
    assert node["duration_minutes"] == 60
    assert node.get("time_window") is None
    assert ok.json().get("excursion_review") is None


def test_time_window_survives_reload(client):
    trip_id = _trip(client, "utx-12")
    _clear(trip_id, ("morning_tour", "lunch", "afternoon_evening_tour"))
    node_id = _added(_window(client, "utx-12", trip_id, "whole_day"))["node_id"]
    got = client.get(f"/api/v1/trip/{trip_id}", headers=auth("utx-12"))
    assert got.status_code == 200, got.text
    node = next(n for n in got.json()["nodes"] if n["node_id"] == node_id)
    assert node["time_window"] == "whole_day"


def _window_node(client, user):
    trip_id = _trip(client, user)
    _clear(trip_id, ("morning_tour", "lunch", "afternoon_evening_tour"))
    node = _added(_window(client, user, trip_id, "whole_day"))
    _clear(trip_id, ("afternoon_evening_tour",), day="2026-12-26")
    return trip_id, node


def test_move_of_window_node_is_refused(client):
    trip_id, node = _window_node(client, "utx-17")
    before = {n["node_id"]: (n["scheduled_start"], n["status"]) for n in _stored(trip_id)}
    r = _event(
        client,
        "utx-17",
        trip_id,
        "move_activity",
        target=node["node_id"],
        preferences={
            "mode": "move",
            "target_date": "2026-12-26",
            "target_slot": "afternoon_evening_tour",
        },
    )
    assert r.status_code == 422, r.text
    assert _code(r) == "window_node"
    assert {n["node_id"]: (n["scheduled_start"], n["status"]) for n in _stored(trip_id)} == before


def test_swap_event_of_window_node_is_refused(client):
    trip_id, node = _window_node(client, "utx-18")
    before = {n["node_id"]: (n["venue_name"], n["status"]) for n in _stored(trip_id)}
    r = _event(client, "utx-18", trip_id, "swap_activity", target=node["node_id"])
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["error"] == "window_node"
    assert {n["node_id"]: (n["venue_name"], n["status"]) for n in _stored(trip_id)} == before


def test_swap_candidates_for_window_node_is_refused(client):
    trip_id, node = _window_node(client, "utx-19")
    r = client.get(
        f"/api/v1/trip/{trip_id}/swap_candidates/{node['node_id']}", headers=auth("utx-19")
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == {
        "error": "window_node",
        "message": "This excursion covers a whole window. Remove it and add it again to change it.",
    }


def test_cancel_of_window_node_skips_in_place(client):
    trip_id, node = _window_node(client, "utx-20")
    r = _event(client, "utx-20", trip_id, "cancel_activity", target=node["node_id"])
    assert r.status_code == 200, r.text
    stored = next(n for n in _stored(trip_id) if n["node_id"] == node["node_id"])
    assert stored["status"] == "skipped"
    assert stored["time_window"] == "whole_day"


def test_move_and_swap_of_plain_trip_private_node_unchanged(client):
    user = "utx-21"
    trip_id = _trip(client, user)
    _clear(trip_id, ("afternoon_evening_tour",))
    _clear(trip_id, ("afternoon_evening_tour",), day="2026-12-26")
    prefs = {
        "mode": "uncatalogued_add",
        "name": "Kiponda Lane Walk",
        "target_date": DAY,
        "target_slot": "afternoon_evening_tour",
        "typical_dwell_minutes": 60,
    }
    near = _day(_stored(trip_id))["lunch"]  # coords needed on a non-empty day
    prefs.update(lat=near["lat"], lng=near["lng"])
    node = _added(
        _event(client, user, trip_id, "add_activity", preferences=prefs), "Kiponda Lane Walk"
    )
    assert node.get("time_window") is None
    mv = _event(
        client,
        user,
        trip_id,
        "move_activity",
        target=node["node_id"],
        preferences={
            "mode": "move",
            "target_date": "2026-12-26",
            "target_slot": "afternoon_evening_tour",
        },
    )
    assert mv.status_code == 200, mv.text
    moved = next(n for n in mv.json()["updated_nodes"] if n["node_id"] == node["node_id"])
    assert _local_date(moved) == "2026-12-26" and moved["slot_name"] == "afternoon_evening_tour"
    cand = client.get(
        f"/api/v1/trip/{trip_id}/swap_candidates/{node['node_id']}", headers=auth(user)
    )
    assert cand.status_code == 200, cand.text
