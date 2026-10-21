"""Tests for typed Ask-to-Add (add_activity + preferences.mode=ask_to_add)."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from agents.state_machine import state_machine
from models.schemas import EventType, NodeStatus, TripNode, TripState, VenueRAG
from services.ask_service import AskIntent, AskPath, TrustTier, handle_ask_to_add

OPEN_ALL_DAY = {d: [["08:00", "22:00"]] for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}


def _venue(
    vid,
    name,
    *,
    geo="vientiane_laos",
    cat="temple",
    lat=17.9640,
    lng=102.6120,
    dwell=45,
    hours_structured=None,
):
    return VenueRAG(
        venue_id=vid,
        name=name,
        description=f"Test {name}",
        micro_location="nam_phou_fountain",
        lat=lat,
        lng=lng,
        category=cat,
        geo_region=geo,
        typical_dwell_minutes=dwell,
        opening_hours_structured=hours_structured if hours_structured is not None else OPEN_ALL_DAY,
        opening_hours="09:00-22:00",
    )


class FakeDb:
    def __init__(self, venues):
        self._venues = [v.model_dump() for v in venues]

    def get_venue_by_id(self, venue_id):
        for v in self._venues:
            if str(v.get("venue_id")) == str(venue_id):
                return VenueRAG(**{k: v2 for k, v2 in v.items() if k != "embedding"})
        return None

    def list_venues_for_region(self, geo_region):
        return [dict(v) for v in self._venues if v.get("geo_region") == geo_region]


@pytest.fixture
def now_utc():
    return datetime(2026, 10, 2, 4, 0, tzinfo=timezone.utc)


@pytest.fixture
def trip_nodes(now_utc):
    return [
        {
            "node_id": "n1",
            "venue_name": "Context Temple",
            "venue_id": "ctx-1",
            "scheduled_start": now_utc.isoformat(),
            "duration_minutes": 60,
            "geo_region": "vientiane_laos",
            "is_locked": False,
            "status": "pending",
            "lat": 17.96345,
            "lng": 102.61112,
            "vibe_tags": [],
        }
    ]


@pytest.fixture
def db():
    return FakeDb(
        [
            _venue("vt-1", "Wat Si Saket"),
            _venue("vt-2", "Saffron Cafe", cat="cafe", dwell=30),
            _venue("infra-1", "Hospital", cat="hospital"),
            _venue("dubai-1", "Dubai Mall", geo="dubai_uae"),
            _venue("no-dwell", "Mystery Place", dwell=None),
        ]
    )


class TestSuccessfulAdd:
    def test_vientiane_venue_adds_one_node(self, now_utc, trip_nodes, db):
        prefs = {"mode": "ask_to_add", "venue_id": "vt-1"}
        resp = handle_ask_to_add(prefs, trip_nodes, now_utc, "vientiane_laos", db)
        assert resp.tier == TrustTier.ASSERT
        assert resp.path == AskPath.GROUNDED_DETERMINISTIC
        assert resp.added_node is not None
        assert resp.added_node["venue_id"] == "vt-1"
        assert resp.added_node["venue_name"] == "Wat Si Saket"
        assert resp.added_node["duration_minutes"] == 45
        assert resp.added_node["geo_region"] == "vientiane_laos"
        assert resp.added_node["node_id"].startswith("n-")

    def test_uses_scheduled_start_from_prefs(self, now_utc, trip_nodes, db):
        prefs = {
            "mode": "ask_to_add",
            "venue_id": "vt-1",
            "scheduled_start": "2026-10-02T12:00:00+07:00",
        }
        resp = handle_ask_to_add(prefs, trip_nodes, now_utc, "vientiane_laos", db)
        assert resp.added_node is not None
        assert "12:00" in resp.answer

    def test_other_nodes_unchanged(self, now_utc, trip_nodes, db):
        orig = [(n["node_id"], n["scheduled_start"]) for n in trip_nodes]
        handle_ask_to_add(
            {"mode": "ask_to_add", "venue_id": "vt-1"}, trip_nodes, now_utc, "vientiane_laos", db
        )
        assert [(n["node_id"], n["scheduled_start"]) for n in trip_nodes] == orig

    def test_never_dubai_for_vientiane(self, now_utc, trip_nodes, db):
        resp = handle_ask_to_add(
            {"mode": "ask_to_add", "venue_id": "vt-1"}, trip_nodes, now_utc, "vientiane_laos", db
        )
        assert resp.added_node["geo_region"] == "vientiane_laos"


class TestRefusals:
    def test_duplicate_venue_refuses(self, now_utc, db):
        nodes = [
            {
                "node_id": "n1",
                "venue_name": "Wat Si Saket",
                "venue_id": "vt-1",
                "scheduled_start": now_utc.isoformat(),
                "duration_minutes": 60,
                "geo_region": "vientiane_laos",
                "is_locked": False,
                "status": "pending",
                "lat": 17.96345,
                "lng": 102.61112,
            }
        ]
        resp = handle_ask_to_add(
            {"mode": "ask_to_add", "venue_id": "vt-1"}, nodes, now_utc, "vientiane_laos", db
        )
        assert resp.tier == TrustTier.REFUSE
        assert resp.added_node is None
        assert "already" in resp.answer.lower()

    def test_missing_venue_id_refuses(self, now_utc, trip_nodes, db):
        resp = handle_ask_to_add({"mode": "ask_to_add"}, trip_nodes, now_utc, "vientiane_laos", db)
        assert resp.tier == TrustTier.REFUSE
        assert resp.added_node is None

    def test_unknown_dwell_refuses(self, now_utc, trip_nodes, db):
        resp = handle_ask_to_add(
            {"mode": "ask_to_add", "venue_id": "no-dwell"},
            trip_nodes,
            now_utc,
            "vientiane_laos",
            db,
        )
        assert resp.tier == TrustTier.REFUSE
        assert "duration" in resp.answer.lower()

    def test_infrastructure_refuses(self, now_utc, trip_nodes, db):
        resp = handle_ask_to_add(
            {"mode": "ask_to_add", "venue_id": "infra-1"}, trip_nodes, now_utc, "vientiane_laos", db
        )
        assert resp.tier == TrustTier.REFUSE
        assert "infrastructure" in resp.answer.lower()

    def test_cross_region_refuses(self, now_utc, trip_nodes, db):
        resp = handle_ask_to_add(
            {"mode": "ask_to_add", "venue_id": "dubai-1"}, trip_nodes, now_utc, "vientiane_laos", db
        )
        assert resp.tier == TrustTier.REFUSE
        assert "region" in resp.answer.lower()

    def test_bare_add_via_state_machine(self, now_utc):
        trip = TripState(
            trip_id="t1",
            user_id="u1",
            geo_region="vientiane_laos",
            nodes=[
                TripNode(
                    venue_name="Temple",
                    venue_id="ctx-1",
                    scheduled_start=now_utc,
                    duration_minutes=60,
                    geo_region="vientiane_laos",
                )
            ],
        )
        result = asyncio.run(
            state_machine.process_event(
                trip_state=trip,
                event_type=EventType.ADD_ACTIVITY.value,
                message="add something",
                now_utc=now_utc,
            )
        )
        assert len(result["updated_trip_state"].nodes) == 1
        assert "specific venue" in result.get("response", "").lower()


class TestBookingReachability:
    def test_fits_next_lock_passes(self, now_utc, db):
        lock_start = now_utc + timedelta(minutes=120)
        nodes = [
            {
                "node_id": "n1",
                "venue_name": "Ctx",
                "venue_id": "ctx-1",
                "scheduled_start": now_utc.isoformat(),
                "duration_minutes": 30,
                "geo_region": "vientiane_laos",
                "is_locked": False,
                "status": "pending",
                "lat": 17.96345,
                "lng": 102.61112,
            },
            {
                "node_id": "lock-1",
                "venue_name": "Train",
                "venue_id": "lock-v1",
                "scheduled_start": lock_start.isoformat(),
                "duration_minutes": 60,
                "geo_region": "vientiane_laos",
                "is_locked": True,
                "status": "pending",
                "node_kind": "booking",
                "booking_type": "train",
                "lat": 17.975,
                "lng": 102.625,
            },
        ]
        resp = handle_ask_to_add(
            {
                "mode": "ask_to_add",
                "venue_id": "vt-2",
                "scheduled_start": (now_utc + timedelta(minutes=35)).isoformat(),
            },
            nodes,
            now_utc,
            "vientiane_laos",
            db,
        )
        assert resp.added_node is not None

    def test_violates_next_lock_refuses(self, now_utc, db):
        """R17 sabotage target: dropping walk from fits_next_lock must fail THIS test."""
        lock_start = now_utc + timedelta(minutes=50)
        nodes = [
            {
                "node_id": "n1",
                "venue_name": "Ctx",
                "venue_id": "ctx-1",
                "scheduled_start": now_utc.isoformat(),
                "duration_minutes": 30,
                "geo_region": "vientiane_laos",
                "is_locked": False,
                "status": "pending",
                "lat": 17.96345,
                "lng": 102.61112,
            },
            {
                "node_id": "lock-1",
                "venue_name": "Train",
                "venue_id": "lock-v1",
                "scheduled_start": lock_start.isoformat(),
                "duration_minutes": 60,
                "geo_region": "vientiane_laos",
                "is_locked": True,
                "status": "pending",
                "node_kind": "booking",
                "booking_type": "train",
                "lat": 17.975,
                "lng": 102.625,
            },
        ]
        resp = handle_ask_to_add(
            {"mode": "ask_to_add", "venue_id": "vt-1", "scheduled_start": now_utc.isoformat()},
            nodes,
            now_utc,
            "vientiane_laos",
            db,
        )
        assert resp.tier == TrustTier.REFUSE
        assert "unreachable" in resp.answer.lower()


class TestZeroLLM:
    def test_no_llm_calls(self, now_utc):
        trip = TripState(
            trip_id="t1",
            user_id="u1",
            geo_region="vientiane_laos",
            nodes=[
                TripNode(
                    venue_name="Temple",
                    venue_id="ctx-1",
                    scheduled_start=now_utc,
                    duration_minutes=60,
                    geo_region="vientiane_laos",
                )
            ],
        )
        with patch(
            "services.llm_service.llm_service.complete",
            side_effect=AssertionError("llm.complete called"),
        ):
            asyncio.run(
                state_machine.process_event(
                    trip_state=trip,
                    event_type=EventType.ADD_ACTIVITY.value,
                    message="add",
                    preferences={"mode": "ask_to_add", "venue_id": "vt-1"},
                    now_utc=now_utc,
                )
            )


# =========================================================================
# process_event contract tests
# =========================================================================

CONTRACT_KEYS = {
    "updated_trip_state",
    "response",
    "routing_tier_used",
    "from_cache",
    "venues_found",
    "schedule_warnings",
    "ask_response",
}


class TestProcessEventContract:
    """process_event must return the standard contract dict, not internal state."""

    def test_bare_refuse_returns_contract(self, now_utc):
        trip = TripState(
            trip_id="t1",
            user_id="u1",
            geo_region="vientiane_laos",
            nodes=[
                TripNode(
                    venue_name="Temple",
                    venue_id="ctx-1",
                    scheduled_start=now_utc,
                    duration_minutes=60,
                    geo_region="vientiane_laos",
                ),
            ],
        )
        result = asyncio.run(
            state_machine.process_event(
                trip_state=trip,
                event_type=EventType.ADD_ACTIVITY.value,
                message="add a cafe",
                now_utc=now_utc,
            )
        )
        # Must have all contract keys
        assert CONTRACT_KEYS <= set(result.keys()), (
            f"Missing keys: {CONTRACT_KEYS - set(result.keys())}"
        )
        # No internal keys leaked
        assert "trip_state" not in result
        assert "routing_tier" not in result
        assert "event_type" not in result

        # Values
        assert result["updated_trip_state"] is not None
        assert len(result["updated_trip_state"].nodes) == 1  # unchanged
        assert isinstance(result["response"], str)
        assert len(result["response"]) > 0
        assert result["routing_tier_used"] == "light"
        assert result["from_cache"] is False
        assert result["venues_found"] == []
        assert result["schedule_warnings"] == []
        assert result["ask_response"]["tier"] == "refuse"
        assert result["ask_response"]["added_node"] is None

    def test_typed_add_returns_contract(self, now_utc):
        """Typed add via process_event, with venue injected into db_service."""
        from services.database_service import db_service

        # Inject a venue so handle_ask_to_add finds it
        injected = VenueRAG(
            venue_id="contract-v1",
            name="Contract Temple",
            description="Test venue",
            micro_location="test_loc",
            lat=17.9640,
            lng=102.6120,
            category="temple",
            geo_region="vientiane_laos",
            typical_dwell_minutes=40,
            opening_hours_structured={
                d: [["08:00", "22:00"]] for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
            },
            opening_hours="08:00-22:00",
        )
        # Monkey-patch get_venue_by_id for this test
        orig_get = db_service.get_venue_by_id

        def _patched_get(venue_id):
            if venue_id == "contract-v1":
                return injected
            return orig_get(venue_id)

        db_service.get_venue_by_id = _patched_get
        try:
            trip = TripState(
                trip_id="t1",
                user_id="u1",
                geo_region="vientiane_laos",
                nodes=[
                    TripNode(
                        venue_name="Temple",
                        venue_id="ctx-1",
                        scheduled_start=now_utc,
                        duration_minutes=60,
                        geo_region="vientiane_laos",
                    ),
                ],
            )
            result = asyncio.run(
                state_machine.process_event(
                    trip_state=trip,
                    event_type=EventType.ADD_ACTIVITY.value,
                    message="add",
                    preferences={
                        "mode": "ask_to_add",
                        "venue_id": "contract-v1",
                    },
                    now_utc=now_utc,
                )
            )

            # Must have all contract keys
            assert CONTRACT_KEYS <= set(result.keys()), (
                f"Missing keys: {CONTRACT_KEYS - set(result.keys())}"
            )
            assert "trip_state" not in result
            assert "routing_tier" not in result

            # Success: node count incremented
            assert len(result["updated_trip_state"].nodes) == 2
            new_node = result["updated_trip_state"].nodes[1]
            assert new_node.venue_id == "contract-v1"
            assert new_node.venue_name == "Contract Temple"
            assert new_node.duration_minutes == 40

            # Original node unchanged
            orig = result["updated_trip_state"].nodes[0]
            assert orig.venue_id == "ctx-1"
            assert orig.scheduled_start == now_utc

            # Other contract fields
            assert isinstance(result["response"], str)
            assert "Contract Temple" in result["response"]
            assert result["routing_tier_used"] == "light"
            assert result["from_cache"] is False
            assert result["venues_found"] == []
            assert result["schedule_warnings"] == []
            assert result["ask_response"]["added_node"] is not None
            assert result["ask_response"]["added_node"]["venue_id"] == "contract-v1"
        finally:
            db_service.get_venue_by_id = orig_get
