from tests.conftest import auth


def test_free_tier_reroute_limit(client):
    trip_id = client.post(
        "/api/v1/trip/create", headers=auth("u1"),
        json={"start_date": "2026-08-05T09:00:00"},
    ).json()["trip_id"]
    nodes = client.get(f"/api/v1/trip/{trip_id}", headers=auth("u1")).json()["nodes"]
    target = next(n["node_id"] for n in nodes if not n["is_locked"])

    codes = []
    for _ in range(6):  # free tier = 5/day
        codes.append(client.post("/api/v1/trip/event", headers=auth("u1"), json={
            "trip_id": trip_id, "event_type": "cancel_activity",
            "message": "cancel this", "target_node_id": target,
        }).status_code)

    assert codes[:5] == [200] * 5
    assert codes[5] == 403
