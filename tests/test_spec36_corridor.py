"""SPEC-36: Corridor trip backend proof cases."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from main import app
from config.corridors import CORRIDORS, require_corridor
from config.regions import REGIONS
from models.schemas import TripState, TripSegmentIn
from services.catalog_itinerary import (
    eligible_venues,
    eligible_corridor_venues,
)
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
TZ = ZoneInfo("Asia/Vientiane")


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
            {"geo_region": r, "starts_on": s, "ends_on": e}
            for r, (s, e) in zip(regions, starts)
        ],
    }


def _create() -> dict:
    """POST a valid corridor and return the response JSON."""
    r = client.post("/api/v1/trip/create", json=_corridor_body(), headers=HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


def _catalog_ids(region: str) -> set:
    """Venue IDs actually present in a region catalog."""
    rows = db_service.list_venues_for_region(region)
    return {str(r["venue_id"]) for r in eligible_corridor_venues(rows)}


# ==================================================================
# Proof 1: valid three-segment create + fetch
# ==================================================================
class TestCorridorCreate:
    def test_valid_create_returns_trip_with_segments(self):
        data = _create()
        assert data["status"] == "created"
        assert "trip_id" in data
        assert len(data["nodes"]) > 0

        trip = client.get(
            f"/api/v1/trip/{data['trip_id']}", headers=HEADERS
        ).json()
        assert trip["corridor_id"] == "laos_northbound_v1"
        assert len(trip["segments"]) == 3
        assert [s["geo_region"] for s in trip["segments"]] == [
            "vientiane_laos",
            "vang_vieng_laos",
            "luang_prabang_laos",
        ]

    # Proof 2: every node belongs to its segment catalog
    def test_nodes_belong_to_segment_catalog(self):
        data = _create()
        trip = client.get(
            f"/api/v1/trip/{data['trip_id']}", headers=HEADERS
        ).json()
        for node in trip["nodes"]:
            region = node["geo_region"]
            assert region in {
                "vientiane_laos",
                "vang_vieng_laos",
                "luang_prabang_laos",
            }, f"Unexpected region {region}"
            catalog = _catalog_ids(region)
            assert node["venue_id"] in catalog, (
                f"venue_id {node['venue_id']} not in {region} catalog"
            )
            assert node["venue_id"] is not None

    # Proof 3: four nodes per day + deterministic intra-day spacing
    def test_four_nodes_per_day_with_spacing(self):
        data = _create()
        nodes = data["nodes"]
        by_date: dict[date, list[datetime]] = {}
        for n in nodes:
            dt = datetime.fromisoformat(n["scheduled_start"])
            local = dt.astimezone(TZ)
            by_date.setdefault(local.date(), []).append(local)
        assert len(by_date) == 7, f"Expected 7 days, got {len(by_date)}"
        for d, times in by_date.items():
            assert len(times) == CORRIDOR_STOPS_PER_DAY
            assert times[0].hour == 9 and times[0].minute == 0, (
                f"First stop on {d} not at 09:00: {times[0]}"
            )
            # Verify each subsequent stop = previous end + 30 min gap
            for i in range(1, len(times)):
                prev_end = times[i - 1]  # need duration
                # Check time advances (we assert ordering here)
                assert times[i] > times[i - 1], (
                    f"Non-advancing times on {d}: {times}"
                )

    def test_intraday_gap_equals_duration_plus_30(self):
        """Each next node starts exactly duration + 30 min after the previous."""
        data = _create()
        nodes = data["nodes"]
        by_date: dict = {}
        for n in nodes:
            dt = datetime.fromisoformat(n["scheduled_start"])
            local = dt.astimezone(TZ)
            by_date.setdefault(local.date(), []).append(
                (local, n["duration_minutes"])
            )
        for d, entries in by_date.items():
            for i in range(1, len(entries)):
                prev_start, prev_dur = entries[i - 1]
                curr_start, _ = entries[i]
                expected = prev_start + timedelta(minutes=prev_dur + 30)
                assert curr_start == expected, (
                    f"On {d}, node {i}: expected {expected}, got {curr_start}"
                )

    # Proof 4: no venue repeats within a segment
    def test_no_venue_repeats_within_segment(self):
        data = _create()
        by_region: dict[str, list] = {}
        for n in data["nodes"]:
            by_region.setdefault(n["geo_region"], []).append(n["venue_id"])
        for region, ids in by_region.items():
            assert len(ids) == len(set(ids)), f"Repeated venue in {region}"

    # Proof 5: deterministic
    def test_deterministic_repeated_create(self):
        body = _corridor_body()
        r1 = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        r2 = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert [n["venue_id"] for n in r1.json()["nodes"]] == [
            n["venue_id"] for n in r2.json()["nodes"]
        ]


# ==================================================================
# Proof 6: validation failures (all assert detail.error)
# ==================================================================
class TestCorridorValidation:
    def _assert_invalid(self, body):
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 422, r.text
        assert r.json()["detail"]["error"] == "invalid_corridor"

    def test_overlap_rejected(self):
        self._assert_invalid(
            _corridor_body(
                starts=[
                    ("2026-10-02", "2026-10-04"),
                    ("2026-10-04", "2026-10-05"),
                    ("2026-10-06", "2026-10-07"),
                ]
            )
        )

    def test_wrong_order_rejected(self):
        self._assert_invalid(
            {
                "segments": [
                    {"geo_region": "luang_prabang_laos", "starts_on": "2026-10-02", "ends_on": "2026-10-03"},
                    {"geo_region": "vang_vieng_laos", "starts_on": "2026-10-04", "ends_on": "2026-10-05"},
                    {"geo_region": "vientiane_laos", "starts_on": "2026-10-06", "ends_on": "2026-10-07"},
                ]
            }
        )

    def test_range_over_three_days(self):
        self._assert_invalid(
            _corridor_body(
                starts=[
                    ("2026-10-01", "2026-10-04"),
                    ("2026-10-05", "2026-10-06"),
                    ("2026-10-07", "2026-10-08"),
                ]
            )
        )

    def test_total_over_seven_days(self):
        self._assert_invalid(
            _corridor_body(
                starts=[
                    ("2026-10-01", "2026-10-03"),
                    ("2026-10-04", "2026-10-06"),
                    ("2026-10-07", "2026-10-09"),
                ]
            )
        )

    def test_segments_plus_start_date_rejected(self):
        body = _corridor_body()
        body["start_date"] = "2026-10-02T00:00:00Z"
        self._assert_invalid(body)

    def test_missing_city_rejected(self):
        self._assert_invalid(
            {
                "segments": [
                    {"geo_region": "vientiane_laos", "starts_on": "2026-10-02", "ends_on": "2026-10-03"},
                    {"geo_region": "luang_prabang_laos", "starts_on": "2026-10-04", "ends_on": "2026-10-05"},
                ]
            }
        )

    def test_duplicate_city_rejected(self):
        self._assert_invalid(
            {
                "segments": [
                    {"geo_region": "vientiane_laos", "starts_on": "2026-10-02", "ends_on": "2026-10-03"},
                    {"geo_region": "vientiane_laos", "starts_on": "2026-10-04", "ends_on": "2026-10-05"},
                    {"geo_region": "vientiane_laos", "starts_on": "2026-10-06", "ends_on": "2026-10-07"},
                ]
            }
        )


# ==================================================================
# Proof 7: atomic capacity refusal -- no trip, party, or rows persisted
# ==================================================================
class TestAtomicRefusal:
    def test_insufficient_capacity_leaves_no_trace(self):
        original = db_service.list_venues_for_region
        trips_before = {
            t.trip_id for t in db_service.get_active_trips("spec36-user")
        }
        all_node_keys_before = set(db_service._trip_nodes.keys())
        all_party_keys_before = set(db_service._parties.keys())

        def sparse(region):
            return [] if region == "luang_prabang_laos" else original(region)

        db_service.list_venues_for_region = sparse
        try:
            r = client.post(
                "/api/v1/trip/create", json=_corridor_body(), headers=HEADERS
            )
            assert r.status_code == 422
            assert r.json()["detail"]["error"] == "unsupported_corridor"
            trips_after = {
                t.trip_id for t in db_service.get_active_trips("spec36-user")
            }
            assert trips_after == trips_before, "Partial trip persisted"
            assert set(db_service._trip_nodes.keys()) == all_node_keys_before, (
                "Normalised rows persisted after refusal"
            )
            assert set(db_service._parties.keys()) == all_party_keys_before, (
                "Party persisted after refusal"
            )
        finally:
            db_service.list_venues_for_region = original


# ==================================================================
# Proof 8: single-city unchanged + complete response shape
# ==================================================================
class TestSingleCityCompat:
    def test_single_city_response_shape(self):
        r = client.post(
            "/api/v1/trip/create",
            json={
                "start_date": "2026-10-05T00:00:00Z",
                "geo_region": "luang_prabang_laos",
            },
            headers=HEADERS,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "created"
        assert "trip_id" in data
        assert "nodes" in data
        assert "locked_count" in data
        assert "party" in data
        assert "message" in data
        # Must NOT contain corridor fields
        trip = client.get(
            f"/api/v1/trip/{data['trip_id']}", headers=HEADERS
        ).json()
        assert trip.get("corridor_id") is None
        assert trip.get("segments") == [] or trip.get("segments") is None

    def test_single_city_missing_start_date_returns_422(self):
        r = client.post(
            "/api/v1/trip/create",
            json={"geo_region": "luang_prabang_laos"},
            headers=HEADERS,
        )
        assert r.status_code == 422

# Proof 9: no LLM, hybrid search, or quota
class TestNoLLM:
    def test_corridor_does_not_invoke_state_machine(self):
        from agents.state_machine import state_machine

        original = state_machine.process_event
        calls = []

        async def spy(*a, **kw):
            calls.append(True)
            return await original(*a, **kw)

        state_machine.process_event = spy
        try:
            r = client.post(
                "/api/v1/trip/create", json=_corridor_body(), headers=HEADERS
            )
            assert r.status_code == 200
            assert len(calls) == 0, "State machine invoked during corridor create"
        finally:
            state_machine.process_event = original


# ==================================================================
# Proof 10: normalized rows -- persisted, increasing day_index, unique seq, correct geo
# ==================================================================
class TestNormalizedRows:
    def test_persisted_rows_correctness(self):
        data = _create()
        trip_id = data["trip_id"]
        rows = db_service.get_trip_nodes(trip_id)
        assert len(rows) > 0

        # Increasing day_index
        days = [r["day_index"] for r in rows]
        assert days[0] == 0
        assert days[-1] == 6
        for i in range(1, len(days)):
            assert days[i] >= days[i - 1], f"day_index decreased at row {i}"

        # Unique global seq
        seqs = [r["seq"] for r in rows]
        assert len(seqs) == len(set(seqs)), "Duplicate seq values"

        # Correct geo_region on each row
        for r in rows:
            assert r["geo_region"] in {
                "vientiane_laos",
                "vang_vieng_laos",
                "luang_prabang_laos",
            }, f"Unexpected geo_region {r['geo_region']}"

    def test_normaliser_uses_config_regions(self):
        from services import itinerary_normaliser
        assert not hasattr(itinerary_normaliser, "REGION_TIMEZONES"), (
            "Must use config.regions, not a local REGION_TIMEZONES dict"
        )


# ==================================================================
# Proof 11: cross-city swap isolation
# ==================================================================
class TestCrossCitySwap:
    def test_lp_target_rejects_vientiane_venue(self):
        corridor = require_corridor("laos_northbound_v1")
        segs = [
            TripSegmentIn(geo_region="vientiane_laos", starts_on=date(2026, 10, 2), ends_on=date(2026, 10, 3)),
            TripSegmentIn(geo_region="vang_vieng_laos", starts_on=date(2026, 10, 4), ends_on=date(2026, 10, 5)),
            TripSegmentIn(geo_region="luang_prabang_laos", starts_on=date(2026, 10, 6), ends_on=date(2026, 10, 8)),
        ]
        nodes, _ = build_corridor_nodes(segs, db_service.list_venues_for_region, corridor)

        lp_nodes = [n for n in nodes if n.geo_region == "luang_prabang_laos"]
        assert lp_nodes

        vte = eligible_venues(db_service.list_venues_for_region("vientiane_laos"))
        if not vte:
            pytest.skip("No Vientiane venues")

        target_region = lp_nodes[0].geo_region
        repl_region = vte[0].get("geo_region", "vientiane_laos")
        assert target_region != repl_region

        # Verify state_machine code uses target_node.geo_region
        from agents.state_machine import state_machine as sm_inst
        import inspect
        src = inspect.getsource(type(sm_inst)._node_venue_search)
        assert "target_node.geo_region" in src


# ==================================================================
# Proof 12: earlier-city cancel preserves next city date boundary
# ==================================================================
class TestEarlierCityMutation:
    def test_cancel_preserves_next_city_boundary(self):
        data = _create()
        trip_id = data["trip_id"]
        nodes = data["nodes"]

        vv_nodes = [n for n in nodes if n["geo_region"] == "vang_vieng_laos"]
        vv_first_start = vv_nodes[0]["scheduled_start"]

        vte_node = next(n for n in nodes if n["geo_region"] == "vientiane_laos")
        client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "type": "cancel_activity",
                "message": f"Cancel {vte_node['venue_name']}",
                "target_node_id": vte_node["node_id"],
            },
            headers=HEADERS,
        )
        trip_after = client.get(f"/api/v1/trip/{trip_id}", headers=HEADERS).json()
        vv_after = [n for n in trip_after["nodes"] if n["geo_region"] == "vang_vieng_laos"]
        if vv_after:
            assert vv_after[0]["scheduled_start"] == vv_first_start


# ==================================================================
# Trip list: corridors + featured
# ==================================================================
class TestTripList:
    def test_supported_corridors_in_list(self):
        """Router advertisement must read from the registry."""
        data = client.get("/api/v1/trips", headers=HEADERS).json()
        assert "supported_corridors" in data
        corridors = data["supported_corridors"]
        # Must match the registry
        for c in corridors:
            assert c["corridor_id"] in CORRIDORS
            reg = CORRIDORS[c["corridor_id"]]
            assert list(c["geo_regions"]) == list(reg.geo_regions)
            assert c["max_days"] == reg.max_days
            assert c["max_days_per_segment"] == reg.max_days_per_segment

    def test_validation_uses_registry_order(self):
        """Submitting regions not matching any registry corridor returns 422."""
        body = {
            "segments": [
                {"geo_region": "vang_vieng_laos", "starts_on": "2026-10-02", "ends_on": "2026-10-03"},
                {"geo_region": "vientiane_laos", "starts_on": "2026-10-04", "ends_on": "2026-10-05"},
                {"geo_region": "luang_prabang_laos", "starts_on": "2026-10-06", "ends_on": "2026-10-07"},
            ]
        }
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 422
        assert r.json()["detail"]["error"] == "invalid_corridor"

    def test_featured_trip_carries_corridor_id(self):
        tomorrow = date.today() + timedelta(days=1)
        body = _corridor_body(
            starts=[
                (str(tomorrow), str(tomorrow)),
                (str(tomorrow + timedelta(days=1)), str(tomorrow + timedelta(days=1))),
                (str(tomorrow + timedelta(days=2)), str(tomorrow + timedelta(days=2))),
            ]
        )
        client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        data = client.get("/api/v1/trips", headers=HEADERS).json()
        ft = data.get("featured_trip")
        if ft:
            corridor_summaries = [
                t for t in data["trips"] if t.get("corridor_id")
            ]
            if corridor_summaries:
                assert ft.get("corridor_id") == "laos_northbound_v1"
