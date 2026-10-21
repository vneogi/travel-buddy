"""SPEC-42 thin typed Move -- backend tests.

R17 sabotage: drop the walking term from ``fits_next_lock`` (non-flight
branch) -> ``TestNextLock::test_next_lock_walk_makes_tour_unreachable`` fails.
"""

import asyncio
import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from agents.state_machine import state_machine
from models.schemas import (
    CreationContext,
    EventType,
    NodeStatus,
    TripNode,
    TripSegment,
    TripState,
)
from services.database_service import db_service
from services.move_service import apply_move
from tests.conftest import auth

ICT = ZoneInfo("Asia/Bangkok")
VTE = "vientiane_laos"
LPQ = "luang_prabang_laos"

OPEN_ALL_DAY = {d: [["06:00", "23:00"]] for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}
LUNCH_ONLY = {d: [["11:00", "14:00"]] for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}

CONTRACT_KEYS = {
    "updated_trip_state",
    "response",
    "routing_tier_used",
    "from_cache",
    "venues_found",
    "schedule_warnings",
}


def local(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=ICT).astimezone(timezone.utc)


def node(nid, name, start, *, slot=None, dur=60, lat=17.9640, lng=102.6120, **kw):
    return TripNode(
        node_id=nid,
        venue_name=name,
        venue_id=f"v-{nid}",
        scheduled_start=start,
        duration_minutes=dur,
        slot_name=slot,
        lat=lat,
        lng=lng,
        geo_region=kw.pop("geo_region", VTE),
        opening_hours_structured=kw.pop("hours", OPEN_ALL_DAY),
        **kw,
    )


CATEGORIES = {
    "v-temple": "temple",
    "v-lunch": "restaurant",
    "v-aft": "market",
    "v-dinner": "restaurant",
    "v-lpq": "temple",
}


class FakeDb:
    def get_venue_by_id(self, venue_id):
        cat = CATEGORIES.get(venue_id)
        if cat is None:
            return None
        return SimpleNamespace(category=cat, opening_hours_structured=None)


DB = FakeDb()


def base_trip(extra=None, user_id="move-user"):
    nodes = [
        node("temple", "Wat Si Saket", local(2026, 10, 12, 9), slot="morning_tour"),
        node(
            "lunch",
            "Khop Chai Deu",
            local(2026, 10, 12, 12),
            slot="lunch",
            lat=17.9660,
            lng=102.6100,
        ),
        node("aft", "Night Market", local(2026, 10, 12, 14), slot="afternoon_evening_tour", dur=90),
    ]
    nodes += extra or []
    return TripState(
        trip_id=str(uuid.uuid4()),
        user_id=user_id,
        geo_region=VTE,
        nodes=nodes,
        creation_context=CreationContext(
            destination=VTE, start_date_local="2026-10-12", end_date_local="2026-10-14"
        ),
    )


def prefs(d, slot, mode="move"):
    return {"mode": mode, "target_date": d, "target_slot": slot}


def snapshot(nodes, skip):
    return {n.node_id: n.model_dump() for n in nodes if n.node_id != skip}


def local_date(n):
    return n.scheduled_start.astimezone(ICT).date()


# ---------------------------------------------------------------------------
class TestSuccessfulMove:
    def test_lunch_moves_to_dinner_same_date(self):
        trip = base_trip()
        before = snapshot(trip.nodes, "lunch")
        r = apply_move(trip, "lunch", prefs("2026-10-12", "dinner"), DB)
        assert r.ok, r.code
        moved = next(n for n in r.nodes if n.node_id == "lunch")
        assert moved.venue_id == "v-lunch"
        assert moved.slot_name == "dinner"
        assert moved.scheduled_start.astimezone(ICT).hour >= 17
        assert local_date(moved) == date(2026, 10, 12)
        assert moved.duration_minutes == 60
        assert len(r.nodes) == 3
        assert snapshot(r.nodes, "lunch") == before

    def test_defer_to_empty_in_span_date(self):
        trip = base_trip()
        r = apply_move(trip, "temple", prefs("2026-10-13", "morning_tour"), DB)
        assert r.ok, r.code
        moved = next(n for n in r.nodes if n.node_id == "temple")
        assert local_date(moved) == date(2026, 10, 13)
        assert moved.slot_name == "morning_tour"
        oct12 = [n.node_id for n in r.nodes if local_date(n) == date(2026, 10, 12)]
        assert "temple" not in oct12
        assert set(oct12) == {"lunch", "aft"}

    def test_existing_duration_kept_not_invented(self):
        trip = base_trip()
        trip.nodes[0] = trip.nodes[0].model_copy(update={"duration_minutes": 75})
        r = apply_move(trip, "temple", prefs("2026-10-13", "afternoon_evening_tour"), DB)
        assert r.ok, r.code
        moved = next(n for n in r.nodes if n.node_id == "temple")
        assert moved.duration_minutes == 75
        assert moved.duration_minutes != 90


class TestRefusals:
    def _assert_refused(self, trip, r, code):
        assert not r.ok
        assert r.code == code
        assert [n.model_dump() for n in r.nodes] == [n.model_dump() for n in trip.nodes]

    @pytest.mark.parametrize("btype", ["hotel", "flight"])
    def test_locked_booking_refuses(self, btype):
        bk = node(
            "bk",
            "Booking",
            local(2026, 10, 12, 8),
            is_locked=True,
            node_kind="booking",
            booking_type=btype,
        )
        trip = base_trip([bk])
        r = apply_move(trip, "bk", prefs("2026-10-13", "morning_tour"), DB)
        self._assert_refused(trip, r, "locked_target")

    def test_occupied_target_slot_refuses(self):
        din = node("dinner", "Dinner Place", local(2026, 10, 12, 18), slot="dinner")
        trip = base_trip([din])
        r = apply_move(trip, "lunch", prefs("2026-10-12", "dinner"), DB)
        self._assert_refused(trip, r, "slot_occupied")

    def test_food_to_morning_refuses(self):
        trip = base_trip()
        r = apply_move(trip, "lunch", prefs("2026-10-13", "morning_tour"), DB)
        self._assert_refused(trip, r, "slot_type_mismatch")

    def test_activity_to_dinner_refuses(self):
        trip = base_trip()
        r = apply_move(trip, "temple", prefs("2026-10-13", "dinner"), DB)
        self._assert_refused(trip, r, "slot_type_mismatch")

    def test_corridor_cross_city_date_refuses(self):
        lp = node(
            "lpq", "Wat Xieng Thong", local(2026, 10, 14, 9), slot="morning_tour", geo_region=LPQ
        )
        trip = base_trip([lp])
        trip.creation_context = None
        trip.segments = [
            TripSegment(geo_region=VTE, starts_on=date(2026, 10, 12), ends_on=date(2026, 10, 13)),
            TripSegment(geo_region=LPQ, starts_on=date(2026, 10, 14), ends_on=date(2026, 10, 15)),
        ]
        r = apply_move(trip, "temple", prefs("2026-10-14", "afternoon_evening_tour"), DB)
        self._assert_refused(trip, r, "cross_city_date")

    def test_outside_span_refuses(self):
        trip = base_trip()
        r = apply_move(trip, "temple", prefs("2026-10-20", "morning_tour"), DB)
        self._assert_refused(trip, r, "outside_span")

    def test_closed_hours_refuses(self):
        trip = base_trip()
        trip.nodes[1] = trip.nodes[1].model_copy(update={"opening_hours_structured": LUNCH_ONLY})
        r = apply_move(trip, "lunch", prefs("2026-10-13", "dinner"), DB)
        self._assert_refused(trip, r, "closed_hours")

    def test_same_slot_same_date_is_noop_refuse(self):
        trip = base_trip()
        r = apply_move(trip, "lunch", prefs("2026-10-12", "lunch"), DB)
        self._assert_refused(trip, r, "no_change")

    @pytest.mark.parametrize("status", [NodeStatus.COMPLETED, NodeStatus.SKIPPED])
    def test_completed_or_skipped_refuses(self, status):
        trip = base_trip()
        trip.nodes[0] = trip.nodes[0].model_copy(update={"status": status})
        r = apply_move(trip, "temple", prefs("2026-10-13", "morning_tour"), DB)
        self._assert_refused(trip, r, "not_movable_status")

    def test_whole_day_excursion_refuses(self):
        trip = base_trip()
        trip.nodes[0] = trip.nodes[0].model_copy(update={"vibe_tags": ["day_trip"]})
        r = apply_move(trip, "temple", prefs("2026-10-13", "morning_tour"), DB)
        self._assert_refused(trip, r, "whole_day_excursion")

    def test_missing_target_refuses(self):
        trip = base_trip()
        self._assert_refused(
            trip, apply_move(trip, None, prefs("2026-10-13", "morning_tour"), DB), "missing_target"
        )
        self._assert_refused(
            trip,
            apply_move(trip, "ghost", prefs("2026-10-13", "morning_tour"), DB),
            "target_not_found",
        )

    def test_missing_mode_refuses(self):
        trip = base_trip()
        p = {"target_date": "2026-10-13", "target_slot": "morning_tour"}
        self._assert_refused(trip, apply_move(trip, "temple", p, DB), "invalid_mode")

    @pytest.mark.parametrize("slot", ["brunch", "", None, "09:00"])
    def test_bad_slot_refuses(self, slot):
        trip = base_trip()
        r = apply_move(trip, "temple", prefs("2026-10-13", slot), DB)
        self._assert_refused(trip, r, "invalid_slot")

    @pytest.mark.parametrize("d", [None, "13 Oct", "2026-13-01", "2026-10-13T09:00"])
    def test_bad_date_refuses(self, d):
        trip = base_trip()
        r = apply_move(trip, "temple", prefs(d, "morning_tour"), DB)
        self._assert_refused(trip, r, "invalid_date")


class TestNextLock:
    """Next locked non-hotel must stay reachable via the shared helper."""

    def _tour(self, hour, minute=0):
        # ~4.5 km from the temple -> walking well over 30 minutes.
        return node(
            "tour",
            "Booked Tour",
            local(2026, 10, 13, hour, minute),
            is_locked=True,
            node_kind="booking",
            booking_type="tour",
            lat=17.9990,
            lng=102.6420,
        )

    def test_next_lock_walk_makes_tour_unreachable(self):
        """R17 target: temple 09:00-10:00 cannot walk ~4.5 km to a 10:30 tour."""
        trip = base_trip([self._tour(10, 30)])
        r = apply_move(trip, "temple", prefs("2026-10-13", "morning_tour"), DB)
        assert not r.ok
        assert r.code == "next_lock_unreachable"

    def test_next_lock_reachable_passes(self):
        trip = base_trip([self._tour(12, 30)])
        r = apply_move(trip, "temple", prefs("2026-10-13", "morning_tour"), DB)
        assert r.ok, r.code

    def test_next_flight_remains_reachable(self):
        flight = node(
            "flt",
            "QV101",
            local(2026, 10, 13, 16),
            is_locked=True,
            node_kind="booking",
            booking_type="flight",
            dur=60,
        )
        trip = base_trip([flight])
        r = apply_move(trip, "temple", prefs("2026-10-13", "morning_tour"), DB)
        assert r.ok, r.code
        f = next(n for n in r.nodes if n.node_id == "flt")
        assert f.model_dump() == flight.model_dump()

    def test_flight_cutoff_refuses(self):
        flight = node(
            "flt",
            "QV101",
            local(2026, 10, 13, 11),
            is_locked=True,
            node_kind="booking",
            booking_type="flight",
        )
        trip = base_trip([flight])
        r = apply_move(trip, "temple", prefs("2026-10-13", "morning_tour"), DB)
        assert not r.ok
        assert r.code == "next_lock_unreachable"


# ---------------------------------------------------------------------------
class TestProcessEvent:
    def _run(self, trip, target, p):
        with (
            patch.object(db_service, "get_venue_by_id", DB.get_venue_by_id),
            patch("services.llm_service.llm_service.complete", new_callable=AsyncMock) as llm,
        ):
            result = asyncio.run(
                state_machine.process_event(
                    trip_state=trip,
                    event_type=EventType.MOVE_ACTIVITY.value,
                    message="Move",
                    target_node_id=target,
                    preferences=p,
                )
            )
        return result, llm

    def test_contract_keys_on_success(self):
        trip = base_trip()
        result, llm = self._run(trip, "lunch", prefs("2026-10-12", "dinner"))
        assert CONTRACT_KEYS <= set(result)
        assert "trip_state" not in result
        assert "move_refused" not in result
        moved = next(n for n in result["updated_trip_state"].nodes if n.node_id == "lunch")
        assert moved.slot_name == "dinner"
        assert result["venues_found"] == []
        llm.assert_not_called()

    def test_contract_keys_on_refusal(self):
        trip = base_trip()
        result, llm = self._run(trip, "lunch", prefs("2026-10-13", "morning_tour"))
        assert CONTRACT_KEYS <= set(result)
        assert "trip_state" not in result
        assert result["move_refused"] is True
        assert result["move_refusal_code"] == "slot_type_mismatch"
        assert [n.model_dump() for n in result["updated_trip_state"].nodes] == [
            n.model_dump() for n in trip.nodes
        ]
        llm.assert_not_called()

    def test_zero_llm_and_no_venue_search(self):
        trip = base_trip()
        with patch.object(db_service, "hybrid_venue_search") as search:
            _, llm = self._run(trip, "temple", prefs("2026-10-13", "morning_tour"))
        llm.assert_not_called()
        search.assert_not_called()


class TestHttp:
    def _save(self, trip):
        db_service.save_trip(trip)
        return trip.trip_id

    def _count(self, uid):
        return db_service.get_or_create_user(uid).daily_reroute_count

    def _post(self, client, uid, trip_id, target, p):
        with patch.object(db_service, "get_venue_by_id", DB.get_venue_by_id):
            return client.post(
                "/api/v1/trip/event",
                headers=auth(uid),
                json={
                    "trip_id": trip_id,
                    "event_type": "move_activity",
                    "message": "Move",
                    "target_node_id": target,
                    "preferences": p,
                },
            )

    def test_http_success_consumes_one_reroute(self, client):
        uid = f"move-ok-{uuid.uuid4().hex[:6]}"
        trip_id = self._save(base_trip(user_id=uid))
        before = self._count(uid)
        r = self._post(client, uid, trip_id, "lunch", prefs("2026-10-12", "dinner"))
        assert r.status_code == 200, r.text
        nodes = r.json()["updated_nodes"]
        moved = next(n for n in nodes if n["node_id"] == "lunch")
        assert moved["slot_name"] == "dinner"
        assert moved["venue_id"] == "v-lunch"
        assert self._count(uid) == before + 1

    def test_http_locked_refuses_without_quota(self, client):
        uid = f"move-lock-{uuid.uuid4().hex[:6]}"
        hotel = node(
            "hotel",
            "Hotel",
            local(2026, 10, 12, 15),
            is_locked=True,
            node_kind="booking",
            booking_type="hotel",
        )
        trip = base_trip([hotel], user_id=uid)
        trip_id = self._save(trip)
        before = self._count(uid)
        r = self._post(client, uid, trip_id, "hotel", prefs("2026-10-13", "morning_tour"))
        assert r.status_code == 409
        assert r.json()["detail"]["error"] == "locked_move_refused"
        assert self._count(uid) == before
        stored = db_service.get_trip(trip_id)
        assert [n.model_dump() for n in stored.nodes] == [n.model_dump() for n in trip.nodes]

    def test_http_occupied_refuses_without_write_or_quota(self, client):
        uid = f"move-occ-{uuid.uuid4().hex[:6]}"
        din = node("dinner", "Dinner Place", local(2026, 10, 12, 18), slot="dinner")
        trip = base_trip([din], user_id=uid)
        trip_id = self._save(trip)
        before_version = db_service.get_trip(trip_id).version
        before = self._count(uid)
        r = self._post(client, uid, trip_id, "lunch", prefs("2026-10-12", "dinner"))
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert detail["error"] == "move_refused"
        assert detail["code"] == "slot_occupied"
        assert self._count(uid) == before
        stored = db_service.get_trip(trip_id)
        assert stored.version == before_version
        assert [n.model_dump() for n in stored.nodes] == [n.model_dump() for n in trip.nodes]

    def test_event_type_round_trip(self):
        assert EventType("move_activity") is EventType.MOVE_ACTIVITY
        assert EventType.MOVE_ACTIVITY.value == "move_activity"


def test_slot_floor_dinner_is_17_local():
    trip = base_trip()
    r = apply_move(trip, "lunch", prefs("2026-10-13", "dinner"), DB)
    assert r.ok, r.code
    moved = next(n for n in r.nodes if n.node_id == "lunch")
    assert moved.scheduled_start == local(2026, 10, 13, 17)
