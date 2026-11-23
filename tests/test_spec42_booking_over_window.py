"""SPEC-42: a non-hotel booking inside an active excursion window is refused.

All through POST /api/v1/trip/event. Excursions are created through the real
add flow (review, then confirm_skip_node_ids). Booking times are naive
destination-local wall time; Zanzibar is UTC+3.
"""

import copy
from datetime import datetime, timedelta, timezone

import services.db_provider as dbp
from models.schemas import TripNode
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
    return dbp.db_service._trips[trip_id]


def _node(trip_id, node_id):
    return next(n for n in _stored(trip_id)["nodes"] if n["node_id"] == node_id)


def _excursion(client, user, trip_id, window="morning"):
    prefs = {"mode": "uncatalogued_add", "name": WINDOW, "target_date": DAY, "time_window": window}
    review = _event(client, user, trip_id, "add_activity", preferences=prefs)
    assert review.status_code == 200, review.text
    ids = review.json()["excursion_review"]["skip_node_ids"]
    done = _event(
        client, user, trip_id, "add_activity", preferences={**prefs, "confirm_skip_node_ids": ids}
    )
    assert done.status_code == 200, done.text
    return next(n for n in _stored(trip_id)["nodes"] if n.get("time_window") == window)


def _local(utc_iso):
    """UTC ISO string -> naive Zanzibar wall time string (UTC+3)."""
    utc = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    return (utc + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S")


def _window_bounds(window_node):
    start = datetime.fromisoformat(window_node["scheduled_start"].replace("Z", "+00:00"))
    end = start + timedelta(minutes=window_node["duration_minutes"])
    return start, end


def _book(client, user, trip_id, booking_type, local_start, minutes, name=None):
    return _event(
        client,
        user,
        trip_id,
        "add_booking",
        preferences={
            "venue_name": name or f"{booking_type} booking",
            "booking_type": booking_type,
            "scheduled_start": local_start,
            "duration_minutes": minutes,
        },
    )


def _assert_refused(r, trip_id, before):
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "booking_refused"
    assert WINDOW in detail["message"]
    assert "(morning, 2026-12-27)" in detail["message"]
    assert "Cancel the excursion first" in detail["message"]
    assert _stored(trip_id) == before


def _booking_ids(trip_id):
    return {n["node_id"] for n in _stored(trip_id)["nodes"] if n.get("node_kind") == "booking"}


def test_tour_inside_active_window_is_refused(client):
    user = "bow-1"
    trip_id = _trip(client, user)
    _excursion(client, user, trip_id)
    before = copy.deepcopy(_stored(trip_id))
    r = _book(client, user, trip_id, "tour", f"{DAY}T10:00:00", 60)
    _assert_refused(r, trip_id, before)
    assert _stored(trip_id)["version"] == before["version"]


def test_flight_inside_active_window_is_refused(client):
    user = "bow-2"
    trip_id = _trip(client, user)
    _excursion(client, user, trip_id)
    before = copy.deepcopy(_stored(trip_id))
    r = _book(client, user, trip_id, "flight", f"{DAY}T12:00:00", 90)
    _assert_refused(r, trip_id, before)


def test_hotel_inside_active_window_is_accepted(client):
    user = "bow-3"
    trip_id = _trip(client, user)
    _excursion(client, user, trip_id)
    r = _book(client, user, trip_id, "hotel", f"{DAY}T10:00:00", 20 * 60)
    assert r.status_code == 200, r.text
    assert any(n.get("booking_type") == "hotel" for n in _stored(trip_id)["nodes"])


def test_tour_inside_cancelled_window_is_accepted(client):
    user = "bow-4"
    trip_id = _trip(client, user)
    window = _excursion(client, user, trip_id)
    cancel = _event(client, user, trip_id, "cancel_activity", target=window["node_id"])
    assert cancel.status_code == 200, cancel.text
    assert _node(trip_id, window["node_id"])["status"] == "skipped"
    r = _book(client, user, trip_id, "tour", f"{DAY}T10:00:00", 60)
    assert r.status_code == 200, r.text


def test_booking_touching_window_edges_is_accepted(client):
    user = "bow-5"
    trip_id = _trip(client, user)
    w_start, w_end = _window_bounds(_excursion(client, user, trip_id))
    ends_at_start = _local((w_start - timedelta(minutes=60)).isoformat())
    starts_at_end = _local(w_end.isoformat())
    r1 = _book(client, user, trip_id, "tour", ends_at_start, 60, name="Early tour")
    assert r1.status_code == 200, r1.text
    r2 = _book(client, user, trip_id, "tour", starts_at_end, 60, name="Late tour")
    assert r2.status_code == 200, r2.text


def _outside_booking(client, user, trip_id, local_start, minutes=60):
    before = _booking_ids(trip_id)
    r = _book(client, user, trip_id, "tour", local_start, minutes, name="Snorkel trip")
    assert r.status_code == 200, r.text
    (booking_id,) = _booking_ids(trip_id) - before
    return booking_id


def test_edit_time_into_window_is_refused_and_nothing_changes(client):
    user = "bow-6"
    trip_id = _trip(client, user)
    _excursion(client, user, trip_id)
    booking_id = _outside_booking(client, user, trip_id, f"{DAY}T16:00:00")
    before = copy.deepcopy(_node(trip_id, booking_id))
    r = _event(
        client,
        user,
        trip_id,
        "edit_booking",
        target=booking_id,
        preferences={
            "venue_name": "Renamed tour",
            "scheduled_start": f"{DAY}T10:00:00",
            "duration_minutes": 60,
            "booking_type": "tour",
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["error"] == "booking_refused"
    assert "Cancel the excursion first" in r.json()["detail"]["message"]
    after = _node(trip_id, booking_id)
    assert after["scheduled_start"] == before["scheduled_start"]
    assert after["duration_minutes"] == before["duration_minutes"]
    assert after["venue_name"] == before["venue_name"] == "Snorkel trip"


def test_edit_duration_into_window_is_refused(client):
    user = "bow-7"
    trip_id = _trip(client, user)
    w_start, _w_end = _window_bounds(_excursion(client, user, trip_id))
    local_start = _local((w_start - timedelta(minutes=60)).isoformat())
    booking_id = _outside_booking(client, user, trip_id, local_start, 60)
    r = _event(
        client,
        user,
        trip_id,
        "edit_booking",
        target=booking_id,
        preferences={
            "venue_name": "Snorkel trip",
            "scheduled_start": local_start,
            "duration_minutes": 180,
            "booking_type": "tour",
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["error"] == "booking_refused"
    assert _node(trip_id, booking_id)["duration_minutes"] == 60


def _pre_slice_overlap(trip_id):
    """Setup only: a tour booking already inside the window, as stored before
    this slice (add_booking would now refuse it)."""
    start = datetime(2026, 12, 27, 7, 0, tzinfo=timezone.utc)  # 10:00 local
    node = TripNode(
        venue_name="Old tour",
        scheduled_start=start,
        duration_minutes=60,
        is_locked=True,
        node_kind="booking",
        booking_type="tour",
        geo_region=GEO,
    )
    nodes = _stored(trip_id)["nodes"]
    nodes.append(node.model_dump(mode="json"))
    nodes.sort(key=lambda n: n["scheduled_start"])
    return node.node_id


def test_notes_and_title_edit_of_pre_slice_overlap_is_accepted(client):
    user = "bow-8"
    trip_id = _trip(client, user)
    _excursion(client, user, trip_id)
    booking_id = _pre_slice_overlap(trip_id)
    # The sheet resends every field: identical time, duration and type.
    r = _event(
        client,
        user,
        trip_id,
        "edit_booking",
        target=booking_id,
        preferences={
            "venue_name": "Old tour (fixed)",
            "scheduled_start": f"{DAY}T10:00:00",
            "duration_minutes": 60,
            "booking_type": "tour",
            "booking_notes": "Meet at the jetty",
        },
    )
    assert r.status_code == 200, r.text
    node = _node(trip_id, booking_id)
    assert node["venue_name"] == "Old tour (fixed)"
    assert node["booking_notes"] == "Meet at the jetty"


def test_type_change_of_pre_slice_overlap_is_refused(client):
    user = "bow-8b"
    trip_id = _trip(client, user)
    _excursion(client, user, trip_id)
    booking_id = _pre_slice_overlap(trip_id)
    r = _event(
        client,
        user,
        trip_id,
        "edit_booking",
        target=booking_id,
        preferences={
            "venue_name": "Old tour",
            "scheduled_start": f"{DAY}T10:00:00",
            "duration_minutes": 60,
            "booking_type": "flight",
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["error"] == "booking_refused"
    assert _node(trip_id, booking_id)["booking_type"] == "tour"


def test_refusal_takes_no_reroute_quota(client):
    user = "bow-9"
    trip_id = _trip(client, user)
    _excursion(client, user, trip_id)
    status_before = client.get("/api/v1/user/status", headers=auth(user)).json()
    # On this slice the booking is refused (see test 1); either way, add
    # booking never touches the reroute quota.
    r = _book(client, user, trip_id, "tour", f"{DAY}T10:00:00", 60)
    assert r.status_code in (200, 422), r.text
    assert client.get("/api/v1/user/status", headers=auth(user)).json() == status_before
