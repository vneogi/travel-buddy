"""Regression tests from the 2026-09-05 Windows device run."""

from unittest.mock import patch

from models.schemas import VenueRAG, VenueSearchResult
from services.db_provider import db_service
from tests.conftest import auth


def _create_luang_prabang_trip(client, user: str) -> dict:
    response = client.post(
        "/api/v1/trip/create",
        headers=auth(user),
        json={
            "start_date": "2026-10-06T09:00:00Z",
            "geo_region": "luang_prabang_laos",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_selected_swap_uses_exact_venue_and_preserves_node_id(client):
    user = "sep5-exact-swap"
    trip = _create_luang_prabang_trip(client, user)
    target = trip["nodes"][0]
    itinerary_ids = {node["venue_id"] for node in trip["nodes"]}
    replacement = next(
        row
        for row in db_service.list_venues_for_region("luang_prabang_laos")
        if row["venue_id"] not in itinerary_ids
    )

    response = client.post(
        "/api/v1/trip/event",
        headers=auth(user),
        json={
            "trip_id": trip["trip_id"],
            "event_type": "swap_activity",
            "message": f"Swap {target['venue_name']} for {replacement['name']}",
            "target_node_id": target["node_id"],
            "preferences": {"replacement_venue_id": replacement["venue_id"]},
        },
    )

    assert response.status_code == 200
    updated = response.json()["updated_nodes"]
    replaced = next(node for node in updated if node["node_id"] == target["node_id"])
    assert replaced["venue_id"] == replacement["venue_id"]
    assert replaced["venue_name"] == replacement["name"]
    assert replaced["venue_id"] != target["venue_id"]


def test_same_venue_swap_is_refused_before_quota_consumption(client):
    user = "sep5-same-venue"
    trip = _create_luang_prabang_trip(client, user)
    target = trip["nodes"][0]
    before = client.get("/api/v1/user/status", headers=auth(user)).json()

    response = client.post(
        "/api/v1/trip/event",
        headers=auth(user),
        json={
            "trip_id": trip["trip_id"],
            "event_type": "swap_activity",
            "message": "Swap to the same venue",
            "target_node_id": target["node_id"],
            "preferences": {"replacement_venue_id": target["venue_id"]},
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "same_venue"
    after = client.get("/api/v1/user/status", headers=auth(user)).json()
    assert after["daily_reroutes_used"] == before["daily_reroutes_used"]


def test_unknown_replacement_is_refused_before_quota_consumption(client):
    user = "sep5-missing-replacement"
    trip = _create_luang_prabang_trip(client, user)
    target = trip["nodes"][0]
    before = client.get("/api/v1/user/status", headers=auth(user)).json()

    response = client.post(
        "/api/v1/trip/event",
        headers=auth(user),
        json={
            "trip_id": trip["trip_id"],
            "event_type": "swap_activity",
            "message": "Swap to a venue that disappeared",
            "target_node_id": target["node_id"],
            "preferences": {"replacement_venue_id": "missing-venue-id"},
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "replacement_not_found"
    after = client.get("/api/v1/user/status", headers=auth(user)).json()
    assert after["daily_reroutes_used"] == before["daily_reroutes_used"]


def test_positive_score_delta_discloses_supabase_sponsored_boost(client):
    result = VenueSearchResult(
        venue=VenueRAG(
            venue_id="boosted-from-rpc",
            name="Boosted Partner",
            description="",
            micro_location="Downtown",
            lat=25.1972,
            lng=55.2744,
            # Supabase's RPC adapter cannot populate these private fields.
            is_sponsored=False,
            bid_weight=0.0,
        ),
        similarity_score=0.5,
        final_score=0.62,
    )
    with patch.object(db_service, "hybrid_venue_search", return_value=[result]):
        response = client.get(
            "/api/v1/venues/search",
            params={"query": "nearby activity", "lat": 25.1972, "lng": 55.2744},
            headers=auth("sep5-sponsored"),
        )

    assert response.status_code == 200
    item = response.json()["results"][0]
    assert item["is_sponsored"] is True
    assert item["sponsored_boost_applied"] is True
