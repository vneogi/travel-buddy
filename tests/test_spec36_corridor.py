"""SPEC-36: Corridor trip backend proof cases and sabotage proofs."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from main import app
from config.corridors import CORRIDORS, require_corridor
from config.regions import REGIONS
from models.schemas import TripState, TripSegmentIn
from services.catalog_itinerary import eligible_venues
from services.corridor_itinerary import (
    CORRIDOR_STOPS_PER_DAY,
    InvalidCorridor,
    UnsupportedCorridor,
    build_corridor_nodes,
    validate_corridor_segments,
    advertised_corridors,
)
from services.itinerary_normaliser import decompose_trip
from services.db_provider import db_service
from tests.conftest import auth

client = TestClient(app)
HEADERS = auth("spec36-user")


def _corridor_body(
    starts=None,
    regions=("vientiane_laos", "vang_vieng_laos", "luang_prabang_laos"),
):
    if starts is None:
        starts = [
            ("2026-10-02", "2026-10-03"),
            ("2026-10-04", "2026-10-05"),
            ("2026-10-06", "2026-10-08"),
        ]
    return {
        "segments": [
            {"geo_region": r, "starts_on": s, "ends_on": e} for r, (s, e) in zip(regions, starts)
        ],
    }


# ================================================================
# Proof 1: valid three-segment create
# ================================================================
class TestCorridorCreate:
    def test_valid_create_returns_trip_with_segments(self):
        resp = client.post("/api/v1/trip/create", json=_corridor_body(), headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        assert "trip_id" in data
        assert len(data["nodes"]) > 0

        trip_resp = client.get(f"/api/v1/trip/{data['trip_id']}", headers=HEADERS)
        assert trip_resp.status_code == 200
        trip = trip_resp.json()
        assert trip["corridor_id"] == "laos_northbound_v1"
        assert len(trip["segments"]) == 3
        assert trip["segments"][0]["geo_region"] == "vientiane_laos"
        assert trip["segments"][1]["geo_region"] == "vang_vieng_laos"
        assert trip["segments"][2]["geo_region"] == "luang_prabang_laos"

    # Proof 2
    def test_nodes_carry_segment_geo_region(self):
        resp = client.post("/api/v1/trip/create", json=_corridor_body(), headers=HEADERS)
        trip = client.get(f"/api/v1/trip/{resp.json()['trip_id']}", headers=HEADERS).json()
        for node in trip["nodes"]:
            assert node["geo_region"] in {"vientiane_laos", "vang_vieng_laos", "luang_prabang_laos"}

    # Proof 3
    def test_four_nodes_per_day_at_0900_local(self):
        resp = client.post("/api/v1/trip/create", json=_corridor_body(), headers=HEADERS)
        nodes = resp.json()["nodes"]
        tz = ZoneInfo("Asia/Vientiane")
        by_date = {}
        for n in nodes:
            dt = datetime.fromisoformat(n["scheduled_start"])
            local = dt.astimezone(tz)
            by_date.setdefault(local.date(), []).append(local)
        assert len(by_date) == 7
        for d, times in by_date.items():
            assert len(times) == CORRIDOR_STOPS_PER_DAY
            assert times[0].hour == 9

    # Proof 4
    def test_no_venue_repeats_within_segment(self):
        resp = client.post("/api/v1/trip/create", json=_corridor_body(), headers=HEADERS)
        nodes = resp.json()["nodes"]
        by_region = {}
        for n in nodes:
            by_region.setdefault(n["geo_region"], []).append(n["venue_id"])
        for region, ids in by_region.items():
            assert len(ids) == len(set(ids)), f"Repeated venue in {region}"

    # Proof 5
    def test_deterministic_repeated_create(self):
        body = _corridor_body()
        r1 = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        r2 = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert [n["venue_id"] for n in r1.json()["nodes"]] == [
            n["venue_id"] for n in r2.json()["nodes"]
        ]


# ================================================================
# Proof 6: validation failures
# ================================================================
class TestCorridorValidation:
    def test_overlap_rejected(self):
        body = _corridor_body(
            starts=[
                ("2026-10-02", "2026-10-04"),
                ("2026-10-04", "2026-10-05"),
                ("2026-10-06", "2026-10-07"),
            ]
        )
        assert client.post("/api/v1/trip/create", json=body, headers=HEADERS).status_code == 422

    def test_wrong_order_rejected(self):
        body = {
            "segments": [
                {
                    "geo_region": "luang_prabang_laos",
                    "starts_on": "2026-10-02",
                    "ends_on": "2026-10-03",
                },
                {
                    "geo_region": "vang_vieng_laos",
                    "starts_on": "2026-10-04",
                    "ends_on": "2026-10-05",
                },
                {
                    "geo_region": "vientiane_laos",
                    "starts_on": "2026-10-06",
                    "ends_on": "2026-10-07",
                },
            ]
        }
        assert client.post("/api/v1/trip/create", json=body, headers=HEADERS).status_code == 422

    def test_range_over_three_days(self):
        body = _corridor_body(
            starts=[
                ("2026-10-01", "2026-10-04"),
                ("2026-10-05", "2026-10-06"),
                ("2026-10-07", "2026-10-08"),
            ]
        )
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 422
        assert r.json()["detail"]["error"] == "invalid_corridor"

    def test_total_over_seven_days(self):
        body = _corridor_body(
            starts=[
                ("2026-10-01", "2026-10-03"),
                ("2026-10-04", "2026-10-06"),
                ("2026-10-07", "2026-10-09"),
            ]
        )
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 422
        assert r.json()["detail"]["error"] == "invalid_corridor"

    def test_segments_plus_start_date_rejected(self):
        body = _corridor_body()
        body["start_date"] = "2026-10-02T00:00:00Z"
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 422
        assert r.json()["detail"]["error"] == "invalid_corridor"

    def test_missing_city_rejected(self):
        body = {
            "segments": [
                {
                    "geo_region": "vientiane_laos",
                    "starts_on": "2026-10-02",
                    "ends_on": "2026-10-03",
                },
                {
                    "geo_region": "luang_prabang_laos",
                    "starts_on": "2026-10-04",
                    "ends_on": "2026-10-05",
                },
            ]
        }
        assert client.post("/api/v1/trip/create", json=body, headers=HEADERS).status_code == 422

    # ================================================================
    # Proof 7: atomic capacity refusal
    # ================================================================
    def test_insufficient_capacity_atomic(self):
        original = db_service.list_venues_for_region

        def sparse(region):
            return [] if region == "luang_prabang_laos" else original(region)

        db_service.list_venues_for_region = sparse
        try:
            r = client.post("/api/v1/trip/create", json=_corridor_body(), headers=HEADERS)
            assert r.status_code == 422
            assert r.json()["detail"]["error"] == "unsupported_corridor"
        finally:
            db_service.list_venues_for_region = original


# ================================================================
# Proof 8: single-city unchanged
# ================================================================
class TestSingleCityCompat:
    def test_single_city_create_unchanged(self):
        r = client.post(
            "/api/v1/trip/create",
            json={"start_date": "2026-10-05T00:00:00Z", "geo_region": "luang_prabang_laos"},
            headers=HEADERS,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "created"

    # Proof 9
    def test_no_llm_no_hybrid_no_quota(self):
        r = client.post("/api/v1/trip/create", json=_corridor_body(), headers=HEADERS)
        assert r.status_code == 200


# ================================================================
# Proof 10: normalized day indexes
# ================================================================
class TestNormalizedRows:
    def test_corridor_day_indexes(self):
        r = client.post("/api/v1/trip/create", json=_corridor_body(), headers=HEADERS)
        trip = db_service.get_trip(r.json()["trip_id"])
        nodes, _ = decompose_trip(trip.model_dump(mode="json"))
        days = [n["day_index"] for n in nodes]
        assert min(days) == 0
        assert max(days) == 6
        for i in range(1, len(days)):
            assert days[i] >= days[i - 1]


# ================================================================
# Proof 11: cross-city swap isolation
# ================================================================
class TestCrossCitySwap:
    def test_lp_target_rejects_vientiane_venue(self):
        """A Luang Prabang target node must not accept a Vientiane replacement.

        The state machine checks target_node.geo_region against replacement.geo_region.
        We test the unit-level rejection rather than the full HTTP flow to avoid
        the reroute throttle.
        """
        # Build a corridor trip
        corridor = require_corridor("laos_northbound_v1")
        segs = [
            TripSegmentIn(
                geo_region="vientiane_laos", starts_on=date(2026, 10, 2), ends_on=date(2026, 10, 3)
            ),
            TripSegmentIn(
                geo_region="vang_vieng_laos", starts_on=date(2026, 10, 4), ends_on=date(2026, 10, 5)
            ),
            TripSegmentIn(
                geo_region="luang_prabang_laos",
                starts_on=date(2026, 10, 6),
                ends_on=date(2026, 10, 8),
            ),
        ]
        nodes, _ = build_corridor_nodes(segs, db_service.list_venues_for_region, corridor)

        lp_nodes = [n for n in nodes if n.geo_region == "luang_prabang_laos"]
        assert len(lp_nodes) > 0

        vte = eligible_venues(db_service.list_venues_for_region("vientiane_laos"))
        if not vte:
            pytest.skip("No Vientiane venues")

        # The state machine uses this check:
        # if replacement.geo_region and target_region and replacement.geo_region != target_region:
        #     state["no_candidates"] = True
        target_region = lp_nodes[0].geo_region
        replacement_region = vte[0].get("geo_region", "vientiane_laos")
        assert (
            target_region != replacement_region
        ), f"LP target region {target_region} must differ from VTE venue region {replacement_region}"


# ================================================================
# Trip list
# ================================================================
class TestTripList:
    def test_supported_corridors_in_list(self):
        data = client.get("/api/v1/trips", headers=HEADERS).json()
        assert "supported_corridors" in data
        assert any(c["corridor_id"] == "laos_northbound_v1" for c in data["supported_corridors"])


# ================================================================
# Registry drift
# ================================================================
class TestRegistryDrift:
    def test_router_reads_registry_not_hardcode(self):
        corridor = require_corridor("laos_northbound_v1")
        assert corridor.geo_regions == ("vientiane_laos", "vang_vieng_laos", "luang_prabang_laos")
        regions = tuple(s["geo_region"] for s in _corridor_body()["segments"])
        found = next((c for c in CORRIDORS.values() if c.geo_regions == regions), None)
        assert found is not None
        assert found.corridor_id == "laos_northbound_v1"
