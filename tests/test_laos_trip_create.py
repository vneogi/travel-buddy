"""SPEC-32 catalog-backed trip creation.

Sabotage proofs:
  S1: Stamp geo_region onto Dubai fixture names -> names/bbox assertions fail
  S2: Allow unknown region without 422 -> test_create_rejects_unknown_region fails
  S3: Silent get_region Dubai fallback as allowlist -> unknown region becomes Dubai
  S4: Call LLM or consume_reroute on create -> quota/LLM tests fail
  S5: Non-deterministic pick -> repeated create sequence test fails
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from config.regions import REGIONS, require_region
from services.catalog_itinerary import DUBAI_FIXTURE_NAMES, InsufficientCatalog, select_day_venues
from services.db_provider import db_service
from tests.conftest import auth

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LAOS_FILES = {
    "luang_prabang_laos": DATA_DIR / "laos_luang_prabang.json",
    "vang_vieng_laos": DATA_DIR / "laos_vang_vieng.json",
    "vientiane_laos": DATA_DIR / "laos_vientiane.json",
}
LAOS_BBOX = {
    "luang_prabang_laos": (13.9, 22.6, 100.0, 107.8),
    "vang_vieng_laos": (13.9, 22.6, 100.0, 107.8),
    "vientiane_laos": (13.9, 22.6, 100.0, 107.8),
}


def _catalog_names(geo_region: str) -> set[str]:
    payload = json.loads(LAOS_FILES[geo_region].read_text(encoding="utf-8"))
    return {row["name"] for row in payload["venues"]}


def test_require_region_unknown_does_not_return_dubai():
    try:
        require_region("paris_france")
        raise AssertionError("expected KeyError")
    except KeyError:
        pass
    assert "paris_france" not in REGIONS


def test_select_day_venues_raises_when_catalog_too_small():
    try:
        select_day_venues([{"name": "Only One", "category": "cafe", "lat": 1, "lng": 2}])
        raise AssertionError("expected InsufficientCatalog")
    except InsufficientCatalog:
        pass


def test_trips_advertise_laos_and_dubai(client):
    body = client.get("/api/v1/trips", headers=auth("u1")).json()
    regions = body["supported_regions"]
    assert regions[0] == "dubai_uae"
    assert set(regions) >= {
        "dubai_uae",
        "luang_prabang_laos",
        "vang_vieng_laos",
        "vientiane_laos",
    }


def test_create_rejects_unknown_region_and_does_not_fallback_to_dubai(client):
    response = client.post(
        "/api/v1/trip/create",
        headers=auth("u1"),
        json={"start_date": "2026-10-04T09:00:00", "geo_region": "paris_france"},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"] == "unsupported_region"
    assert "paris_france" not in detail.get("supported_regions", [])
    assert "Dubai Museum" not in response.text


def test_empty_catalog_region_is_not_advertised_and_refuses(client):
    original = db_service.list_venues_for_region

    def _empty_luang(geo_region: str):
        if geo_region == "luang_prabang_laos":
            return []
        return original(geo_region)

    with patch.object(db_service, "list_venues_for_region", side_effect=_empty_luang):
        listed = client.get("/api/v1/trips", headers=auth("empty-user")).json()
        assert "luang_prabang_laos" not in listed["supported_regions"]
        response = client.post(
            "/api/v1/trip/create",
            headers=auth("empty-user"),
            json={
                "start_date": "2026-10-04T09:00:00",
                "geo_region": "luang_prabang_laos",
            },
        )
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "unsupported_region"


def _assert_laos_trip(body: dict, geo_region: str) -> None:
    names = [node["venue_name"] for node in body["nodes"]]
    assert 4 <= len(names) <= 6
    catalog = _catalog_names(geo_region)
    assert set(names) <= catalog
    assert not (set(names) & DUBAI_FIXTURE_NAMES)
    south, north, west, east = LAOS_BBOX[geo_region]
    for node in body["nodes"]:
        assert node["geo_region"] == geo_region
        assert node.get("venue_id")
        assert south <= node["lat"] <= north
        assert west <= node["lng"] <= east
        assert "hospital" not in (node.get("venue_name") or "").lower()


def test_create_laos_cities_use_catalog_not_dubai_template(client):
    for geo_region in LAOS_FILES:
        created = client.post(
            "/api/v1/trip/create",
            headers=auth(f"laos-{geo_region}"),
            json={"start_date": "2026-10-05T09:00:00", "geo_region": geo_region},
        )
        assert created.status_code == 200, created.text
        body = created.json()
        _assert_laos_trip(body, geo_region)
        fetched = client.get(
            f"/api/v1/trip/{body['trip_id']}",
            headers=auth(f"laos-{geo_region}"),
        ).json()
        region_meta = REGIONS[geo_region]
        assert fetched["geo_region"] == geo_region
        assert fetched["current_context"]["location_lat"] == region_meta.default_lat
        assert fetched["current_context"]["location_lng"] == region_meta.default_lng
        _assert_laos_trip({"nodes": fetched["nodes"]}, geo_region)


def test_create_laos_sequence_is_stable(client):
    first = client.post(
        "/api/v1/trip/create",
        headers=auth("stable-1"),
        json={"start_date": "2026-10-05T09:00:00", "geo_region": "luang_prabang_laos"},
    ).json()
    second = client.post(
        "/api/v1/trip/create",
        headers=auth("stable-2"),
        json={"start_date": "2026-10-05T09:00:00", "geo_region": "luang_prabang_laos"},
    ).json()
    assert [n["venue_name"] for n in first["nodes"]] == [n["venue_name"] for n in second["nodes"]]
    assert [n["venue_id"] for n in first["nodes"]] == [n["venue_id"] for n in second["nodes"]]


def test_create_does_not_consume_quota_or_call_llm(client):
    before = db_service.get_or_create_user("quota-user").daily_reroute_count
    with patch(
        "services.llm_service.llm_service.generate_itinerary_response",
        new_callable=AsyncMock,
    ) as generate:
        created = client.post(
            "/api/v1/trip/create",
            headers=auth("quota-user"),
            json={"start_date": "2026-10-05T09:00:00", "geo_region": "vang_vieng_laos"},
        )
    assert created.status_code == 200
    generate.assert_not_awaited()
    after = db_service.get_or_create_user("quota-user").daily_reroute_count
    assert after == before


def test_create_does_not_use_hybrid_search(client):
    with patch.object(db_service, "hybrid_venue_search") as search:
        created = client.post(
            "/api/v1/trip/create",
            headers=auth("search-user"),
            json={"start_date": "2026-10-05T09:00:00", "geo_region": "vientiane_laos"},
        )
    assert created.status_code == 200
    search.assert_not_called()
