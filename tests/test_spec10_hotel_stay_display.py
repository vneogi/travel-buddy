"""SPEC-10 hotel stay display: dual timestamps, lat/lng persistence, catalog match.

Required proofs from the brief:
- hotel 18:02 local 2 Oct check-in / 15:00 local 3 Oct check-out renders both times
- add_booking with lat/lng persists; hotel-return uses them
- add_booking without lat/lng still saves; hotel-return stays ineligible; itinerary not mutated
- catalog name-match copies that venue only
- booking local-time tests still pass (covered by existing test_spec10_booking_local_time.py)
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
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
# Proof 1: Hotel dual timestamps
# ---------------------------------------------------------------------------


class TestHotelDualTimestamps:
    def test_hotel_1802_checkin_1500_checkout_both_render(self, client):
        """Hotel check-in 18:02 local 2 Oct, check-out 15:00 local 3 Oct."""
        from tests.conftest import auth

        created = client.post(
            "/api/v1/trip/create",
            headers=auth("dual-ts-user"),
            json=_vtn_trip_body(),
        )
        assert created.status_code == 200
        trip_id = created.json()["trip_id"]

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

        stored_utc = datetime.fromisoformat(hotel["scheduled_start"].replace("Z", "+00:00"))
        checkin_local = to_destination_local(stored_utc, VTN)
        assert checkin_local.hour == 18
        assert checkin_local.minute == 2
        assert checkin_local.date() == date(2026, 10, 2)

        checkout_utc = stored_utc + timedelta(minutes=hotel["duration_minutes"])
        checkout_local = to_destination_local(checkout_utc, VTN)
        assert checkout_local.hour == 15
        assert checkout_local.minute == 0
        assert checkout_local.date() == date(2026, 10, 3)

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

    def test_multi_night_hotel_covers_two_dates(self):
        """Check-in Oct 2 18:02 / checkout Oct 4 15:00 covers Oct 2 and Oct 3."""
        # 18:02 VTN Oct 2 = 11:02 UTC Oct 2
        # 15:00 VTN Oct 4 = 08:00 UTC Oct 4
        # Duration = 44h58m = 2698 min
        hotel = TripNode(
            venue_name="Multi-night Hotel",
            scheduled_start=datetime(2026, 10, 2, 11, 2, tzinfo=timezone.utc),
            duration_minutes=2698,
            is_locked=True,
            status=NodeStatus.PENDING,
            node_kind="booking",
            booking_type="hotel",
            geo_region=VTN,
        )
        dates = hotel_covered_dates(hotel, VTN)
        assert date(2026, 10, 2) in dates
        assert date(2026, 10, 3) in dates
        assert date(2026, 10, 4) not in dates  # checkout date excluded
        assert len(dates) == 2


# ---------------------------------------------------------------------------
# Proof 2: add_booking with lat/lng persists; hotel-return uses them
# ---------------------------------------------------------------------------


class TestHotelWithCoords:
    def test_add_booking_with_latlng_persists(self, client):
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
# Proof 3: add_booking without lat/lng; hotel-return ineligible; no mutation
# ---------------------------------------------------------------------------


class TestHotelWithoutCoords:
    def test_add_booking_without_latlng_saves(self, client):
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
        """No-coord hotel must not mutate non-hotel nodes (field-level)."""
        from tests.conftest import auth

        created = client.post(
            "/api/v1/trip/create",
            headers=auth("no-mutate-user"),
            json=_vtn_trip_body(),
        )
        trip_id = created.json()["trip_id"]
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
        pre_nodes = [n for n in pre.json()["nodes"] if n.get("node_kind", "activity") != "booking"]

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
        post_nodes = [
            n for n in resp.json()["updated_nodes"] if n.get("node_kind", "activity") != "booking"
        ]

        # Field-level comparison for each non-hotel node
        pre_by_id = {n["node_id"]: n for n in pre_nodes}
        post_by_id = {n["node_id"]: n for n in post_nodes}
        assert set(pre_by_id.keys()) == set(post_by_id.keys()), (
            "Non-hotel node IDs must be identical"
        )
        for nid in pre_by_id:
            before = pre_by_id[nid]
            after = post_by_id[nid]
            assert before["scheduled_start"] == after["scheduled_start"], (
                f"scheduled_start mutated for {nid}"
            )
            assert before["duration_minutes"] == after["duration_minutes"], (
                f"duration_minutes mutated for {nid}"
            )
            assert before["status"] == after["status"], f"status mutated for {nid}"
            assert before["venue_name"] == after["venue_name"], f"venue_name mutated for {nid}"
            assert before.get("is_locked") == after.get("is_locked"), f"is_locked mutated for {nid}"


# ---------------------------------------------------------------------------
# Proof 4: Catalog name-match (unit)
# ---------------------------------------------------------------------------


class TestCatalogNameMatch:
    def test_exact_match_returns_coords(self):
        catalog = [
            {"name": "Settha Palace", "lat": 17.97, "lng": 102.61, "geo_region": VTN},
            {"name": "Dhavara Hotel", "lat": 17.98, "lng": 102.63, "geo_region": VTN},
        ]
        lat, lng = catalog_coords_for_name("Settha Palace", VTN, catalog_fn=lambda _: catalog)
        assert lat == pytest.approx(17.97)
        assert lng == pytest.approx(102.61)

    def test_case_insensitive_match(self):
        catalog = [{"name": "Settha Palace", "lat": 17.97, "lng": 102.61}]
        lat, lng = catalog_coords_for_name("settha palace", VTN, catalog_fn=lambda _: catalog)
        assert lat == pytest.approx(17.97)

    def test_no_match_returns_none(self):
        catalog = [{"name": "Settha Palace", "lat": 17.97, "lng": 102.61}]
        lat, lng = catalog_coords_for_name("Champa Lao Hotel", VTN, catalog_fn=lambda _: catalog)
        assert lat is None
        assert lng is None

    def test_never_copies_different_venue(self):
        catalog = [
            {"name": "Hotel A", "lat": 10.0, "lng": 20.0},
            {"name": "Hotel B", "lat": 30.0, "lng": 40.0},
        ]
        lat, lng = catalog_coords_for_name("Hotel A", VTN, catalog_fn=lambda _: catalog)
        assert lat == pytest.approx(10.0)
        assert lng == pytest.approx(20.0)
        assert lat != pytest.approx(30.0)

    def test_empty_name_returns_none(self):
        lat, lng = catalog_coords_for_name("", VTN, catalog_fn=lambda _: [])
        assert lat is None
        assert lng is None

    def test_catalog_exception_returns_none(self):
        def boom(_):
            raise RuntimeError("db unavailable")

        lat, lng = catalog_coords_for_name("Hotel X", VTN, catalog_fn=boom)
        assert lat is None
        assert lng is None

    def test_rejects_different_geo_region(self):
        """A catalog row from a different region is not matched."""
        catalog = [
            {"name": "Hotel X", "lat": 10.0, "lng": 20.0, "geo_region": "dubai_uae"},
        ]
        lat, lng = catalog_coords_for_name("Hotel X", VTN, catalog_fn=lambda _: catalog)
        assert lat is None
        assert lng is None


# ---------------------------------------------------------------------------
# Proof 5: Catalog auto-match integration (no conditional skip)
# ---------------------------------------------------------------------------


class TestCatalogAutoMatchIntegration:
    def test_add_hotel_catalog_match_fills_coords(self, client):
        """Catalog match auto-fills coords when lat/lng both absent (hotel)."""
        from tests.conftest import auth

        created = client.post(
            "/api/v1/trip/create",
            headers=auth("cat-match-user"),
            json=_vtn_trip_body(),
        )
        trip_id = created.json()["trip_id"]

        with patch(
            "services.catalog_name_match.catalog_coords_for_name",
            return_value=(17.555, 102.444),
        ):
            resp = client.post(
                "/api/v1/trip/event",
                headers=auth("cat-match-user"),
                json={
                    "trip_id": trip_id,
                    "event_type": "add_booking",
                    "message": "Hotel",
                    "preferences": {
                        "venue_name": "CatalogTestHotel",
                        "booking_type": "hotel",
                        "scheduled_start": "2026-10-02T18:00:00",
                        "duration_minutes": 480,
                        "geo_region": VTN,
                    },
                },
            )
        assert resp.status_code == 200
        hotel = next(
            n
            for n in resp.json()["updated_nodes"]
            if n.get("booking_type") == "hotel" and n["venue_name"] == "CatalogTestHotel"
        )
        assert hotel["lat"] == pytest.approx(17.555, abs=0.01)
        assert hotel["lng"] == pytest.approx(102.444, abs=0.01)

    def test_flight_does_not_trigger_catalog_match(self, client):
        """Catalog match must NOT run for flights."""
        from tests.conftest import auth

        created = client.post(
            "/api/v1/trip/create",
            headers=auth("flight-cat-user"),
            json=_vtn_trip_body(),
        )
        trip_id = created.json()["trip_id"]

        with patch(
            "services.catalog_name_match.catalog_coords_for_name",
            return_value=(99.0, 99.0),
        ) as mock_fn:
            resp = client.post(
                "/api/v1/trip/event",
                headers=auth("flight-cat-user"),
                json={
                    "trip_id": trip_id,
                    "event_type": "add_booking",
                    "message": "Flight",
                    "preferences": {
                        "venue_name": "VN 921",
                        "booking_type": "flight",
                        "scheduled_start": "2026-10-05T07:00:00",
                        "duration_minutes": 120,
                        "geo_region": VTN,
                    },
                },
            )
            # catalog_coords_for_name must NOT have been called for a flight
            mock_fn.assert_not_called()
        assert resp.status_code == 200
        flight = next(n for n in resp.json()["updated_nodes"] if n.get("booking_type") == "flight")
        assert flight.get("lat") is None
        assert flight.get("lng") is None
