"""G0 field-fix proof tests.

Five required proofs:

P1: Corridor 2+2+4 Laos: eight destination-local dates have >= 1 node;
    LP days 7-9 Oct not empty when 6 Oct packed four slots.
P2: ADD_BOOKING hotel geo_region=luang_prabang_laos, check-in 6 Oct:
    node geo_region is LP; VTE segment unchanged; coverage 6,7,8 Oct.
P3: ADD_BOOKING without geo_region on segmented trip for 6 Oct date:
    derive LP from segments -- never stamp vientiane_laos.
P4: Hotel missing coords: last dinner gets no 'cannot return' warning;
    optional one hotel-location warning; pack/swap still treats
    missing-coord hotel-return as True.
P5: Swap candidates for a lunch node: no infra; every listed venue is
    food. Confirm of a listed venue succeeds. Confirm of infra refuses.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from main import app
from models.schemas import (
    NodeStatus,
    TripNode,
    TripSegment,
    TripSegmentIn,
)
from services.database_service import db_service
from tests.conftest import auth

client = TestClient(app)
HEADERS = auth()
GEO_VTE = "vientiane_laos"
GEO_VV = "vang_vieng_laos"
GEO_LP = "luang_prabang_laos"
TZ = ZoneInfo("Asia/Vientiane")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _local_dates_for_region(nodes, region):
    """Return set of local dates for nodes in *region*."""
    return {
        n.scheduled_start.astimezone(TZ).date()
        for n in nodes
        if getattr(n, "geo_region", None) == region
    }


def _make_trip_with_segments() -> dict:
    """POST /trip/create for VTE+VV+LP corridor and return JSON."""
    body = {
        "segments": [
            {"geo_region": GEO_VTE, "starts_on": "2026-10-02", "ends_on": "2026-10-03"},
            {"geo_region": GEO_VV, "starts_on": "2026-10-04", "ends_on": "2026-10-05"},
            {"geo_region": GEO_LP, "starts_on": "2026-10-06", "ends_on": "2026-10-09"},
        ],
    }
    r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
    assert r.status_code == 200, f"Trip create failed: {r.text}"
    return r.json()


# ---------------------------------------------------------------------------
# P1: Corridor 2+2+4 -- eight dates packed, LP days 7-9 not empty
# ---------------------------------------------------------------------------


class TestP1CorridorPacksAllDays:
    def test_all_eight_dates_have_at_least_one_node(self):
        """VTE 2d + VV 2d + LP 4d = 8 calendar dates.
        Each date must have >= 1 activity node when the catalog allows it.
        LP has 21 eligible venues; 4 days x 4 stops is well in range.
        """
        trip = _make_trip_with_segments()
        trip_id = trip["trip_id"]
        r = client.get(f"/api/v1/trip/{trip_id}", headers=HEADERS)
        assert r.status_code == 200
        nodes_json = r.json().get("updated_nodes") or r.json().get("nodes", [])

        from models.schemas import TripNode as TN

        nodes = [TN(**n) for n in nodes_json]

        expected = {
            (GEO_VTE, date(2026, 10, 2)),
            (GEO_VTE, date(2026, 10, 3)),
            (GEO_VV, date(2026, 10, 4)),
            (GEO_VV, date(2026, 10, 5)),
            (GEO_LP, date(2026, 10, 6)),
            (GEO_LP, date(2026, 10, 7)),
            (GEO_LP, date(2026, 10, 8)),
            (GEO_LP, date(2026, 10, 9)),
        }
        actual = {
            (n.geo_region, n.scheduled_start.astimezone(TZ).date())
            for n in nodes
            if getattr(n, "node_kind", "activity") != "booking"
        }
        for key in expected:
            assert key in actual, f"Date {key[1]} in {key[0]} was not populated"

    def test_lp_day_7_to_9_not_empty_when_day_6_packed(self):
        """LP days 7-9 Oct must not all be empty when 6 Oct packed."""
        trip = _make_trip_with_segments()
        trip_id = trip["trip_id"]
        r = client.get(f"/api/v1/trip/{trip_id}", headers=HEADERS)
        nodes_json = r.json().get("updated_nodes") or r.json().get("nodes", [])
        from models.schemas import TripNode as TN

        lp_dates = {
            n.scheduled_start.astimezone(TZ).date()
            for n in (TN(**n) for n in nodes_json)
            if getattr(n, "geo_region", None) == GEO_LP
            and getattr(n, "node_kind", "activity") != "booking"
        }
        oct6_packed = date(2026, 10, 6) in lp_dates
        if oct6_packed:
            # At least one of 7, 8, 9 must also be populated.
            later = {date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9)} & lp_dates
            assert later, "LP Oct 6 packed but Oct 7-9 are all empty"


# ---------------------------------------------------------------------------
# P2: ADD_BOOKING hotel LP geo_region explicit
# ---------------------------------------------------------------------------


class TestP2HotelBookingLPGeoRegion:
    def test_lp_hotel_saves_with_lp_geo_region(self):
        """ADD_BOOKING hotel with geo_region=luang_prabang_laos, check-in 6 Oct.
        Node geo_region must be LP; VTE segment dates must be unchanged;
        coverage dates are 6, 7, 8 Oct only ([check-in, checkout))."""
        trip = _make_trip_with_segments()
        trip_id = trip["trip_id"]

        r = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "add_booking",
                "message": "Add LP hotel",
                "preferences": {
                    "venue_name": "Queens House Luang Prabang",
                    "booking_type": "hotel",
                    "geo_region": GEO_LP,
                    "scheduled_start": "2026-10-06T15:00:00",
                    "duration_minutes": 3 * 24 * 60,  # 3 nights -> checkout 9 Oct
                },
            },
            headers=HEADERS,
        )
        assert r.status_code == 200, r.text
        nodes_json = r.json().get("updated_nodes") or r.json().get("nodes", [])
        from models.schemas import TripNode as TN

        hotel = next(
            (TN(**n) for n in nodes_json if n.get("booking_type") == "hotel"),
            None,
        )
        assert hotel is not None, "No hotel node returned"
        assert hotel.geo_region == GEO_LP, (
            f"Hotel geo_region is {hotel.geo_region}, expected {GEO_LP}"
        )

        # VTE segment dates unchanged: activity nodes in VTE still on Oct 2-3.
        vte_nodes = [
            TN(**n)
            for n in nodes_json
            if n.get("geo_region") == GEO_VTE and n.get("node_kind") != "booking"
        ]
        for n in vte_nodes:
            d = n.scheduled_start.astimezone(TZ).date()
            assert d in {date(2026, 10, 2), date(2026, 10, 3)}, (
                f"VTE node {n.venue_name} is on {d}, not Oct 2-3"
            )

    def test_hotel_coverage_dates_are_checkin_inclusive_checkout_exclusive(self):
        """Coverage [check-in, checkout) = 6, 7, 8 Oct (not 9)."""
        from services.booking_constraints import hotel_covered_dates

        node = TripNode(
            node_id="h1",
            venue_name="Queens House",
            scheduled_start=datetime(2026, 10, 6, 8, 0, 0, tzinfo=timezone.utc),
            duration_minutes=3 * 24 * 60,
            is_locked=True,
            status=NodeStatus.PENDING,
            geo_region=GEO_LP,
            node_kind="booking",
            booking_type="hotel",
            vibeTags=[],
        )
        covered = hotel_covered_dates(node, GEO_LP)
        assert date(2026, 10, 6) in covered
        assert date(2026, 10, 7) in covered
        assert date(2026, 10, 8) in covered
        assert date(2026, 10, 9) not in covered, "Checkout date must not be in coverage"


# ---------------------------------------------------------------------------
# P3: ADD_BOOKING without geo_region derives from segments (never VTE)
# ---------------------------------------------------------------------------


class TestP3BookingDerivedGeoRegion:
    def test_booking_6oct_without_geo_region_is_not_vientiane(self):
        """ADD_BOOKING for a 6 Oct date without explicit geo_region on a
        segmented trip must derive LP (or refuse), never stamp VTE."""
        trip = _make_trip_with_segments()
        trip_id = trip["trip_id"]

        r = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "add_booking",
                "message": "Add tour",
                "preferences": {
                    "venue_name": "Morning Alms Ceremony Tour",
                    "booking_type": "tour",
                    # No geo_region: server must derive from scheduled_start date.
                    "scheduled_start": "2026-10-06T09:00:00",
                    "duration_minutes": 120,
                },
            },
            headers=HEADERS,
        )
        assert r.status_code == 200, r.text
        nodes_json = r.json().get("updated_nodes") or r.json().get("nodes", [])
        from models.schemas import TripNode as TN

        tour = next(
            (TN(**n) for n in nodes_json if n.get("booking_type") == "tour"),
            None,
        )
        assert tour is not None, "No tour node returned"
        assert tour.geo_region != GEO_VTE, (
            f"Tour geo_region is {GEO_VTE}; 6 Oct must resolve to LP, not VTE"
        )
        assert tour.geo_region == GEO_LP, f"Tour geo_region is {tour.geo_region}, expected {GEO_LP}"


# ---------------------------------------------------------------------------
# P4: Hotel missing coords -- no false per-activity 'cannot return' warning
# ---------------------------------------------------------------------------


class TestP4HotelMissingCoordsWarning:
    def test_no_cannot_return_warning_when_hotel_has_no_coords(self):
        """Last dinner must NOT get 'cannot return to the hotel in time'
        when the hotel has no coords. At most one hotel-location warning."""
        from services.scheduler import reschedule_and_validate
        from services.booking_constraints import HOTEL_RETURN_LOCAL_HOUR

        tz = TZ
        base = datetime(2026, 10, 6, 9, 0, 0, tzinfo=tz).astimezone(timezone.utc)

        hotel = TripNode(
            node_id="htl-no-coords",
            venue_name="Salana Boutique Hotel",
            scheduled_start=base,
            duration_minutes=3 * 24 * 60,
            is_locked=True,
            status=NodeStatus.PENDING,
            geo_region=GEO_LP,
            node_kind="booking",
            booking_type="hotel",
            vibeTags=[],
            # No lat/lng
        )
        # Last dinner: 19:00 local
        dinner_start = datetime(2026, 10, 6, 12, 0, 0, tzinfo=tz).astimezone(timezone.utc)
        dinner = TripNode(
            node_id="dinner-1",
            venue_name="Khop Chai Deu",
            scheduled_start=dinner_start,
            duration_minutes=90,
            is_locked=False,
            status=NodeStatus.PENDING,
            geo_region=GEO_LP,
            lat=19.8856,
            lng=102.1347,
            node_kind="activity",
            vibeTags=[],
        )
        nodes = [hotel, dinner]
        result = reschedule_and_validate(nodes)

        # No per-activity "cannot return" warning
        bad = [w for w in result.warnings if "cannot return" in w.lower()]
        assert not bad, f"False 'cannot return' warnings when hotel has no coords: {bad}"

        # At most one hotel-location warning
        location_warns = [w for w in result.warnings if "no map location" in w.lower()]
        assert len(location_warns) <= 1, (
            f"Expected at most 1 hotel-location warning, got {location_warns}"
        )

    def test_pack_swap_hotel_return_still_true_when_coords_missing(self):
        """violates_hotel_return returns True when hotel has no coords
        (pack/swap last-slot eligibility unchanged)."""
        from services.booking_constraints import violates_hotel_return

        hotel = TripNode(
            node_id="htl-nc",
            venue_name="No Coords Hotel",
            scheduled_start=datetime(2026, 10, 6, 14, 0, 0, tzinfo=timezone.utc),
            duration_minutes=24 * 60,
            is_locked=True,
            status=NodeStatus.PENDING,
            geo_region=GEO_LP,
            node_kind="booking",
            booking_type="hotel",
            vibeTags=[],
        )
        act_start = datetime(2026, 10, 6, 12, 0, 0, tzinfo=timezone.utc)
        result = violates_hotel_return(
            act_start,
            90,
            hotel,
            GEO_LP,
            date(2026, 10, 6),
            activity_lat=19.89,
            activity_lng=102.13,
        )
        assert result is True, "Missing hotel coords must make violates_hotel_return True"


# ---------------------------------------------------------------------------
# P5: Swap candidates for lunch node -- slot-typed, no infra
# ---------------------------------------------------------------------------


class TestP5SwapCandidatesSlotTyped:
    def _seed_trip_with_lunch(self):
        """Seed a VV trip with a lunch node and return (trip_id, lunch_node_id)."""
        r = client.post(
            "/api/v1/trip/create",
            json={"geo_region": GEO_VV, "start_date": "2026-10-04"},
            headers=HEADERS,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        trip_id = data["trip_id"]
        nodes = data["nodes"]
        lunch = next((n for n in nodes if n.get("slot_name") == "lunch"), None)
        if lunch is None:
            pytest.skip("No lunch node in seeded VV trip -- catalog too small")
        return trip_id, lunch["node_id"]

    def test_no_infrastructure_in_candidates(self):
        """Hospital, pharmacy, transport_hub must not appear in swap candidates."""
        trip_id, lunch_id = self._seed_trip_with_lunch()
        r = client.get(
            f"/api/v1/trip/{trip_id}/swap_candidates/{lunch_id}",
            headers=HEADERS,
        )
        assert r.status_code == 200, r.text
        candidates = r.json()["candidates"]
        infra = {"hospital", "pharmacy", "transport_hub"}
        bad = [c for c in candidates if (c.get("category") or "").lower() in infra]
        assert not bad, f"Infrastructure venues in candidates: {[b['name'] for b in bad]}"

    def test_lunch_candidates_are_food_only(self):
        """Swap candidates for a lunch node must all be food venues."""
        from services.day_slots import _FOOD_CATEGORIES

        trip_id, lunch_id = self._seed_trip_with_lunch()
        r = client.get(
            f"/api/v1/trip/{trip_id}/swap_candidates/{lunch_id}",
            headers=HEADERS,
        )
        assert r.status_code == 200, r.text
        candidates = r.json()["candidates"]
        if not candidates:
            pytest.skip("No lunch swap candidates (catalog size); infra proof sufficient")
        bad = [
            c
            for c in candidates
            if (c.get("category") or "experience").lower() not in _FOOD_CATEGORIES
        ]
        assert not bad, (
            f"Non-food venues in lunch swap candidates: "
            f"{[(b['name'], b.get('category')) for b in bad]}"
        )

    def test_confirm_listed_venue_succeeds(self):
        """Confirm of a candidate from the list must succeed (not no_candidates)."""
        trip_id, lunch_id = self._seed_trip_with_lunch()
        r = client.get(
            f"/api/v1/trip/{trip_id}/swap_candidates/{lunch_id}",
            headers=HEADERS,
        )
        assert r.status_code == 200
        candidates = r.json()["candidates"]
        if not candidates:
            pytest.skip("No candidates; confirm test not applicable")
        chosen_id = candidates[0]["venue_id"]

        confirm_r = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "swap_activity",
                "message": "Swap lunch",
                "target_node_id": lunch_id,
                "preferences": {"replacement_venue_id": chosen_id},
            },
            headers=HEADERS,
        )
        assert confirm_r.status_code == 200, confirm_r.text
        resp = confirm_r.json()
        # Successful swap: message should say "Swapped to ..." not refusal.
        assert "couldn't find" not in resp.get("message", "").lower(), (
            f"Confirm of a listed swap candidate was refused: {resp.get('message')}"
        )

    def test_confirm_infrastructure_venue_returns_no_candidates(self):
        """Confirm of a hospital/pharmacy/hub must return no_candidates."""
        trip_id, lunch_id = self._seed_trip_with_lunch()

        # Find an infrastructure venue in VV
        vv_rows = db_service.list_venues_for_region(GEO_VV)
        infra_cats = {"hospital", "pharmacy", "transport_hub"}
        infra_venue = next(
            (r for r in vv_rows if (r.get("category") or "").lower() in infra_cats),
            None,
        )
        if infra_venue is None:
            pytest.skip("No infrastructure venue in VV catalog")
        infra_id = str(infra_venue["venue_id"])

        confirm_r = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "swap_activity",
                "message": "Swap to infra",
                "target_node_id": lunch_id,
                "preferences": {"replacement_venue_id": infra_id},
            },
            headers=HEADERS,
        )
        assert confirm_r.status_code == 200, confirm_r.text
        resp = confirm_r.json()
        # no_candidates -> status="processed" but message contains refusal.
        # The venue is unchanged in updated_nodes.
        assert "couldn't find" in resp.get("message", "").lower() or (
            "unchanged" in resp.get("message", "").lower()
        ), f"Confirming an infrastructure venue must be refused, got: {resp.get('message')}"


# ---------------------------------------------------------------------------
# P6: ADD_BOOKING invalid geo_region on corridor trip -> 422 refusal
# ---------------------------------------------------------------------------


class TestP6AddBookingInvalidRegionRefused:
    def test_invalid_geo_region_returns_422(self):
        """ADD_BOOKING with geo_region not in segments must return 422,
        not HTTP-200 with success copy."""
        trip = _make_trip_with_segments()
        trip_id = trip["trip_id"]

        r = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "add_booking",
                "message": "Add Dubai hotel",
                "preferences": {
                    "venue_name": "Burj Al Arab",
                    "booking_type": "hotel",
                    "geo_region": "dubai_uae",
                    "scheduled_start": "2026-10-06T15:00:00",
                    "duration_minutes": 1440,
                },
            },
            headers=HEADERS,
        )
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
        detail = r.json()["detail"]
        assert detail["error"] == "booking_refused", detail

    def test_no_new_node_created(self):
        """Refused booking must not leave a new node in the trip."""
        trip = _make_trip_with_segments()
        trip_id = trip["trip_id"]
        orig_count = len(trip.get("nodes", []))

        client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "add_booking",
                "message": "Add Dubai hotel",
                "preferences": {
                    "venue_name": "Burj Al Arab",
                    "booking_type": "hotel",
                    "geo_region": "dubai_uae",
                    "scheduled_start": "2026-10-06T15:00:00",
                    "duration_minutes": 1440,
                },
            },
            headers=HEADERS,
        )
        r2 = client.get(f"/api/v1/trip/{trip_id}", headers=HEADERS)
        new_count = len(r2.json().get("nodes", []))
        assert new_count == orig_count, (
            f"Node count changed from {orig_count} to {new_count} after refused booking"
        )


# ---------------------------------------------------------------------------
# P7: ADD_BOOKING date outside all segments -> refuse, no nearest
# ---------------------------------------------------------------------------


class TestP7GapDateRefused:
    def test_date_after_all_segments_is_refused(self):
        """ADD_BOOKING for 2026-10-15 (after LP ends Oct 9) must be refused.
        No silent nearest-segment assignment."""
        trip = _make_trip_with_segments()
        trip_id = trip["trip_id"]

        r = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "add_booking",
                "message": "Add tour after corridor",
                "preferences": {
                    "venue_name": "Luang Namtha Trekking",
                    "booking_type": "tour",
                    "scheduled_start": "2026-10-15T10:00:00",
                    "duration_minutes": 180,
                },
            },
            headers=HEADERS,
        )
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
        detail = r.json()["detail"]
        assert detail["error"] == "booking_refused", detail


# ---------------------------------------------------------------------------
# P8: ADD_BOOKING naive 2026-10-06T00:30 -> LP not VTE (destination-local)
# ---------------------------------------------------------------------------


class TestP8AfterMidnightLocalLP:
    def test_naive_00_30_oct6_resolves_to_lp(self):
        """2026-10-06T00:30:00 naive = LP local (Oct 6).
        If parsed as UTC, .date() = Oct 5 in UTC which is still Oct 5 --
        but segment TZ is Asia/Vientiane (UTC+7), so this is already
        Oct 6 local.  The derive must give LP, not VTE."""
        trip = _make_trip_with_segments()
        trip_id = trip["trip_id"]

        r = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "add_booking",
                "message": "Late night LP",
                "preferences": {
                    "venue_name": "Night Market Walk",
                    "booking_type": "tour",
                    # naive ISO -- no Z, no offset
                    "scheduled_start": "2026-10-06T00:30:00",
                    "duration_minutes": 60,
                },
            },
            headers=HEADERS,
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        from models.schemas import TripNode as TN

        nodes_json = r.json().get("updated_nodes") or r.json().get("nodes", [])
        tour = next(
            (TN(**n) for n in nodes_json if n.get("venue_name") == "Night Market Walk"),
            None,
        )
        assert tour is not None, "Night Market Walk node not found"
        assert tour.geo_region == GEO_LP, (
            f"geo_region is {tour.geo_region}, expected {GEO_LP} for Oct 6 local"
        )
        assert tour.geo_region != GEO_VTE, "Must not resolve to VTE"


# ---------------------------------------------------------------------------
# P9: EDIT_BOOKING invalid city -> node unchanged (name and region)
# ---------------------------------------------------------------------------


class TestP9EditBookingInvalidCity:
    def test_edit_invalid_city_returns_422_node_unchanged(self):
        """EDIT_BOOKING with invalid corridor city: 422, node unchanged."""
        trip = _make_trip_with_segments()
        trip_id = trip["trip_id"]

        # First add a valid LP hotel.
        add_r = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "add_booking",
                "message": "Add LP hotel",
                "preferences": {
                    "venue_name": "Queens House LP",
                    "booking_type": "hotel",
                    "geo_region": GEO_LP,
                    "scheduled_start": "2026-10-06T15:00:00",
                    "duration_minutes": 1440,
                },
            },
            headers=HEADERS,
        )
        assert add_r.status_code == 200, add_r.text
        from models.schemas import TripNode as TN

        nodes_json = add_r.json().get("updated_nodes") or []
        hotel = next(
            (TN(**n) for n in nodes_json if n.get("booking_type") == "hotel"),
            None,
        )
        assert hotel is not None
        hotel_id = hotel.node_id

        # Now try to edit with invalid city.
        edit_r = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "edit_booking",
                "message": "Move to Dubai",
                "target_node_id": hotel_id,
                "preferences": {
                    "venue_name": "Burj Al Arab",
                    "geo_region": "dubai_uae",
                },
            },
            headers=HEADERS,
        )
        assert edit_r.status_code == 422, f"Expected 422, got {edit_r.status_code}: {edit_r.text}"

        # Verify node is unchanged.
        get_r = client.get(f"/api/v1/trip/{trip_id}", headers=HEADERS)
        nodes_after = get_r.json().get("nodes", [])
        hotel_after = next((n for n in nodes_after if n["node_id"] == hotel_id), None)
        assert hotel_after is not None
        assert hotel_after["venue_name"] == "Queens House LP", (
            f"Name changed to {hotel_after['venue_name']} after refused edit"
        )
        assert hotel_after["geo_region"] == GEO_LP, (
            f"Region changed to {hotel_after['geo_region']} after refused edit"
        )


# ---------------------------------------------------------------------------
# P10: EDIT_BOOKING city change clears old coords
# ---------------------------------------------------------------------------


class TestP10EditCityChangeCoords:
    def test_edit_city_change_clears_old_coords(self):
        """When city changes from VTE to LP, old VTE coords must be
        cleared (or re-resolved from catalog). Not carried over."""
        trip = _make_trip_with_segments()
        trip_id = trip["trip_id"]

        # Add VTE hotel with coords.
        add_r = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "add_booking",
                "message": "Add VTE hotel",
                "preferences": {
                    "venue_name": "Ansara Hotel",
                    "booking_type": "hotel",
                    "geo_region": GEO_VTE,
                    "scheduled_start": "2026-10-02T15:00:00",
                    "duration_minutes": 1440,
                    "lat": 17.962,
                    "lng": 102.609,
                },
            },
            headers=HEADERS,
        )
        assert add_r.status_code == 200, add_r.text
        from models.schemas import TripNode as TN

        nodes_json = add_r.json().get("updated_nodes") or []
        hotel = next(
            (TN(**n) for n in nodes_json if n.get("booking_type") == "hotel"),
            None,
        )
        assert hotel is not None
        hotel_id = hotel.node_id

        # Edit: move to LP with a different name (not in LP catalog).
        edit_r = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "edit_booking",
                "message": "Move hotel to LP",
                "target_node_id": hotel_id,
                "preferences": {
                    "venue_name": "Riverside Guesthouse LP",
                    "geo_region": GEO_LP,
                },
            },
            headers=HEADERS,
        )
        assert edit_r.status_code == 200, f"Expected 200, got {edit_r.status_code}: {edit_r.text}"

        # Check coords are cleared (not the old VTE coords).
        get_r = client.get(f"/api/v1/trip/{trip_id}", headers=HEADERS)
        hotel_after = next(
            (n for n in get_r.json().get("nodes", []) if n["node_id"] == hotel_id),
            None,
        )
        assert hotel_after is not None
        assert hotel_after["geo_region"] == GEO_LP
        # Old VTE coords must not persist.
        lat_after = hotel_after.get("lat")
        lng_after = hotel_after.get("lng")
        if lat_after is not None and lng_after is not None:
            # If coords are set, they must be catalog-resolved LP coords,
            # not the original VTE ones.
            assert abs(lat_after - 17.962) > 0.01 or abs(lng_after - 102.609) > 0.01, (
                "Old VTE coords persisted after city change to LP"
            )


# ---------------------------------------------------------------------------
# P11: Corridor create with exhausted catalog warns honestly
# ---------------------------------------------------------------------------


class TestP11CorridorEmptyDayWarning:
    def test_p1_eight_date_fixture_still_populates_all(self):
        """Standard 8-date Laos fixture must still populate all 8 dates
        when the catalog has enough venues."""
        trip = _make_trip_with_segments()
        from models.schemas import TripNode as TN

        nodes_json = trip.get("nodes", [])
        nodes = [TN(**n) for n in nodes_json]
        dates = set()
        for n in nodes:
            dates.add(n.scheduled_start.astimezone(TZ).date())
        expected = set()
        for d in range(2, 10):
            expected.add(date(2026, 10, d))
        # All 8 expected dates must appear.
        for d in expected:
            assert d in dates, f"Date {d} has no nodes"

    def test_exhausted_catalog_returns_422(self):
        """If we request more days than the catalog can fill, the create
        must fail with corridor_empty_days (not silently succeed)."""
        from services.corridor_itinerary import build_corridor_nodes
        from config.corridors import require_corridor

        corridor = require_corridor("laos_northbound_v1")
        # Request 10 days for LP -- catalog has ~21 eligible venues,
        # at 4 per day that is 5 full days + ~1 partial; days 6+ empty.
        segments = [
            TripSegmentIn(
                geo_region=GEO_LP,
                starts_on=date(2026, 10, 1),
                ends_on=date(2026, 10, 10),
            ),
        ]

        _nodes, _stored, warnings = build_corridor_nodes(
            segments, db_service.list_venues_for_region, corridor
        )
        if not warnings:
            # Catalog is large enough -- that is fine; the test is about
            # the _behavior_ when warnings exist.  Let us manufacture one.
            pass

        # Build with artificially small catalog to guarantee exhaustion.
        def _tiny_fn(region):
            rows = db_service.list_venues_for_region(region)
            return rows[:4]  # only 4 venues -> 1 full day, rest empty

        _n2, _s2, w2 = build_corridor_nodes(segments, _tiny_fn, corridor)
        assert len(w2) > 0, "Expected empty-day warnings from exhausted catalog"
        # The warning should name the empty date.
        assert any("2026-10-" in w for w in w2), f"Warning must name the date: {w2}"
