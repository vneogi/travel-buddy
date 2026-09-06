"""SPEC-36: Corridor trip backend proof cases."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from main import app
from config.corridors import CORRIDORS, require_corridor
from config.regions import REGIONS
from models.schemas import TripState, TripSegmentIn, EventType
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
            {"geo_region": r, "starts_on": s, "ends_on": e} for r, (s, e) in zip(regions, starts)
        ],
    }


def _create() -> dict:
    r = client.post("/api/v1/trip/create", json=_corridor_body(), headers=HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


def _catalog_ids(region: str) -> set:
    rows = db_service.list_venues_for_region(region)
    return {str(r["venue_id"]) for r in eligible_corridor_venues(rows)}


# ==================================================================
# Proof 1-5: create + structure
# ==================================================================
class TestCorridorCreate:
    def test_valid_create_returns_trip_with_segments(self):
        data = _create()
        assert data["status"] == "created"
        assert "trip_id" in data
        assert len(data["nodes"]) > 0
        trip = client.get(f"/api/v1/trip/{data['trip_id']}", headers=HEADERS).json()
        assert trip["corridor_id"] == "laos_northbound_v1"
        assert len(trip["segments"]) == 3
        assert [s["geo_region"] for s in trip["segments"]] == [
            "vientiane_laos",
            "vang_vieng_laos",
            "luang_prabang_laos",
        ]

    def test_nodes_belong_to_segment_catalog(self):
        data = _create()
        trip = client.get(f"/api/v1/trip/{data['trip_id']}", headers=HEADERS).json()
        for node in trip["nodes"]:
            region = node["geo_region"]
            catalog = _catalog_ids(region)
            assert node["venue_id"] in catalog, (
                f"venue_id {node['venue_id']} not in {region} catalog"
            )

    def test_four_nodes_per_day_with_spacing(self):
        data = _create()
        by_date: dict = {}
        for n in data["nodes"]:
            dt = datetime.fromisoformat(n["scheduled_start"])
            local = dt.astimezone(TZ)
            by_date.setdefault(local.date(), []).append(local)
        assert len(by_date) == 7
        for d, times in by_date.items():
            assert len(times) == CORRIDOR_STOPS_PER_DAY
            assert times[0].hour == 9 and times[0].minute == 0

    def test_intraday_gap_equals_duration_plus_30(self):
        data = _create()
        by_date: dict = {}
        for n in data["nodes"]:
            dt = datetime.fromisoformat(n["scheduled_start"])
            local = dt.astimezone(TZ)
            by_date.setdefault(local.date(), []).append((local, n["duration_minutes"]))
        for d, entries in by_date.items():
            for i in range(1, len(entries)):
                prev_start, prev_dur = entries[i - 1]
                curr_start, _ = entries[i]
                expected = prev_start + timedelta(minutes=prev_dur + 30)
                assert curr_start == expected, (
                    f"On {d}, node {i}: expected {expected}, got {curr_start}"
                )

    def test_no_venue_repeats_within_segment(self):
        data = _create()
        by_region: dict = {}
        for n in data["nodes"]:
            by_region.setdefault(n["geo_region"], []).append(n["venue_id"])
        for region, ids in by_region.items():
            assert len(ids) == len(set(ids))

    def test_deterministic_repeated_create(self):
        body = _corridor_body()
        r1 = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        r2 = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert [n["venue_id"] for n in r1.json()["nodes"]] == [
            n["venue_id"] for n in r2.json()["nodes"]
        ]


# ==================================================================
# Proof 6: validation (all assert detail.error == invalid_corridor)
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
        )

    def test_duplicate_city_rejected(self):
        self._assert_invalid(
            {
                "segments": [
                    {
                        "geo_region": "vientiane_laos",
                        "starts_on": "2026-10-02",
                        "ends_on": "2026-10-03",
                    },
                    {
                        "geo_region": "vientiane_laos",
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
        )


# ==================================================================
# Proof 7: atomic capacity refusal
# ==================================================================
class TestAtomicRefusal:
    def test_insufficient_capacity_leaves_no_trace(self):
        original = db_service.list_venues_for_region
        trips_before = set(db_service._trips.keys())
        nodes_before = set(db_service._trip_nodes.keys())
        parties_before = set(db_service._parties.keys())

        def sparse(region):
            return [] if region == "luang_prabang_laos" else original(region)

        db_service.list_venues_for_region = sparse
        try:
            r = client.post("/api/v1/trip/create", json=_corridor_body(), headers=HEADERS)
            assert r.status_code == 422
            assert r.json()["detail"]["error"] == "unsupported_corridor"
            assert set(db_service._trips.keys()) == trips_before
            assert set(db_service._trip_nodes.keys()) == nodes_before
            assert set(db_service._parties.keys()) == parties_before
        finally:
            db_service.list_venues_for_region = original


# ==================================================================
# Proof 8: single-city response shape
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
        for key in ("trip_id", "status", "nodes", "locked_count", "party", "message"):
            assert key in data, f"Missing key {key}"
        assert data["status"] == "created"
        trip = client.get(f"/api/v1/trip/{data['trip_id']}", headers=HEADERS).json()
        assert trip.get("corridor_id") is None

    def test_single_city_missing_start_date_returns_422(self):
        r = client.post(
            "/api/v1/trip/create",
            json={"geo_region": "luang_prabang_laos"},
            headers=HEADERS,
        )
        assert r.status_code == 422


# ==================================================================
# Proof 9: no LLM, no hybrid search, no quota consumed
# ==================================================================
class TestNoLLMNoQuota:
    def test_corridor_create_never_invokes_heavy_path(self):
        from agents.state_machine import state_machine as sm_inst
        from services.llm_service import llm_service as llm_inst
        from agents.router_agent import router_agent as ra_inst

        originals = {}
        calls = {}

        def make_bomb(name, orig):
            def bomb(*a, **kw):
                calls[name] = True
                raise AssertionError(f"{name} called during corridor create")

            return bomb

        targets = {
            "process_event": sm_inst,
            "hybrid_venue_search": db_service,
            "consume_reroute": db_service,
            "generate_itinerary_response": llm_inst,
            "generate_info_response": llm_inst,
            "generate_response": ra_inst,
        }
        for name, obj in targets.items():
            originals[name] = getattr(obj, name)
            setattr(obj, name, make_bomb(name, originals[name]))

        user = "spec36-quota-user"
        hdrs = auth(user)
        db_service.get_or_create_user(user)
        reroute_before = db_service._users[user]["daily_reroute_count"]

        try:
            r = client.post("/api/v1/trip/create", json=_corridor_body(), headers=hdrs)
            assert r.status_code == 200
            assert not calls, f"Unexpected calls: {list(calls)}"
            reroute_after = db_service._users[user]["daily_reroute_count"]
            assert reroute_after == reroute_before, (
                f"Quota changed: {reroute_before} -> {reroute_after}"
            )
        finally:
            for name, obj in targets.items():
                setattr(obj, name, originals[name])


# ==================================================================
# Proof 10: normalized rows
# ==================================================================
class TestNormalizedRows:
    def test_persisted_rows_correctness(self):
        data = _create()
        rows = db_service.get_trip_nodes(data["trip_id"])
        assert len(rows) > 0
        days = [r["day_index"] for r in rows]
        assert days[0] == 0
        assert days[-1] == 6
        for i in range(1, len(days)):
            assert days[i] >= days[i - 1]
        seqs = [r["seq"] for r in rows]
        assert len(seqs) == len(set(seqs))
        for r in rows:
            assert r["geo_region"] in {
                "vientiane_laos",
                "vang_vieng_laos",
                "luang_prabang_laos",
            }

    def test_normaliser_uses_config_regions(self):
        from services import itinerary_normaliser

        assert not hasattr(itinerary_normaliser, "REGION_TIMEZONES")


# ==================================================================
# Proof 11: cross-city swap isolation via HTTP
# ==================================================================
class TestCrossCitySwap:
    def test_swap_lp_target_searches_lp_catalog(self):
        """POST /trip/event swap for a Luang Prabang node must search LP,
        and reject a Vientiane venue replacement."""
        data = _create()
        trip_id = data["trip_id"]
        lp_node = next(n for n in data["nodes"] if n["geo_region"] == "luang_prabang_laos")
        vte_rows = eligible_venues(db_service.list_venues_for_region("vientiane_laos"))
        if not vte_rows:
            pytest.skip("No Vientiane venues seeded")
        vte_venue_id = str(vte_rows[0]["venue_id"])

        # Attempt swap with a Vientiane venue on an LP target.
        r = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "swap_activity",
                "message": "Swap to a Vientiane place",
                "target_node_id": lp_node["node_id"],
                "preferences": {"replacement_venue_id": vte_venue_id},
            },
            headers=HEADERS,
        )
        assert r.status_code == 409, f"Expected 409, got {r.status_code}: {r.text}"
        assert r.json()["detail"]["error"] == "replacement_wrong_region"
        # Router catches cross-region replacement at HTTP layer.
        trip_after = client.get(f"/api/v1/trip/{trip_id}", headers=HEADERS).json()
        lp_after = next(n for n in trip_after["nodes"] if n["node_id"] == lp_node["node_id"])
        # The LP node must NOT have been replaced by the Vientiane venue.
        assert lp_after["venue_id"] != vte_venue_id, (
            "Cross-region swap was accepted -- should have been rejected"
        )
        assert lp_after["geo_region"] == "luang_prabang_laos"

    def test_swap_lp_target_search_receives_lp_region(self):
        """Spy hybrid_venue_search to verify geo_region=luang_prabang_laos."""
        data = _create()
        trip_id = data["trip_id"]
        lp_node = next(n for n in data["nodes"] if n["geo_region"] == "luang_prabang_laos")
        original = db_service.hybrid_venue_search
        search_calls = []

        def spy_search(**kw):
            search_calls.append(kw)
            return original(**kw)

        db_service.hybrid_venue_search = spy_search
        try:
            r = client.post(
                "/api/v1/trip/event",
                json={
                    "trip_id": trip_id,
                    "event_type": "swap_activity",
                    "message": "Find me a temple",
                    "target_node_id": lp_node["node_id"],
                },
                headers=HEADERS,
            )
            assert r.status_code == 200
            assert len(search_calls) >= 1, "hybrid_venue_search never called"
            assert search_calls[0]["geo_region"] == "luang_prabang_laos", (
                f"Search used {search_calls[0]['geo_region']}, not luang_prabang_laos"
            )
        finally:
            db_service.hybrid_venue_search = original


# ==================================================================
# Proof 12: earlier-city cancel/swap preserves next-city boundary
# ==================================================================
class TestEarlierCityMutation:
    def test_cancel_skips_target_preserves_next_city(self):
        """Cancel a Vientiane node: target becomes SKIPPED, VV boundary intact."""
        data = _create()
        trip_id = data["trip_id"]
        vv_nodes = [n for n in data["nodes"] if n["geo_region"] == "vang_vieng_laos"]
        vv_first_start = vv_nodes[0]["scheduled_start"]
        vte_node = next(n for n in data["nodes"] if n["geo_region"] == "vientiane_laos")
        target_id = vte_node["node_id"]
        assert vte_node["status"] == "pending", "Precondition: target is pending"

        r = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "cancel_activity",
                "message": f"Cancel {vte_node['venue_name']}",
                "target_node_id": target_id,
            },
            headers=HEADERS,
        )
        assert r.status_code == 200, f"Cancel returned {r.status_code}: {r.text}"

        trip_after = client.get(f"/api/v1/trip/{trip_id}", headers=HEADERS).json()

        # 1. The cancelled node is now skipped.
        target_after = next(n for n in trip_after["nodes"] if n["node_id"] == target_id)
        assert target_after["status"] == "skipped", (
            f"Expected skipped, got {target_after['status']}"
        )

        # 2. Vang Vieng first node timestamp unchanged.
        vv_after = [n for n in trip_after["nodes"] if n["geo_region"] == "vang_vieng_laos"]
        assert len(vv_after) > 0, "Vang Vieng nodes disappeared"
        assert vv_after[0]["scheduled_start"] == vv_first_start, (
            f"VV boundary moved: {vv_first_start} -> {vv_after[0]['scheduled_start']}"
        )

    def test_swap_changes_venue_preserves_next_city(self):
        """Swap a VV node with an explicit same-region replacement: venue_id
        changes, LP boundary stays fixed."""
        data = _create()
        trip_id = data["trip_id"]
        vv_nodes = [n for n in data["nodes"] if n["geo_region"] == "vang_vieng_laos"]
        lp_nodes = [n for n in data["nodes"] if n["geo_region"] == "luang_prabang_laos"]
        lp_first_start = lp_nodes[0]["scheduled_start"]
        vv_target = vv_nodes[0]
        original_venue_id = vv_target["venue_id"]

        # Find a same-region venue NOT already in the trip.
        trip_vids = {n["venue_id"] for n in data["nodes"] if n["geo_region"] == "vang_vieng_laos"}
        all_vv = eligible_corridor_venues(db_service.list_venues_for_region("vang_vieng_laos"))
        unused = [v for v in all_vv if str(v["venue_id"]) not in trip_vids]
        assert len(unused) > 0, "Need at least one unused VV venue for swap"
        replacement_vid = str(unused[0]["venue_id"])

        r = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "swap_activity",
                "message": "Swap to a different VV venue",
                "target_node_id": vv_target["node_id"],
                "preferences": {"replacement_venue_id": replacement_vid},
            },
            headers=HEADERS,
        )
        assert r.status_code == 200, f"Swap returned {r.status_code}: {r.text}"

        trip_after = client.get(f"/api/v1/trip/{trip_id}", headers=HEADERS).json()

        # 1. The swapped node now has the new venue_id.
        swapped = next(n for n in trip_after["nodes"] if n["node_id"] == vv_target["node_id"])
        assert swapped["venue_id"] == replacement_vid, (
            f"venue_id not changed: expected {replacement_vid}, got {swapped['venue_id']}"
        )
        assert swapped["venue_id"] != original_venue_id, "venue_id unchanged after swap"
        assert swapped["geo_region"] == "vang_vieng_laos"

        # 2. LP first node timestamp unchanged.
        lp_after = [n for n in trip_after["nodes"] if n["geo_region"] == "luang_prabang_laos"]
        assert len(lp_after) > 0, "LP nodes disappeared"
        assert lp_after[0]["scheduled_start"] == lp_first_start, (
            f"LP boundary moved: {lp_first_start} -> {lp_after[0]['scheduled_start']}"
        )


# ==================================================================
# Trip list: registry drives router
# ==================================================================
class TestTripList:
    def test_supported_corridors_in_list(self):
        data = client.get("/api/v1/trips", headers=HEADERS).json()
        assert "supported_corridors" in data
        for c in data["supported_corridors"]:
            assert c["corridor_id"] in CORRIDORS
            reg = CORRIDORS[c["corridor_id"]]
            assert list(c["geo_regions"]) == list(reg.geo_regions)
            assert c["max_days"] == reg.max_days
            assert c["max_days_per_segment"] == reg.max_days_per_segment

    def test_validation_uses_registry_order(self):
        body = {
            "segments": [
                {
                    "geo_region": "vang_vieng_laos",
                    "starts_on": "2026-10-02",
                    "ends_on": "2026-10-03",
                },
                {
                    "geo_region": "vientiane_laos",
                    "starts_on": "2026-10-04",
                    "ends_on": "2026-10-05",
                },
                {
                    "geo_region": "luang_prabang_laos",
                    "starts_on": "2026-10-06",
                    "ends_on": "2026-10-07",
                },
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
            corridor_summaries = [t for t in data["trips"] if t.get("corridor_id")]
            if corridor_summaries:
                assert ft.get("corridor_id") == "laos_northbound_v1"
