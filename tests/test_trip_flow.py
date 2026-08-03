from tests.conftest import auth


def test_event_requires_auth(client):
    r = client.post("/api/v1/trip/event",
                    json={"trip_id": "x", "event_type": "ask_info", "message": "hi"})
    assert r.status_code == 401


def test_create_get_and_light_event(client):
    data = client.post(
        "/api/v1/trip/create", headers=auth("u1"),
        json={"start_date": "2026-08-05T09:00:00", "initial_mood": "relaxed"},
    ).json()
    trip_id = data["trip_id"]
    assert data["locked_count"] >= 1

    r = client.post("/api/v1/trip/event", headers=auth("u1"), json={
        "trip_id": trip_id, "event_type": "ask_info",
        "message": "What is the dress code?",
    })
    assert r.status_code == 200
    assert isinstance(r.json()["message"], str) and r.json()["message"]


def test_event_on_unknown_trip_404(client):
    r = client.post("/api/v1/trip/event", headers=auth("u1"), json={
        "trip_id": "does-not-exist", "event_type": "ask_info", "message": "hi",
    })
    assert r.status_code == 404
