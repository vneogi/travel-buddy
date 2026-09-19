"""SPEC-10 booking local time: naive wall times are destination-local.

Reproduce-then-fix: naive hotel scheduled_start 2026-10-02T18:02:00 on a
Vientiane trip must round-trip to 18:02 Asia/Vientiane, not 01:02 the next
day.

All tests use TestClient add_booking / edit_booking on a Vientiane trip
(R17: not helper-only tests).

SPEC-10 scheduler + state-machine slice.
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from services.destination_tz import (
    parse_destination_wall_time,
    to_destination_local,
)
from services.booking_constraints import hotel_covered_dates

VTN = "vientiane_laos"
VTN_TZ = ZoneInfo("Asia/Vientiane")  # UTC+7


def _vtn_trip_body():
    return {
        "start_date": "2026-10-02T09:00:00",
        "geo_region": VTN,
    }


# ---------------------------------------------------------------------------
# 1. Naive 18:02 round-trips to 18:02 local, not 01:02 next day
# ---------------------------------------------------------------------------


class TestNaiveRoundTrip:
    def test_naive_hotel_1802_roundtrips_to_1802_local(self, client):
        """POST naive scheduled_start=2026-10-02T18:02:00 with
        geo_region=vientiane_laos. Response node, converted with
        to_destination_local, is 2026-10-02 18:02 in Asia/Vientiane.
        It is NOT 2026-10-03 01:02."""
        from tests.conftest import auth

        created = client.post(
            "/api/v1/trip/create",
            headers=auth("local-time-user"),
            json=_vtn_trip_body(),
        )
        assert created.status_code == 200
        trip_id = created.json()["trip_id"]

        # Add hotel: check-in Oct 2 18:02 local, duration = 20h58m to
        # checkout Oct 3 15:00 local (= Oct 3 08:00 UTC).
        # 18:02 local Oct 2 = 11:02 UTC Oct 2.
        # 15:00 local Oct 3 = 08:00 UTC Oct 3.
        # Duration = 20h58m = 1258 minutes.
        resp = client.post(
            "/api/v1/trip/event",
            headers=auth("local-time-user"),
            json={
                "trip_id": trip_id,
                "event_type": "add_booking",
                "message": "Hotel check-in",
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
        body = resp.json()

        # Find the hotel node
        hotel = next(
            (n for n in body["updated_nodes"] if n.get("booking_type") == "hotel"),
            None,
        )
        assert hotel is not None, "Hotel node must be in response"

        # Parse the stored UTC start
        stored_utc = datetime.fromisoformat(hotel["scheduled_start"].replace("Z", "+00:00"))

        # Convert to destination-local
        local_dt = to_destination_local(stored_utc, VTN)

        # Assert local hour and date
        assert local_dt.hour == 18, f"Expected 18:xx local, got {local_dt}"
        assert local_dt.minute == 2, f"Expected xx:02 local, got {local_dt}"
        assert local_dt.date() == date(2026, 10, 2), f"Expected Oct 2 local, got {local_dt.date()}"

        # Assert the UTC instant is 11:02 UTC Oct 2 (18:02 - 7h)
        assert stored_utc == datetime(2026, 10, 2, 11, 2, tzinfo=timezone.utc)

        # Must NOT be 01:02 next day (the old bug)
        assert local_dt.hour != 1 or local_dt.date() != date(2026, 10, 3)


# ---------------------------------------------------------------------------
# 2. Sabotage: restoring replace(tzinfo=utc) makes test 1 fail
# ---------------------------------------------------------------------------


class TestSabotage:
    def test_naive_as_utc_gives_wrong_local_hour(self):
        """Sabotage proof: if we stamp naive 18:02 as UTC, destination-local
        is 01:02 next day -- exactly the original bug.

        This test documents the bug. Removing parse_destination_wall_time
        and restoring replace(tzinfo=utc) would make TestNaiveRoundTrip fail.
        """
        naive = datetime(2026, 10, 2, 18, 2)
        # OLD CODE: stamp as UTC
        stamped_utc = naive.replace(tzinfo=timezone.utc)
        local_dt = to_destination_local(stamped_utc, VTN)
        # This is the BUG: 01:02 Oct 3, not 18:02 Oct 2
        assert local_dt.hour == 1
        assert local_dt.date() == date(2026, 10, 3)


# ---------------------------------------------------------------------------
# 3. Aware +07:00 stores same UTC as naive 18:02 for that region
# ---------------------------------------------------------------------------


class TestAwareOffset:
    def test_aware_plus_07_stores_same_utc(self, client):
        """Aware 2026-10-02T18:02:00+07:00 stores the same UTC instant
        as naive 18:02 for vientiane_laos."""
        from tests.conftest import auth

        created = client.post(
            "/api/v1/trip/create",
            headers=auth("aware-offset-user"),
            json=_vtn_trip_body(),
        )
        assert created.status_code == 200
        trip_id = created.json()["trip_id"]

        resp = client.post(
            "/api/v1/trip/event",
            headers=auth("aware-offset-user"),
            json={
                "trip_id": trip_id,
                "event_type": "add_booking",
                "message": "Hotel",
                "preferences": {
                    "venue_name": "Settha Palace",
                    "booking_type": "hotel",
                    "scheduled_start": "2026-10-02T18:02:00+07:00",
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
        assert stored_utc == datetime(2026, 10, 2, 11, 2, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 4. Z timestamp is that instant (11:02Z = 18:02 local)
# ---------------------------------------------------------------------------


class TestZTimestamp:
    def test_z_timestamp_is_1802_local(self, client):
        """2026-10-02T11:02:00Z is 18:02 local, not 11:02 local."""
        from tests.conftest import auth

        created = client.post(
            "/api/v1/trip/create",
            headers=auth("z-ts-user"),
            json=_vtn_trip_body(),
        )
        assert created.status_code == 200
        trip_id = created.json()["trip_id"]

        resp = client.post(
            "/api/v1/trip/event",
            headers=auth("z-ts-user"),
            json={
                "trip_id": trip_id,
                "event_type": "add_booking",
                "message": "Hotel",
                "preferences": {
                    "venue_name": "Lao Poet Hotel",
                    "booking_type": "hotel",
                    "scheduled_start": "2026-10-02T11:02:00Z",
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
        # Z timestamp is already UTC -- stored as-is
        assert stored_utc == datetime(2026, 10, 2, 11, 2, tzinfo=timezone.utc)
        # Converts to 18:02 local
        local_dt = to_destination_local(stored_utc, VTN)
        assert local_dt.hour == 18
        assert local_dt.minute == 2
        assert local_dt.date() == date(2026, 10, 2)


# ---------------------------------------------------------------------------
# 5. edit_booking naive start uses the same helper
# ---------------------------------------------------------------------------


class TestEditBooking:
    def test_edit_booking_naive_uses_wall_time(self, client):
        """edit_booking naive start uses parse_destination_wall_time,
        not replace(tzinfo=utc)."""
        from tests.conftest import auth

        created = client.post(
            "/api/v1/trip/create",
            headers=auth("edit-bk-user"),
            json=_vtn_trip_body(),
        )
        assert created.status_code == 200
        trip_id = created.json()["trip_id"]

        # Add a hotel first
        add_resp = client.post(
            "/api/v1/trip/event",
            headers=auth("edit-bk-user"),
            json={
                "trip_id": trip_id,
                "event_type": "add_booking",
                "message": "Hotel",
                "preferences": {
                    "venue_name": "Landmark Mekong Hotel",
                    "booking_type": "hotel",
                    "scheduled_start": "2026-10-02T14:00:00",
                    "duration_minutes": 1440,
                    "lat": 17.976,
                    "lng": 102.633,
                    "geo_region": VTN,
                },
            },
        )
        assert add_resp.status_code == 200
        hotel = next(
            n for n in add_resp.json()["updated_nodes"] if n.get("booking_type") == "hotel"
        )
        hotel_node_id = hotel["node_id"]

        # Edit the check-in to 18:02 naive
        edit_resp = client.post(
            "/api/v1/trip/event",
            headers=auth("edit-bk-user"),
            json={
                "trip_id": trip_id,
                "event_type": "edit_booking",
                "message": "Change check-in",
                "target_node_id": hotel_node_id,
                "preferences": {
                    "scheduled_start": "2026-10-02T18:02:00",
                },
            },
        )
        assert edit_resp.status_code == 200

        # Find the edited hotel
        edited = next(n for n in edit_resp.json()["updated_nodes"] if n["node_id"] == hotel_node_id)
        stored_utc = datetime.fromisoformat(edited["scheduled_start"].replace("Z", "+00:00"))
        # Must be 11:02 UTC (18:02 local - 7h), not 18:02 UTC
        assert stored_utc == datetime(2026, 10, 2, 11, 2, tzinfo=timezone.utc)
        local_dt = to_destination_local(stored_utc, VTN)
        assert local_dt.hour == 18
        assert local_dt.minute == 2


# ---------------------------------------------------------------------------
# 6. Hotel coverage local dates
# ---------------------------------------------------------------------------


class TestHotelCoverage:
    def test_hotel_coverage_includes_oct2_excludes_checkout(self, client):
        """Hotel check-in Oct 2 18:02 local, checkout Oct 3 15:00 local.
        Coverage includes Oct 2 and excludes Oct 3 (checkout date).
        Duration: 1258 min (18:02 -> 15:00 next day)."""
        from tests.conftest import auth
        from models.schemas import TripNode

        created = client.post(
            "/api/v1/trip/create",
            headers=auth("coverage-user"),
            json=_vtn_trip_body(),
        )
        assert created.status_code == 200
        trip_id = created.json()["trip_id"]

        resp = client.post(
            "/api/v1/trip/event",
            headers=auth("coverage-user"),
            json={
                "trip_id": trip_id,
                "event_type": "add_booking",
                "message": "Hotel",
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
        hotel_dict = next(
            n for n in resp.json()["updated_nodes"] if n.get("booking_type") == "hotel"
        )
        # Build a TripNode to use hotel_covered_dates
        hotel_node = TripNode(
            venue_name=hotel_dict["venue_name"],
            scheduled_start=datetime.fromisoformat(
                hotel_dict["scheduled_start"].replace("Z", "+00:00")
            ),
            duration_minutes=hotel_dict["duration_minutes"],
            is_locked=True,
            node_kind="booking",
            booking_type="hotel",
            lat=hotel_dict.get("lat"),
            lng=hotel_dict.get("lng"),
            geo_region=VTN,
        )
        dates = hotel_covered_dates(hotel_node, VTN)
        # Check-in is Oct 2 18:02 local -> covers Oct 2
        assert date(2026, 10, 2) in dates
        # Checkout is Oct 3 15:00 local -> Oct 3 is NOT a covered night
        assert date(2026, 10, 3) not in dates


# ---------------------------------------------------------------------------
# 7. Helper unit tests (supplementary, not R17 replacement)
# ---------------------------------------------------------------------------


class TestParseHelper:
    def test_naive_attaches_destination_tz(self):
        result = parse_destination_wall_time("2026-10-02T18:02:00", VTN)
        assert result == datetime(2026, 10, 2, 11, 2, tzinfo=timezone.utc)

    def test_aware_offset_converts(self):
        result = parse_destination_wall_time("2026-10-02T18:02:00+07:00", VTN)
        assert result == datetime(2026, 10, 2, 11, 2, tzinfo=timezone.utc)

    def test_z_converts(self):
        result = parse_destination_wall_time("2026-10-02T11:02:00Z", VTN)
        assert result == datetime(2026, 10, 2, 11, 2, tzinfo=timezone.utc)

    def test_unknown_region_raises(self):
        with pytest.raises(ValueError, match="unknown geo_region"):
            parse_destination_wall_time("2026-10-02T18:02:00", "narnia")

    def test_none_region_raises(self):
        with pytest.raises(ValueError, match="unknown geo_region"):
            parse_destination_wall_time("2026-10-02T18:02:00", None)
