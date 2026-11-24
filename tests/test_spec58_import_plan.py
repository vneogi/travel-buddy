"""SPEC-58 slice 1a: add_activity mode=import_plan and start_empty create."""

import pytest

import services.db_provider as dbp
from tests.conftest import auth

GEO = "zanzibar_tanzania"


def _seed(monkeypatch, *rows):
    """Setup only: add venues to the in-memory catalog for this test."""
    monkeypatch.setattr(dbp.db_service, "_venues", list(dbp.db_service._venues) + list(rows))


def _row(venue_id, name, names_local=None):
    return {
        "venue_id": venue_id,
        "name": name,
        "geo_region": GEO,
        "names_local": names_local,
        "category": "experience",
        "typical_dwell_minutes": 60,
    }


D1, D2 = "2026-12-27", "2026-12-28"


def _empty_trip(client, user, start="2026-12-27", end="2026-12-28"):
    r = client.post(
        "/api/v1/trip/create",
        headers=auth(user),
        json={"geo_region": GEO, "start_date": start, "end_date": end, "start_empty": True},
    )
    assert r.status_code == 200, r.text
    return r.json()["trip_id"]


def _candidate(client, user, trip_id, day, slot, used=()):
    r = client.get(
        f"/api/v1/trip/{trip_id}/add_candidates",
        headers=auth(user),
        params={"target_date": day, "target_slot": slot},
    )
    assert r.status_code == 200, r.text
    cands = [c["venue_id"] for c in r.json()["candidates"] if c["venue_id"] not in used]
    assert cands, (day, slot)
    return cands[0]


def _import(client, user, trip_id, items):
    return client.post(
        "/api/v1/trip/event",
        headers=auth(user),
        json={
            "trip_id": trip_id,
            "event_type": "add_activity",
            "message": "import",
            "preferences": {"mode": "import_plan", "items": items},
        },
    )


def _cat(venue_id, day, slot):
    return {"kind": "catalog", "venue_id": venue_id, "target_date": day, "target_slot": slot}


def _plain(name, day, slot, dwell=60):
    item = {"kind": "plain", "name": name, "target_date": day, "target_slot": slot}
    if dwell is not None:
        item["typical_dwell_minutes"] = dwell
    return item


def _reroutes(uid):
    return dbp.db_service.get_or_create_user(uid).daily_reroute_count


def _stored(trip_id):
    return dbp.db_service._trips[trip_id]


def test_batch_lands_with_one_version_bump_and_one_reroute(client):
    user = "ip-9"
    trip_id = _empty_trip(client, user)
    # Catalog stops share day 1; the plain stop has day 2 to itself (a
    # trip-private stop with no coordinates is only placeable on an empty day).
    used = []
    for slot in ("morning_tour", "lunch", "dinner"):
        used.append(_candidate(client, user, trip_id, D1, slot, used=used))
    items = [
        _cat(used[0], D1, "morning_tour"),
        _cat(used[1], D1, "lunch"),
        _cat(used[2], D1, "dinner"),
        _plain("Sunset jetty", D2, "dinner"),
    ]
    v0, q0 = _stored(trip_id)["version"], _reroutes(user)
    r = _import(client, user, trip_id, items)
    assert r.status_code == 200, r.text
    results = r.json()["import_results"]
    assert [x["status"] for x in results] == ["added"] * 4
    assert [x["index"] for x in results] == [0, 1, 2, 3]
    assert _stored(trip_id)["version"] == v0 + 1
    assert _reroutes(user) == q0 + 1
    assert len(_stored(trip_id)["nodes"]) == 4


def test_refused_item_is_reported_while_others_land(client):
    user = "ip-10"
    trip_id = _empty_trip(client, user)
    morning = _candidate(client, user, trip_id, D1, "morning_tour")
    items = [
        _cat(morning, D1, "morning_tour"),
        _plain("Second breakfast spot", D1, "morning_tour"),
        _plain("Harbour walk", D2, "afternoon_evening_tour"),
    ]
    r = _import(client, user, trip_id, items)
    assert r.status_code == 200, r.text
    results = r.json()["import_results"]
    assert results[0]["status"] == "added"
    assert results[1]["status"] == "refused" and results[1]["code"] == "occupied"
    assert results[1]["message"] and results[1]["node_id"] is None
    assert results[2]["status"] == "added"


def test_all_refused_persists_nothing_and_uses_no_quota(client):
    user = "ip-11"
    trip_id = _empty_trip(client, user)
    before = dict(_stored(trip_id))
    q0 = _reroutes(user)
    r = _import(
        client,
        user,
        trip_id,
        [_plain("Far away", "2027-03-01", "lunch"), _plain("Also far", "2027-03-02", "dinner")],
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "import_plan_refused"
    assert [x["code"] for x in detail["results"]] == ["invalid_date", "invalid_date"]
    assert _stored(trip_id)["version"] == before["version"]
    assert _stored(trip_id)["nodes"] == []
    assert _reroutes(user) == q0


def test_plain_item_is_trip_private_with_posted_dwell_and_no_catalog_write(client, monkeypatch):
    user = "ip-12"
    trip_id = _empty_trip(client, user)
    venues_before = list(dbp.db_service._venues)

    def _no_write(*args, **kwargs):
        raise AssertionError("catalog write attempted")

    monkeypatch.setattr(dbp.db_service, "add_venue", _no_write)
    r = _import(client, user, trip_id, [_plain("Sunset jetty", D1, "dinner", dwell=75)])
    assert r.status_code == 200, r.text
    node_id = r.json()["import_results"][0]["node_id"]
    node = next(n for n in _stored(trip_id)["nodes"] if n["node_id"] == node_id)
    assert node["venue_id"] is None
    assert node["place_source"] == "trip_private"
    assert node["duration_minutes"] == 75
    assert node.get("opening_hours") is None and node.get("opening_hours_structured") is None
    assert dbp.db_service._venues == venues_before


def test_plain_item_colliding_with_catalog_name_is_refused(client):
    user = "ip-13"
    trip_id = _empty_trip(client, user)
    r = _import(
        client,
        user,
        trip_id,
        [_plain("  house of WONDERS ", D1, "lunch"), _plain("Harbour walk", D2, "lunch")],
    )
    assert r.status_code == 200, r.text
    results = r.json()["import_results"]
    assert results[0]["code"] == "catalog_match" and results[0]["status"] == "refused"
    assert results[1]["status"] == "added"


@pytest.mark.parametrize(
    "items",
    [
        [_plain(f"Stop {i}", D1, "lunch") for i in range(61)],
        [_plain("No dwell given", D1, "lunch", dwell=None)],
        [{"kind": "hotel", "name": "Nope", "target_date": D1, "target_slot": "lunch"}],
        [],
    ],
)
def test_invalid_batches_are_refused_before_persist(client, items):
    user = "ip-14"
    trip_id = _empty_trip(client, user)
    v0 = _stored(trip_id)["version"]
    r = _import(client, user, trip_id, items)
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "invalid_items"
    assert _stored(trip_id)["version"] == v0 and _stored(trip_id)["nodes"] == []


def test_single_item_direct_add_unchanged(client):
    user = "ip-15"
    trip_id = _empty_trip(client, user)
    venue = _candidate(client, user, trip_id, D1, "morning_tour")
    q0 = _reroutes(user)
    r = client.post(
        "/api/v1/trip/event",
        headers=auth(user),
        json={
            "trip_id": trip_id,
            "event_type": "add_activity",
            "message": "add",
            "preferences": {
                "mode": "direct_add",
                "venue_id": venue,
                "target_date": D1,
                "target_slot": "morning_tour",
            },
        },
    )
    assert r.status_code == 200, r.text
    assert r.json().get("import_results") is None
    assert _reroutes(user) == q0 + 1


def test_start_empty_creates_zero_nodes_and_loads(client):
    user = "ip-16"
    trip_id = _empty_trip(client, user, start="2026-12-25", end="2026-12-29")
    assert _stored(trip_id)["nodes"] == []
    got = client.get(f"/api/v1/trip/{trip_id}", headers=auth(user))
    assert got.status_code == 200, got.text
    assert got.json()["nodes"] == []
    ctx = got.json().get("creation_context") or {}
    assert ctx.get("start_date_local") == "2026-12-25" and ctx.get("end_date_local") == "2026-12-29"


def test_create_without_start_empty_unchanged_and_unsupported_paths_refused(client):
    user = "ip-17"
    normal = client.post(
        "/api/v1/trip/create",
        headers=auth(user),
        json={"geo_region": GEO, "start_date": "2026-12-25", "end_date": "2026-12-26"},
    )
    assert normal.status_code == 200, normal.text
    assert _stored(normal.json()["trip_id"])["nodes"] != []
    trips_before = len(dbp.db_service._trips)
    for body in (
        {"geo_region": GEO, "start_date": "2026-12-25", "start_empty": True},
        {
            "segments": [{"geo_region": GEO, "starts_on": "2026-12-25", "ends_on": "2026-12-26"}],
            "start_empty": True,
        },
    ):
        r = client.post("/api/v1/trip/create", headers=auth(user), json=body)
        assert r.status_code == 422, r.text
        assert r.json()["detail"]["error"] == "start_empty_unsupported"
    assert len(dbp.db_service._trips) == trips_before


def test_empty_trip_accepts_an_import_plan_batch(client):
    user = "ip-18"
    trip_id = _empty_trip(client, user)
    r = _import(
        client,
        user,
        trip_id,
        [
            _plain("Harbour walk", D1, "afternoon_evening_tour"),
            _plain("Night swim", D2, "dinner", dwell=45),
        ],
    )
    assert r.status_code == 200, r.text
    assert [x["status"] for x in r.json()["import_results"]] == ["added", "added"]


def test_import_refuses_accent_folded_catalog_name_but_single_add_unchanged(client, monkeypatch):
    user = "ip-20"
    trip_id = _empty_trip(client, user)
    _seed(monkeypatch, _row("znz-test-lumiere", "Caf\u00e9 Lumi\u00e8re Test"))
    r = _import(
        client,
        user,
        trip_id,
        [_plain("Cafe Lumiere Test", D1, "lunch"), _plain("Harbour walk", D2, "lunch")],
    )
    assert r.status_code == 200, r.text
    results = r.json()["import_results"]
    assert results[0]["status"] == "refused" and results[0]["code"] == "catalog_match"
    single = client.post(
        "/api/v1/trip/event",
        headers=auth(user),
        json={
            "trip_id": trip_id,
            "event_type": "add_activity",
            "message": "add",
            "preferences": {
                "mode": "uncatalogued_add",
                "name": "Cafe Lumiere Test",
                "target_date": D1,
                "target_slot": "dinner",
                "typical_dwell_minutes": 60,
            },
        },
    )
    assert single.status_code == 200, single.text
