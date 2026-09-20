"""SPEC-10 hotel stay display: dual timestamps, lat/lng persistence, catalog match.

Required proofs from the brief:
- hotel 18:02 local 2 Oct check-in / 15:00 local 3 Oct check-out renders both times
- add_booking with lat/lng persists; hotel-return uses them
- add_booking without lat/lng still saves; hotel-return stays ineligible
- catalog name-match copies that venue only
- booking local-time tests still pass (covered by existing test_spec10_booking_local_time.py)
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from models.schemas import NodeStatus, TripNode
from services.booking_constraints import (
    hotel_covered_dates,
    violates_hotel_return,
)
from services.catalog_name_match import catalog_coords_for_name
from services.destination_tz import to_destination_local

VTN = "vientiane_laos"
VTN_TZ = ZoneInfo("Asia/Vientiane")  # UTC+7


def _vtn_trip_body():
    return {
        "start_date": "2026-10-02T09:00:00",
        "geo_region": VTN,
    }


# ---------------------------------------------------------------------------
# Proof 1: Hotel dual timestamps -- check-in 18:02 local, check-out 15:00 next day
# ---------------------------------------------------------------------------


class TestHotelDualTimestamps:
    def test_hotel_1802_checkin_1500_checkout_both_render(self, client):
        """Hotel check-in 18:02 local 2 Oct, check-out 15:00 local 3 Oct.
        Both times must be in the response node, derivable from
        scheduled_start and duration_minutes."""
        from tests.conftest import auth

        created = client.post(
            "/api/v1/trip/create",
            headers=auth("dual-ts-user"),
            json=_vtn_trip_body(),
        )
        assert created.status_code == 200
        trip_id = created.json()["trip_id"]

        # 18:02 local Oct 2 = 11:02 UTC Oct 2
        # 15:00 local Oct 3 = 08:00 UTC Oct 3
        # Duration = 20h58m = 1258 min
        resp = client.post(
            "/api/v1/trip/event",
            headers=auth("dual-ts-user"),
            json={
                "trip_id": trip_id,
                "event_type": "add_booking",
                "message": "Hotel stay",
                "preferences": {
                    "venue_name": "Dhavara Boutique Hotel",
                    "booking_type": "hotel",
                    "scheduled_start": "2026-10-02T18:02:00",
                    "duration_minutes": 1258,
                    "lat": 17.976,
                    "lng": 102.633,
                    "geo_region": VTN,
                },
            },
        )
        assert resp.status_code == 200
        hotel = next(n for n in resp.json()["updated_nodes"] if n.get("booking_type") == "hotel")

        # Check-in: 18:02 local Oct 2
        stored_utc = datetime.fromisoformat(hotel["scheduled_start"].replace("Z", "+00:00"))
        checkin_local = to_destination_local(stored_utc, VTN)
        assert checkin_local.hour == 18
        assert checkin_local.minute == 2
        assert checkin_local.date() == date(2026, 10, 2)

        # Check-out: scheduled_start + duration_minutes = 15:00 local Oct 3
        checkout_utc = stored_utc + timedelta(minutes=hotel["duration_minutes"])
        checkout_local = to_destination_local(checkout_utc, VTN)
        assert checkout_local.hour == 15
        assert checkout_local.minute == 0
        assert checkout_local.date() == date(2026, 10, 3)

        # Both times are distinct
        assert checkin_local != checkout_local

    def test_covered_dates_span_oct2(self):
        """Hotel covering Oct 2 evening to Oct 3 afternoon covers Oct 2 only."""
        hotel = TripNode(
            venue_name="Test Hotel",
            scheduled_start=datetime(2026, 10, 2, 11, 2, tzinfo=timezone.utc),
            duration_minutes=1258,
            is_locked=True,
            status=NodeStatus.PENDING,
            node_kind="booking",
            booking_type="hotel",
        )
        dates = hotel_covered_dates(hotel, VTN)
        assert dates == [date(2026, 10, 2)]


# ---------------------------------------------------------------------------
# Proof 2: add_booking with lat/lng persists; hotel-return uses them
# ---------------------------------------------------------------------------


class TestHotelWithCoords:
    def test_add_booking_with_latlng_persists(self, client):
        """add_booking with lat/lng: coords persist on the returned node."""
        from tests.conftest import auth

        created = client.post(
            "/api/v1/trip/create",
            headers=auth("coords-user"),
            json=_vtn_trip_body(),
        )
        trip_id = created.json()["trip_id"]

        resp = client.post(
            "/api/v1/trip/event",
            headers=auth("coords-user"),
            json={
                "trip_id": trip_id,
                "event_type": "add_booking",
                "message": "Hotel",
                "preferences": {
                    "venue_name": "Settha Palace",
                    "booking_type": "hotel",
                    "scheduled_start": "2026-10-02T18:00:00",
                    "duration_minutes": 900,
                    "lat": 17.9669,
                    "lng": 102.6135,
                    "geo_region": VTN,
                },
            },
        )
        assert resp.status_code == 200
        hotel = next(n for n in resp.json()["updated_nodes"] if n.get("booking_type") == "hotel")
        assert hotel["lat"] == pytest.approx(17.9669, abs=0.001)
        assert hotel["lng"] == pytest.approx(102.6135, abs=0.001)

    def test_hotel_return_with_coords_uses_walking(self):
        """With coords on both hotel and activity, violates_hotel_return
        uses walking time, not a blanket True."""
        hotel = TripNode(
            venue_name="Settha Palace",
            scheduled_start=datetime(2026, 10, 2, 11, 0, tzinfo=timezone.utc),
            duration_minutes=900,
            is_locked=True,
            status=NodeStatus.PENDING,
            node_kind="booking",
            booking_type="hotel",
            lat=17.9669,
            lng=102.6135,
            geo_region=VTN,
        )
        # Activity at 17:00 local (10:00 UTC), 60 min, VERY close to hotel.
        # Evening wall is 21:00 local. 17:00 + 60min + ~0 walk = 18:00 < 21:00.
        result = violates_hotel_return(
            activity_start=datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc),
            activity_duration=60,
            hotel=hotel,
            geo_region=VTN,
            local_date=date(2026, 10, 2),
            activity_lat=17.9670,
            activity_lng=102.6136,
        )
        assert result is False, "Close activity should not violate hotel return"


# ---------------------------------------------------------------------------
# Proof 3: add_booking without lat/lng still saves; hotel-return ineligible
# ---------------------------------------------------------------------------


class TestHotelWithoutCoords:
    def test_add_booking_without_latlng_saves(self, client):
        """add_booking without lat/lng: hotel saves, coords are null."""
        from tests.conftest import auth

        created = client.post(
            "/api/v1/trip/create",
            headers=auth("no-coords-user"),
            json=_vtn_trip_body(),
        )
        trip_id = created.json()["trip_id"]

        resp = client.post(
            "/api/v1/trip/event",
            headers=auth("no-coords-user"),
            json={
                "trip_id": trip_id,
                "event_type": "add_booking",
                "message": "Hotel",
                "preferences": {
                    "venue_name": "Unknown Guesthouse",
                    "booking_type": "hotel",
                    "scheduled_start": "2026-10-02T14:00:00",
                    "duration_minutes": 1080,
                    "geo_region": VTN,
                },
            },
        )
        assert resp.status_code == 200
        hotel = next(n for n in resp.json()["updated_nodes"] if n.get("booking_type") == "hotel")
        assert hotel["lat"] is None
        assert hotel["lng"] is None

    def test_hotel_return_missing_coords_is_true(self):
        """Missing hotel coords: violates_hotel_return returns True."""
        hotel = TripNode(
            venue_name="Unknown Guesthouse",
            scheduled_start=datetime(2026, 10, 2, 7, 0, tzinfo=timezone.utc),
            duration_minutes=1080,
            is_locked=True,
            status=NodeStatus.PENDING,
            node_kind="booking",
            booking_type="hotel",
            lat=None,
            lng=None,
        )
        result = violates_hotel_return(
            activity_start=datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc),
            activity_duration=60,
            hotel=hotel,
            geo_region=VTN,
            local_date=date(2026, 10, 2),
            activity_lat=17.9670,
            activity_lng=102.6136,
        )
        assert result is True, "Missing hotel coords must stay ineligible"

    def test_itinerary_not_mutated_by_missing_coord_warning(self, client):
        """Adding a no-coord hotel must not crash or mutate the itinerary
        beyond adding the hotel node itself."""
        from tests.conftest import auth

        created = client.post(
            "/api/v1/trip/create",
            headers=auth("no-mutate-user"),
            json=_vtn_trip_body(),
        )
        trip_id = created.json()["trip_id"]
        # Add an activity first
        client.post(
            "/api/v1/trip/event",
            headers=auth("no-mutate-user"),
            json={
                "trip_id": trip_id,
                "event_type": "reschedule",
                "message": "plan my day",
            },
        )
        pre = client.get(
            f"/api/v1/trip/{trip_id}",
            headers=auth("no-mutate-user"),
        )
        pre_nodes = pre.json()["nodes"]

        # Add hotel without coords
        resp = client.post(
            "/api/v1/trip/event",
            headers=auth("no-mutate-user"),
            json={
                "trip_id": trip_id,
                "event_type": "add_booking",
                "message": "Hotel",
                "preferences": {
                    "venue_name": "No Coords Inn",
                    "booking_type": "hotel",
                    "scheduled_start": "2026-10-02T14:00:00",
                    "duration_minutes": 1080,
                    "geo_region": VTN,
                },
            },
        )
        assert resp.status_code == 200
        post_nodes = resp.json()["updated_nodes"]
        # Only the hotel is new; other node_ids are preserved
        pre_ids = {n["node_id"] for n in pre_nodes}
        post_ids = {n["node_id"] for n in post_nodes}
        assert pre_ids.issubset(post_ids), "Original nodes must be preserved"


# ---------------------------------------------------------------------------
# Proof 4: Catalog name-match copies that venue only
# ---------------------------------------------------------------------------


class TestCatalogNameMatch:
    def test_exact_match_returns_coords(self):
        """Exact name match returns that venue's coords."""
        catalog = [
            {"venue_name": "Settha Palace", "lat": 17.97, "lng": 102.61, "geo_region": VTN},
            {"venue_name": "Dhavara Hotel", "lat": 17.98, "lng": 102.63, "geo_region": VTN},
        ]
        lat, lng = catalog_coords_for_name("Settha Palace", VTN, catalog_fn=lambda _: catalog)
        assert lat == pytest.approx(17.97)
        assert lng == pytest.approx(102.61)

    def test_case_insensitive_match(self):
        """Match is case-insensitive."""
        catalog = [
            {"venue_name": "Settha Palace", "lat": 17.97, "lng": 102.61},
        ]
        lat, lng = catalog_coords_for_name("settha palace", VTN, catalog_fn=lambda _: catalog)
        assert lat == pytest.approx(17.97)

    def test_no_match_returns_none(self):
        """No match returns (None, None)."""
        catalog = [
            {"venue_name": "Settha Palace", "lat": 17.97, "lng": 102.61},
        ]
        lat, lng = catalog_coords_for_name("Champa Lao Hotel", VTN, catalog_fn=lambda _: catalog)
        assert lat is None
        assert lng is None

    def test_never_copies_different_venue(self):
        """Must not copy coords from a differently-named venue."""
        catalog = [
            {"venue_name": "Hotel A", "lat": 10.0, "lng": 20.0},
            {"venue_name": "Hotel B", "lat": 30.0, "lng": 40.0},
        ]
        lat, lng = catalog_coords_for_name("Hotel A", VTN, catalog_fn=lambda _: catalog)
        assert lat == pytest.approx(10.0)
        assert lng == pytest.approx(20.0)
        # NOT Hotel B's coords
        assert lat != pytest.approx(30.0)

    def test_empty_name_returns_none(self):
        """Empty venue name returns (None, None)."""
        lat, lng = catalog_coords_for_name("", VTN, catalog_fn=lambda _: [])
        assert lat is None
        assert lng is None

    def test_catalog_exception_returns_none(self):
        """If catalog_fn raises, return (None, None) gracefully."""

        def boom(_):
            raise RuntimeError("db unavailable")

        lat, lng = catalog_coords_for_name("Hotel X", VTN, catalog_fn=boom)
        assert lat is None
        assert lng is None


# ---------------------------------------------------------------------------
# Proof 5: Catalog auto-match wires through ADD_BOOKING
# ---------------------------------------------------------------------------


class TestCatalogAutoMatchIntegration:
    def test_add_booking_catalog_match_fills_coords(self, client):
        """When lat/lng not supplied but venue name matches a catalog entry,
        coords are auto-filled on the returned node."""
        from tests.conftest import auth

        created = client.post(
            "/api/v1/trip/create",
            headers=auth("cat-match-user"),
            json=_vtn_trip_body(),
        )
        trip_id = created.json()["trip_id"]

        # Get a known venue name from the catalog
        from services.db_provider import db_service

        venues = db_service.list_venues_for_region(VTN)
        if not venues:
            pytest.skip("No Vientiane venues in catalog")
        target_venue = venues[0]
        target_name = target_venue.get("name") or target_venue.get("venue_name")
        expected_lat = target_venue.get("lat")
        expected_lng = target_venue.get("lng")
        if expected_lat is None or expected_lng is None:
            pytest.skip("First venue has no coords")

        resp = client.post(
            "/api/v1/trip/event",
            headers=auth("cat-match-user"),
            json={
                "trip_id": trip_id,
                "event_type": "add_booking",
                "message": "Hotel",
                "preferences": {
                    "venue_name": target_name,
                    "booking_type": "hotel",
                    "scheduled_start": "2026-10-02T18:00:00",
                    "duration_minutes": 480,
                    "geo_region": VTN,
                    # No lat/lng -- should be auto-filled from catalog
                },
            },
        )
        assert resp.status_code == 200
        hotel = next(
            n
            for n in resp.json()["updated_nodes"]
            if n.get("booking_type") == "hotel" and n["venue_name"] == target_name
        )
        assert hotel["lat"] == pytest.approx(expected_lat, abs=0.01)
        assert hotel["lng"] == pytest.approx(expected_lng, abs=0.01)
