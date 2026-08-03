from tests.conftest import auth


def test_health_is_public(client):
    assert client.get("/api/v1/health").status_code == 200


def test_user_status_requires_auth(client):
    assert client.get("/api/v1/user/status").status_code == 401


def test_user_status_with_dev_auth(client):
    r = client.get("/api/v1/user/status", headers=auth("u1"))
    assert r.status_code == 200
    assert r.json()["user_id"] == "u1"
    assert r.json()["tier"] == "free"


def test_trip_ownership_enforced(client):
    trip_id = client.post(
        "/api/v1/trip/create", headers=auth("u1"),
        json={"start_date": "2026-08-05T09:00:00"},
    ).json()["trip_id"]
    assert client.get(f"/api/v1/trip/{trip_id}", headers=auth("u1")).status_code == 200
    # A different user must NOT be able to read it.
    assert client.get(f"/api/v1/trip/{trip_id}", headers=auth("u2")).status_code == 403


def test_free_upgrade_endpoint_removed(client):
    r = client.post("/api/v1/user/u1/upgrade", headers=auth("u1"))
    assert r.status_code in (404, 405)
