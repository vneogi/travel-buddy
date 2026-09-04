from tests.conftest import auth


def test_event_requires_auth(client):
    r = client.post(
        "/api/v1/trip/event", json={"trip_id": "x", "event_type": "ask_info", "message": "hi"}
    )
    assert r.status_code == 401


def test_create_get_and_light_event(client):
    data = client.post(
        "/api/v1/trip/create",
        headers=auth("u1"),
        json={"start_date": "2026-08-05T09:00:00", "initial_mood": "relaxed"},
    ).json()
    trip_id = data["trip_id"]
    assert 4 <= len(data["nodes"]) <= 6

    r = client.post(
        "/api/v1/trip/event",
        headers=auth("u1"),
        json={
            "trip_id": trip_id,
            "event_type": "ask_info",
            "message": "What is the dress code?",
        },
    )
    assert r.status_code == 200
    assert isinstance(r.json()["message"], str) and r.json()["message"]


def test_trip_list_returns_only_callers_lightweight_projection(client):
    own = client.post(
        "/api/v1/trip/create",
        headers=auth("u1"),
        json={"start_date": "2026-10-04T09:00:00"},
    ).json()
    client.post(
        "/api/v1/trip/create",
        headers=auth("u2"),
        json={"start_date": "2026-10-05T09:00:00"},
    )

    response = client.get("/api/v1/trips", headers=auth("u1"))

    assert response.status_code == 200
    body = response.json()
    assert body["supported_regions"]
    assert "state_json" not in body
    trips = body["trips"]
    assert [trip["trip_id"] for trip in trips] == [own["trip_id"]]
    assert set(trips[0]) == {
        "trip_id",
        "geo_region",
        "starts_at",
        "ends_at",
        "node_count",
        "booking_count",
        "updated_at",
    }
    assert 4 <= trips[0]["node_count"] <= 6
    assert "nodes" not in trips[0]
    assert "user_id" not in trips[0]


def test_trip_list_requires_auth(client):
    response = client.get("/api/v1/trips")
    assert response.status_code == 401


def test_trip_list_empty_state_for_user_without_trips(client):
    response = client.get("/api/v1/trips", headers=auth("new-user"))
    assert response.status_code == 200
    assert response.json()["trips"] == []


def test_create_rejects_unconfigured_region_honestly(client):
    response = client.post(
        "/api/v1/trip/create",
        headers=auth("u1"),
        json={
            "start_date": "2026-10-04T09:00:00",
            "geo_region": "unsupported_nowhere",
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "unsupported_region"


def test_booking_anchor_remains_on_same_trip_after_fetch(client):
    created = client.post(
        "/api/v1/trip/create",
        headers=auth("u1"),
        json={"start_date": "2026-10-04T09:00:00"},
    ).json()
    trip_id = created["trip_id"]

    added = client.post(
        "/api/v1/trip/event",
        headers=auth("u1"),
        json={
            "trip_id": trip_id,
            "event_type": "add_booking",
            "message": "Add booking anchor",
            "preferences": {
                "venue_name": "Mad Monkey Vang Vieng",
                "scheduled_start": "2026-10-04T14:00:00+07:00",
                "duration_minutes": 2760,
                "booking_type": "hotel",
                "import_source": "email",
                "geo_region": "vang_vieng_laos",
            },
        },
    )
    assert added.status_code == 200

    second = client.post(
        "/api/v1/trip/event",
        headers=auth("u1"),
        json={
            "trip_id": trip_id,
            "event_type": "add_booking",
            "message": "Add booking anchor",
            "preferences": {
                "venue_name": "Train to Luang Prabang",
                "scheduled_start": "2026-10-06T15:00:00+07:00",
                "duration_minutes": 120,
                "booking_type": "train",
                "import_source": "manual",
            },
        },
    )
    assert second.status_code == 200

    fetched = client.get(f"/api/v1/trip/{trip_id}", headers=auth("u1"))
    hotel = next(
        node for node in fetched.json()["nodes"] if node["venue_name"] == "Mad Monkey Vang Vieng"
    )
    assert hotel["node_kind"] == "booking"
    assert hotel["booking_type"] == "hotel"
    assert hotel["is_locked"] is True
    assert hotel["geo_region"] == "vang_vieng_laos"
    booking_names = {
        node["venue_name"] for node in fetched.json()["nodes"] if node["node_kind"] == "booking"
    }
    assert {"Mad Monkey Vang Vieng", "Train to Luang Prabang"} <= booking_names


def test_event_on_unknown_trip_404(client):
    r = client.post(
        "/api/v1/trip/event",
        headers=auth("u1"),
        json={
            "trip_id": "does-not-exist",
            "event_type": "ask_info",
            "message": "hi",
        },
    )
    assert r.status_code == 404
