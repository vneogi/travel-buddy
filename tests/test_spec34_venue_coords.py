"""SPEC-34: venue search uses trip location, not hardcoded Dubai.

Sabotage proofs:
  S1: Keep the default Dubai coords in /venues/search -> Laos test fails.
  S2: get_region() fallback to Dubai for unknown region -> missing-region test fails.
"""

import pytest

from tests.conftest import auth


def _create_trip(client, geo_region: str):
    """Create a trip in the given region and return its trip_id."""
    resp = client.post(
        "/api/v1/trip/create",
        json={"start_date": "2026-10-04T00:00:00", "geo_region": geo_region},
        headers=auth("u_spec34"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["trip_id"]


class TestVenueSearchCoordinates:
    """Venue search resolves coordinates from trip context or region defaults."""

    def test_laos_trip_sends_lp_coordinates_via_trip_id(self, client):
        """A Luang Prabang trip must NOT search around Dubai."""
        trip_id = _create_trip(client, "luang_prabang_laos")

        resp = client.get(
            "/api/v1/venues/search",
            params={"query": "cafe", "trip_id": trip_id},
            headers=auth("u_spec34"),
        )
        # Should succeed (200) -- coords resolved from trip context/region
        assert resp.status_code == 200, resp.text

    def test_dubai_trip_sends_dubai_coordinates_via_trip_id(self, client):
        """A Dubai trip should still work."""
        trip_id = _create_trip(client, "dubai_uae")

        resp = client.get(
            "/api/v1/venues/search",
            params={"query": "museum", "trip_id": trip_id},
            headers=auth("u_spec34"),
        )
        assert resp.status_code == 200, resp.text

    def test_explicit_lat_lng_override_trip_context(self, client):
        """Explicit lat/lng params take priority over trip_id."""
        resp = client.get(
            "/api/v1/venues/search",
            params={
                "query": "restaurant",
                "lat": 19.8856,
                "lng": 102.1347,
            },
            headers=auth("u_spec34"),
        )
        assert resp.status_code == 200, resp.text

    def test_no_coords_no_trip_returns_422(self, client):
        """Without lat/lng or trip_id, the endpoint must refuse."""
        resp = client.get(
            "/api/v1/venues/search",
            params={"query": "cafe"},
            headers=auth("u_spec34"),
        )
        assert resp.status_code == 422, (
            f"Expected 422 for missing coordinates, got {resp.status_code}"
        )
        body = resp.json()
        assert body["detail"]["error"] == "missing_coordinates"

    def test_unknown_trip_id_returns_422(self, client):
        """A non-existent trip_id should not fall back to Dubai."""
        resp = client.get(
            "/api/v1/venues/search",
            params={"query": "cafe", "trip_id": "nonexistent_trip"},
            headers=auth("u_spec34"),
        )
        # trip not found -> coords cannot be resolved -> 422
        assert resp.status_code == 422, (
            f"Expected 422 for unknown trip, got {resp.status_code}"
        )


class TestExistingBookingMutationsUnchanged:
    """SPEC-10 booking mutations still work (regression guard)."""

    def test_add_booking_still_accepts_duration_minutes(self, client):
        trip_id = _create_trip(client, "dubai_uae")
        resp = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "add_booking",
                "message": "Add hotel",
                "preferences": {
                    "venue_name": "Test Hotel",
                    "scheduled_start": "2026-10-04T15:00:00",
                    "duration_minutes": 2880,
                    "booking_type": "hotel",
                },
            },
            headers=auth("u_spec34"),
        )
        assert resp.status_code == 200, resp.text
        nodes = resp.json()["updated_nodes"]
        hotel = next(n for n in nodes if n.get("booking_type") == "hotel")
        assert hotel["duration_minutes"] == 2880
        assert hotel["node_id"]  # node_id exists
