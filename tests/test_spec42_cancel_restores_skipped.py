"""SPEC-42: cancelling an excursion window restores the stops it skipped.

Excursions in tests 1, 2, 3, 4, 6, 8 and 9 are created through the real add
flow (review, then confirm_skip_node_ids), so production code sets the
skipped_by_window_id tag. Everything goes through POST /api/v1/trip/event.
Zanzibar is UTC+3.
"""

import json
from datetime import datetime, timedelta, timezone

import services.db_provider as dbp
from models.schemas import TripNode, TripState
from tests.conftest import auth

GEO = "zanzibar_tanzania"
DAY = "2026-12-27"
WINDOW = "Prison Island"


def _trip(client, user):
    r = client.post(
        "/api/v1/trip/create",
        headers=auth(user),
        json={"geo_region": GEO, "start_date": "2026-12-25", "end_date": "2026-12-28"},
    )
    assert r.status_code == 200, r.text
    return r.json()["trip_id"]


def _event(client, user, trip_id, event_type, preferences=None, target=None):
    body = {"trip_id": trip_id, "event_type": event_type, "message": event_type}
    if preferences is not None:
        body["preferences"] = preferences
    if target is not None:
        body["target_node_id"] = target
    return client.post("/api/v1/trip/event", headers=auth(user), json=body)


def _stored(trip_id):
    return dbp.db_service._trips[trip_id]["nodes"]


def _local_date(node):
    utc = datetime.fromisoformat(node["scheduled_start"].replace("Z", "+00:00"))
    return (utc + timedelta(hours=3)).date().isoformat()


def _day(trip_id, day=DAY):
    return {
        n["slot_name"]: n
        for n in _stored(trip_id)
        if n.get("slot_name")
        and not n.get("time_window")
        and n.get("node_kind") != "booking"
        and _local_date(n) == day
    }


def _node(trip_id, node_id):
    return next(n for n in _stored(trip_id) if n["node_id"] == node_id)


def _excursion(client, user, trip_id, window="morning", day=DAY):
    """Real add flow: review, then confirm with the reviewed ids."""
    prefs = {"mode": "uncatalogued_add", "name": WINDOW, "target_date": day, "time_window": window}
    review = _event(client, user, trip_id, "add_activity", preferences=prefs)
    assert review.status_code == 200, review.text
    ids = review.json()["excursion_review"]["skip_node_ids"]
    done = _event(
        client, user, trip_id, "add_activity", preferences={**prefs, "confirm_skip_node_ids": ids}
    )
    assert done.status_code == 200, done.text
    window_node = next(n for n in _stored(trip_id) if n.get("time_window") == window)
    return window_node["node_id"], ids


def _cancel(client, user, trip_id, node_id):
    r = _event(client, user, trip_id, "cancel_activity", target=node_id)
    assert r.status_code == 200, r.text
    return r.json()["message"]


def _place_booking(trip_id, name, local_hhmm, minutes=60):
    """Setup only: store a locked tour booking directly, as a booking made
    before the booking-over-window slice would be."""
    hh, mm = (int(x) for x in local_hhmm.split(":"))
    d = datetime.fromisoformat(DAY)
    start = datetime(d.year, d.month, d.day, hh, mm, tzinfo=timezone.utc) - timedelta(hours=3)
    node = TripNode(
        venue_name=name,
        scheduled_start=start,
        duration_minutes=minutes,
        is_locked=True,
        node_kind="booking",
        booking_type="tour",
        geo_region=GEO,
    )
    nodes = _stored(trip_id)
    nodes.append(node.model_dump(mode="json"))
    nodes.sort(key=lambda n: n["scheduled_start"])


def test_cancel_morning_excursion_restores_both_stops(client):
    user = "crs-1"
    trip_id = _trip(client, user)
    day = _day(trip_id)
    morning, lunch = day["morning_tour"], day["lunch"]
    window_id, ids = _excursion(client, user, trip_id)
    assert ids == [morning["node_id"], lunch["node_id"]]
    for nid in ids:
        assert _node(trip_id, nid)["skipped_by_window_id"] == window_id

    message = _cancel(client, user, trip_id, window_id)
    for nid in ids:
        node = _node(trip_id, nid)
        assert node["status"] == "pending"
        assert node["skipped_by_window_id"] is None
    assert _node(trip_id, window_id)["status"] == "skipped"
    assert message == (
        f"Canceled {WINDOW}. Brought back 2 stops: {morning['venue_name']}, {lunch['venue_name']}."
    )
    assert window_id not in message and morning["node_id"] not in message


def test_stop_cancelled_on_its_own_is_not_restored(client):
    user = "crs-2"
    trip_id = _trip(client, user)
    day = _day(trip_id)
    morning, lunch = day["morning_tour"], day["lunch"]
    _cancel(client, user, trip_id, lunch["node_id"])
    window_id, ids = _excursion(client, user, trip_id)
    assert ids == [morning["node_id"]]

    message = _cancel(client, user, trip_id, window_id)
    assert _node(trip_id, lunch["node_id"])["status"] == "skipped"
    assert lunch["venue_name"] not in message


def test_stop_skipped_by_booking_reflow_is_not_restored(client):
    user = "crs-3"
    trip_id = _trip(client, user)
    checkout_day = "2026-12-26"
    hotel = _event(
        client,
        user,
        trip_id,
        "add_booking",
        preferences={
            "venue_name": "Hotel booking",
            "booking_type": "hotel",
            "scheduled_start": "2026-12-25T15:00:00",
            "duration_minutes": 20 * 60,
        },
    )
    assert hotel.status_code == 200, hotel.text
    booking_id = hotel.json()["booking_reflow"]["booking_node_id"]
    reflow = _event(
        client,
        user,
        trip_id,
        "confirm_booking_reflow",
        preferences={"intent": "conservative"},
        target=booking_id,
    )
    assert reflow.status_code == 200, reflow.text
    day = _day(trip_id, checkout_day)
    # Conservative keeps the checkout-day morning and skips lunch onward.
    morning, lunch = day["morning_tour"], day["lunch"]
    assert morning["status"] == "pending"
    assert lunch["status"] == "skipped"  # skipped by the reflow, not a window
    assert lunch.get("skipped_by_window_id") is None

    window_id, ids = _excursion(client, user, trip_id, window="morning", day=checkout_day)
    assert ids == [morning["node_id"]]
    message = _cancel(client, user, trip_id, window_id)
    for slot in ("lunch", "afternoon_evening_tour", "dinner"):
        assert _node(trip_id, day[slot]["node_id"])["status"] == "skipped", slot
    assert lunch["venue_name"] not in message


def test_clashing_stop_stays_skipped_and_is_named(client):
    user = "crs-4"
    trip_id = _trip(client, user)
    day = _day(trip_id)
    morning, lunch = day["morning_tour"], day["lunch"]
    window_id, ids = _excursion(client, user, trip_id)
    # A locked booking added after the excursion, at the skipped lunch stop's time.
    # Setup only: add_booking now refuses a booking inside an active window
    # (SPEC-42 booking-over-window), so place it as a pre-slice booking.
    _place_booking(trip_id, "Spice tour", "11:00")

    message = _cancel(client, user, trip_id, window_id)
    assert _node(trip_id, morning["node_id"])["status"] == "pending"
    kept = _node(trip_id, lunch["node_id"])
    assert kept["status"] == "skipped"
    assert kept["skipped_by_window_id"] == window_id
    assert message == (
        f"Canceled {WINDOW}. Brought back 1 stop: {morning['venue_name']}. "
        f"Left skipped because it now clashes: {lunch['venue_name']}."
    )


def test_reply_wording_one_restored_two_clashed(client):
    user = "crs-4b"
    trip_id = _trip(client, user)
    day = _day(trip_id)
    morning, lunch, afternoon = day["morning_tour"], day["lunch"], day["afternoon_evening_tour"]
    window_id, ids = _excursion(client, user, trip_id, window="whole_day")
    assert ids == [morning["node_id"], lunch["node_id"], afternoon["node_id"]]
    # Setup only: placed as pre-slice bookings (add_booking now refuses them).
    for name, start in (("Spice tour", "09:00"), ("Cooking class", "11:00")):
        _place_booking(trip_id, name, start)

    message = _cancel(client, user, trip_id, window_id)
    assert _node(trip_id, afternoon["node_id"])["status"] == "pending"
    assert message == (
        f"Canceled {WINDOW}. Brought back 1 stop: {afternoon['venue_name']}. "
        "Left skipped because they now clash: "
        f"{morning['venue_name']}, {lunch['venue_name']}."
    )


def test_legacy_excursion_cancels_without_restore(client):
    user = "crs-5"
    trip_id = _trip(client, user)
    # Legacy shape: stops skipped with no tag, window added onto the cleared
    # slots (the window cancel test style), and the tag key absent from JSON.
    for n in _stored(trip_id):
        if _local_date(n) == DAY and n.get("slot_name") in ("morning_tour", "lunch"):
            n["status"] = "skipped"
    prefs = {
        "mode": "uncatalogued_add",
        "name": WINDOW,
        "target_date": DAY,
        "time_window": "morning",
    }
    added = _event(client, user, trip_id, "add_activity", preferences=prefs)
    assert added.status_code == 200, added.text
    for n in _stored(trip_id):
        n.pop("skipped_by_window_id", None)
    window_id = next(n["node_id"] for n in _stored(trip_id) if n.get("time_window"))
    skipped_before = {n["node_id"] for n in _stored(trip_id) if n["status"] == "skipped"}

    message = _cancel(client, user, trip_id, window_id)
    assert message == f"Canceled {WINDOW}."
    assert {n["node_id"] for n in _stored(trip_id) if n["status"] == "skipped"} == (
        skipped_before | {window_id}
    )


def test_tag_survives_save_and_reload(client):
    user = "crs-6"
    trip_id = _trip(client, user)
    window_id, ids = _excursion(client, user, trip_id)
    # Reload from state_json: a JSON round trip of the stored blob, saved back.
    blob = json.loads(json.dumps(dbp.db_service._trips[trip_id]))
    dbp.db_service.save_trip(TripState(**blob))
    got = client.get(f"/api/v1/trip/{trip_id}", headers=auth(user))
    assert got.status_code == 200, got.text
    by_id = {n["node_id"]: n for n in got.json()["nodes"]}
    assert all(by_id[nid]["skipped_by_window_id"] == window_id for nid in ids)

    _cancel(client, user, trip_id, window_id)
    assert all(_node(trip_id, nid)["status"] == "pending" for nid in ids)


def test_cancel_of_ordinary_node_unchanged(client):
    user = "crs-7"
    trip_id = _trip(client, user)
    lunch = _day(trip_id)["lunch"]
    before = {n["node_id"]: n["status"] for n in _stored(trip_id)}
    message = _cancel(client, user, trip_id, lunch["node_id"])
    assert message == f"Canceled {lunch['venue_name']}."
    after = {n["node_id"]: n["status"] for n in _stored(trip_id)}
    assert {k for k in after if after[k] != before[k]} == {lunch["node_id"]}
    assert after[lunch["node_id"]] == "skipped"


def test_completed_stop_stays_completed(client):
    user = "crs-8"
    trip_id = _trip(client, user)
    day = _day(trip_id)
    lunch = day["lunch"]
    window_id, _ids = _excursion(client, user, trip_id)
    _node(trip_id, lunch["node_id"])["status"] = "completed"  # setup: done since

    message = _cancel(client, user, trip_id, window_id)
    assert _node(trip_id, lunch["node_id"])["status"] == "completed"
    assert lunch["venue_name"] not in message


def test_move_and_swap_of_window_node_still_refused(client):
    user = "crs-9"
    trip_id = _trip(client, user)
    window_id, _ids = _excursion(client, user, trip_id)
    mv = _event(
        client,
        user,
        trip_id,
        "move_activity",
        target=window_id,
        preferences={"mode": "move", "target_date": "2026-12-26", "target_slot": "morning_tour"},
    )
    assert mv.status_code == 422, mv.text
    assert mv.json()["detail"]["code"] == "window_node"
    sw = _event(client, user, trip_id, "swap_activity", target=window_id)
    assert sw.status_code == 409, sw.text
    assert sw.json()["detail"]["error"] == "window_node"
