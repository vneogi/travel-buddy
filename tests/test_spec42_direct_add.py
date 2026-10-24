"""SPEC-42 empty-day catalog Add -- backend tests.

R17 sabotage: drop previous-neighbour walking time from the shared evaluator
-> ``TestReachability::test_previous_walk_pushes_candidate_out_of_slot`` fails.
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
    AddCandidatesResponse,
    CreationContext,
    EventType,
    TripNode,
    TripSegment,
    TripState,
)
from services.database_service import DatabaseService, db_service
from services.direct_add_service import apply_direct_add, candidates_response, evaluate
from tests.conftest import auth

ICT = ZoneInfo("Asia/Bangkok")
VTE = "vientiane_laos"
LPQ = "luang_prabang_laos"
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
OPEN = {d: [["06:00", "23:00"]] for d in DAYS}
LUNCH_ONLY = {d: [["11:00", "14:00"]] for d in DAYS}
BASE = (17.9640, 102.6120)
FAR = (17.9990, 102.6420)  # ~4.5 km -> ~55 min walk

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


def v(vid, name, cat="restaurant", *, geo=VTE, at=BASE, dwell=60, hours=OPEN, tags=()):
    lat, lng = at if at else (None, None)
    return {
        "venue_id": vid,
        "name": name,
        "category": cat,
        "geo_region": geo,
        "lat": lat,
        "lng": lng,
        "typical_dwell_minutes": dwell,
        "opening_hours_structured": hours,
        "micro_location": "riverside",
        "vibe_tags": list(tags),
    }


def node(nid, name, start, *, slot=None, dur=60, at=BASE, geo=VTE, **kw):
    return TripNode(
        node_id=nid,
        venue_name=name,
        venue_id=f"v-{nid}",
        scheduled_start=start,
        duration_minutes=dur,
        slot_name=slot,
        lat=at[0] if at else None,
        lng=at[1] if at else None,
        geo_region=geo,
        **kw,
    )


def base_trip(extra=None, user_id="dadd-user", interests=()):
    nodes = [
        node("temple", "Wat Si Saket", local(2026, 10, 12, 9), slot="morning_tour"),
        node("lunch", "Khop Chai Deu", local(2026, 10, 12, 12), slot="lunch"),
        node("aft", "Night Market", local(2026, 10, 12, 14), slot="afternoon_evening_tour", dur=90),
    ] + list(extra or [])
    return TripState(
        trip_id=str(uuid.uuid4()),
        user_id=user_id,
        geo_region=VTE,
        nodes=nodes,
        creation_context=CreationContext(
            destination=VTE,
            start_date_local="2026-10-12",
            end_date_local="2026-10-14",
            interest_ids=list(interests),
        ),
    )


FOOD = [v(f"f{i}", f"Food {chr(71 - i)}") for i in range(7)]  # names G..A
ACT = [v("a1", "Temple One", "temple"), v("a2", "Museum Two", "museum")]


class FakeDb:
    def __init__(self, rows):
        self.rows = rows

    def list_venues_for_region(self, region):
        return [dict(r) for r in self.rows if r.get("geo_region") == region]


def ids(ev):
    return [c.venue_id for c in ev.candidates]


def dumps(nodes):
    return {n.node_id: n.model_dump() for n in nodes}


# ---------------------------------------------------------------------------
class TestListing:
    def test_empty_vientiane_date_returns_five_deterministic_food(self):
        trip = base_trip()
        db = FakeDb(FOOD + ACT)
        ev1 = evaluate(trip, "2026-10-13", "dinner", db.list_venues_for_region)
        ev2 = evaluate(trip, "2026-10-13", "dinner", db.list_venues_for_region)
        assert ev1.geo_region == VTE
        assert len(ev1.candidates) == 5
        assert ids(ev1) == ids(ev2)
        assert ids(ev1) == ["f6", "f5", "f4", "f3", "f2"]  # Food A..E by name
        assert all(c.row["category"] == "restaurant" for c in ev1.candidates)
        assert all(c.start_utc == local(2026, 10, 13, 17) for c in ev1.candidates)

    def test_interest_score_orders_first(self):
        trip = base_trip(interests=["food_markets"])
        rows = FOOD + [v("fz", "Zzz Authentic", tags=["authentic"])]
        ev = evaluate(trip, "2026-10-13", "dinner", FakeDb(rows).list_venues_for_region)
        assert ids(ev)[0] == "fz"

    def test_activity_slot_returns_only_activities(self):
        trip = base_trip()
        ev = evaluate(trip, "2026-10-13", "morning_tour", FakeDb(FOOD + ACT).list_venues_for_region)
        assert set(ids(ev)) == {"a1", "a2"}

    def test_corridor_date_uses_segment_region(self):
        trip = base_trip()
        trip.creation_context = None
        trip.segments = [
            TripSegment(geo_region=VTE, starts_on=date(2026, 10, 12), ends_on=date(2026, 10, 13)),
            TripSegment(geo_region=LPQ, starts_on=date(2026, 10, 14), ends_on=date(2026, 10, 15)),
        ]
        rows = FOOD + [v("lp1", "LP Noodles", geo=LPQ), v("dxb", "Dubai Grill", geo="dubai_uae")]
        ev = evaluate(trip, "2026-10-14", "lunch", FakeDb(rows).list_venues_for_region)
        assert ev.geo_region == LPQ
        assert ids(ev) == ["lp1"]

    @pytest.mark.parametrize(
        "segments",
        [
            # gap: Oct 14 in no segment
            [(VTE, (2026, 10, 12), (2026, 10, 13)), (LPQ, (2026, 10, 15), (2026, 10, 16))],
            # ambiguous overlap on Oct 14
            [(VTE, (2026, 10, 12), (2026, 10, 14)), (LPQ, (2026, 10, 14), (2026, 10, 16))],
        ],
    )
    def test_corridor_gap_or_ambiguous_date_refuses(self, segments):
        trip = base_trip()
        trip.creation_context = None
        trip.segments = [
            TripSegment(geo_region=g, starts_on=date(*a), ends_on=date(*b)) for g, a, b in segments
        ]
        ev = evaluate(trip, "2026-10-14", "lunch", FakeDb(FOOD).list_venues_for_region)
        assert ev.candidates == [] and ev.refusal_code == "invalid_date"

    def test_exclusions(self):
        trip = base_trip()
        rows = [
            v("ok", "Good Food"),
            v("rx", "Pharmacy", "pharmacy"),
            v("v-lunch", "Already On Trip"),
            v("nod", "No Dwell", dwell=None),
            v("tmp", "Temple For Dinner", "temple"),
            v("cls", "Lunch Only", hours=LUNCH_ONLY),
            v("blank", "   "),
            {**v("", "No Id")},
        ]
        ev = evaluate(trip, "2026-10-13", "dinner", FakeDb(rows).list_venues_for_region)
        assert ids(ev) == ["ok"]

    def test_unknown_dwell_never_defaults_to_90(self):
        trip = base_trip()
        ev = evaluate(
            trip, "2026-10-13", "dinner", FakeDb([v("n", "N", dwell=None)]).list_venues_for_region
        )
        assert ev.candidates == []
        assert ev.refusal_code == "no_catalog"


class TestReachability:
    def test_previous_walk_pushes_candidate_out_of_slot(self):
        """R17 target. Prev ends 13:30; ~55 min walk -> 14:25 is not lunch."""
        prev = node("long", "Long Tour", local(2026, 10, 13, 9), slot="morning_tour", dur=270)
        trip = base_trip([prev])
        ev = evaluate(
            trip,
            "2026-10-13",
            "lunch",
            FakeDb([v("far", "Far Food", at=FAR)]).list_venues_for_region,
        )
        assert ids(ev) == []
        assert ev.refusal_code == "hours"

    def test_previous_walk_near_candidate_fits(self):
        prev = node("long", "Long Tour", local(2026, 10, 13, 9), slot="morning_tour", dur=270)
        trip = base_trip([prev])
        ev = evaluate(
            trip, "2026-10-13", "lunch", FakeDb([v("near", "Near Food")]).list_venues_for_region
        )
        assert ids(ev) == ["near"]
        assert ev.candidates[0].start_utc == local(2026, 10, 13, 13, 35)

    def test_missing_coords_refuse_when_transfer_required(self):
        trip = base_trip()  # Oct 12 afternoon node precedes dinner
        rows = [v("nc", "No Coords", at=None), v("wc", "With Coords")]
        ev = evaluate(trip, "2026-10-12", "dinner", FakeDb(rows).list_venues_for_region)
        assert ids(ev) == ["wc"]

    def test_missing_coords_alone_refuses_reachability(self):
        trip = base_trip()
        ev = evaluate(
            trip,
            "2026-10-12",
            "dinner",
            FakeDb([v("nc", "No Coords", at=None)]).list_venues_for_region,
        )
        assert ev.refusal_code == "reachability"

    def test_next_lock_unreachable_excluded(self):
        tour = node(
            "tour",
            "Booked Tour",
            local(2026, 10, 13, 12, 30),
            at=FAR,
            is_locked=True,
            node_kind="booking",
            booking_type="tour",
        )
        trip = base_trip([tour])
        rows = [v("near", "Near Food", at=FAR), v("far", "Far Food", at=BASE)]
        ev = evaluate(trip, "2026-10-13", "lunch", FakeDb(rows).list_venues_for_region)
        assert ids(ev) == ["near"]

    def test_flight_cutoff_excludes(self):
        flight = node(
            "flt",
            "QV101",
            local(2026, 10, 13, 13),
            is_locked=True,
            node_kind="booking",
            booking_type="flight",
        )
        trip = base_trip([flight])
        ev = evaluate(trip, "2026-10-13", "lunch", FakeDb([v("x", "X")]).list_venues_for_region)
        assert ev.candidates == [] and ev.refusal_code == "reachability"

    def test_occupied_slot_refuses(self):
        trip = base_trip()
        ev = evaluate(trip, "2026-10-12", "lunch", FakeDb(FOOD).list_venues_for_region)
        assert ev.candidates == [] and ev.refusal_code == "occupied"


class TestApply:
    def test_every_listed_candidate_applies(self):
        trip = base_trip()
        db = FakeDb(FOOD)
        ev = evaluate(trip, "2026-10-13", "dinner", db.list_venues_for_region)
        assert ev.candidates
        for c in ev.candidates:
            r = apply_direct_add(
                trip,
                {
                    "mode": "direct_add",
                    "venue_id": c.venue_id,
                    "target_date": "2026-10-13",
                    "target_slot": "dinner",
                },
                db,
            )
            assert r.ok, (c.venue_id, r.code)
            assert r.added.scheduled_start == c.start_utc

    def test_success_adds_exactly_one_node(self):
        trip = base_trip()
        before = dumps(trip.nodes)
        r = apply_direct_add(
            trip,
            {
                "mode": "direct_add",
                "venue_id": "f0",
                "target_date": "2026-10-13",
                "target_slot": "dinner",
                "scheduled_start": "2026-10-13T05:00:00Z",
            },
            FakeDb(FOOD),
        )
        assert r.ok
        assert len(r.nodes) == len(trip.nodes) + 1
        new = r.added
        assert new.node_id not in before
        assert new.venue_id == "f0" and new.slot_name == "dinner"
        assert new.scheduled_start == local(2026, 10, 13, 17)  # client time ignored
        assert new.duration_minutes == 60
        assert new.geo_region == VTE
        assert not new.is_locked and new.node_kind == "activity"
        assert {k: d for k, d in dumps(r.nodes).items() if k != new.node_id} == before

    @pytest.mark.parametrize(
        "prefs,code",
        [
            (
                {
                    "mode": "ask",
                    "venue_id": "f0",
                    "target_date": "2026-10-13",
                    "target_slot": "dinner",
                },
                "invalid_mode",
            ),
            (
                {"mode": "direct_add", "target_date": "2026-10-13", "target_slot": "dinner"},
                "invalid_venue",
            ),
            (
                {
                    "mode": "direct_add",
                    "venue_id": "nope",
                    "target_date": "2026-10-13",
                    "target_slot": "dinner",
                },
                "invalid_venue",
            ),
            (
                {
                    "mode": "direct_add",
                    "venue_id": "f0",
                    "target_date": "13 Oct",
                    "target_slot": "dinner",
                },
                "invalid_date",
            ),
            (
                {
                    "mode": "direct_add",
                    "venue_id": "f0",
                    "target_date": "2026-10-20",
                    "target_slot": "dinner",
                },
                "invalid_date",
            ),
            (
                {
                    "mode": "direct_add",
                    "venue_id": "f0",
                    "target_date": "2026-10-13",
                    "target_slot": "brunch",
                },
                "invalid_slot",
            ),
            (
                {
                    "mode": "direct_add",
                    "venue_id": "a1",
                    "target_date": "2026-10-13",
                    "target_slot": "dinner",
                },
                "invalid_venue",
            ),
        ],
    )
    def test_invalid_payload_refuses(self, prefs, code):
        trip = base_trip()
        r = apply_direct_add(trip, prefs, FakeDb(FOOD + ACT))
        assert not r.ok and r.code == code
        assert dumps(r.nodes) == dumps(trip.nodes)


class TestSeams:
    def test_in_memory_and_supabase_seams_share_evaluator(self):
        from services.supabase_service import SupabaseService

        rows = FOOD + ACT
        mem = DatabaseService()
        mem._venues = [dict(r) for r in rows]

        class _Q:
            def __init__(self, data):
                self.data = data

            def table(self, _):
                return self

            def select(self, _):
                return self

            def eq(self, _k, val):
                return _Q([r for r in self.data if r["geo_region"] == val])

            def execute(self):
                return SimpleNamespace(data=[dict(r) for r in self.data])

        sb = SupabaseService.__new__(SupabaseService)
        trip = base_trip()
        a = evaluate(trip, "2026-10-13", "dinner", mem.list_venues_for_region)
        with patch.object(SupabaseService, "client", new=_Q(rows)):
            b = evaluate(trip, "2026-10-13", "dinner", sb.list_venues_for_region)
        assert ids(a) == ids(b) and len(ids(a)) == 5

    def test_response_matches_closed_dto(self):
        payload = candidates_response(base_trip(), "2026-10-13", "dinner", FakeDb(FOOD))
        dto = AddCandidatesResponse(**payload)
        assert dto.candidates[0].planned_start == "2026-10-13T17:00:00+07:00"
        assert dto.refusal_code is None


class TestProcessEvent:
    def _run(self, trip, prefs):
        with (
            patch.object(db_service, "list_venues_for_region", FakeDb(FOOD).list_venues_for_region),
            patch("services.llm_service.llm_service.complete", new_callable=AsyncMock) as llm,
            patch.object(db_service, "hybrid_venue_search") as search,
        ):
            res = asyncio.run(
                state_machine.process_event(
                    trip_state=trip,
                    event_type=EventType.ADD_ACTIVITY.value,
                    message="Add",
                    preferences=prefs,
                )
            )
        llm.assert_not_called()
        search.assert_not_called()
        return res

    def test_contract_on_success(self):
        res = self._run(
            base_trip(),
            {
                "mode": "direct_add",
                "venue_id": "f0",
                "target_date": "2026-10-13",
                "target_slot": "dinner",
            },
        )
        assert CONTRACT_KEYS <= set(res) and "trip_state" not in res
        assert "direct_add_refused" not in res
        assert len(res["updated_trip_state"].nodes) == 4

    def test_contract_on_refusal(self):
        trip = base_trip()
        res = self._run(
            trip,
            {
                "mode": "direct_add",
                "venue_id": "f0",
                "target_date": "2026-10-12",
                "target_slot": "lunch",
            },
        )
        assert CONTRACT_KEYS <= set(res) and "trip_state" not in res
        assert res["direct_add_refused"] is True
        assert res["direct_add_refusal_code"] == "occupied"
        assert dumps(res["updated_trip_state"].nodes) == dumps(trip.nodes)

    def test_bare_add_still_refuses(self):
        trip = base_trip()
        res = self._run(trip, {})
        assert res["ask_response"]["tier"] == "refuse"
        assert dumps(res["updated_trip_state"].nodes) == dumps(trip.nodes)

    def test_ask_to_add_still_dispatched(self):
        trip = base_trip()
        with patch.object(
            type(state_machine), "_handle_typed_add", new_callable=AsyncMock
        ) as typed:
            typed.return_value = {"updated_trip_state": trip}
            asyncio.run(
                state_machine.process_event(
                    trip_state=trip,
                    event_type=EventType.ADD_ACTIVITY.value,
                    message="Add",
                    preferences={"mode": "ask_to_add", "venue_id": "f0"},
                )
            )
        typed.assert_awaited_once()


class TestHttp:
    def _setup(self, extra=None):
        uid = f"dadd-{uuid.uuid4().hex[:8]}"
        trip = base_trip(extra, user_id=uid)
        db_service.save_trip(trip)
        return uid, trip

    def _count(self, uid):
        return db_service.get_or_create_user(uid).daily_reroute_count

    def _patches(self):
        return (
            patch.object(db_service, "list_venues_for_region", FakeDb(FOOD).list_venues_for_region),
            patch("services.llm_service.llm_service.complete", new_callable=AsyncMock),
            patch.object(db_service, "hybrid_venue_search"),
        )

    def _get(self, client, uid, trip_id, d, slot):
        return client.get(
            f"/api/v1/trip/{trip_id}/add_candidates",
            headers=auth(uid),
            params={"target_date": d, "target_slot": slot},
        )

    def _post(self, client, uid, trip_id, prefs):
        return client.post(
            "/api/v1/trip/event",
            headers=auth(uid),
            json={
                "trip_id": trip_id,
                "event_type": "add_activity",
                "message": "Add",
                "preferences": prefs,
            },
        )

    def test_candidates_endpoint_read_only(self, client):
        uid, trip = self._setup()
        v0, c0 = db_service.get_trip(trip.trip_id).version, self._count(uid)
        p1, p2, p3 = self._patches()
        with p1, p2 as llm, p3 as search:
            r = self._get(client, uid, trip.trip_id, "2026-10-13", "dinner")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["geo_region"] == VTE and len(body["candidates"]) == 5
        assert body["refusal_code"] is None
        assert db_service.get_trip(trip.trip_id).version == v0
        assert self._count(uid) == c0
        llm.assert_not_called()
        search.assert_not_called()

    def test_no_fit_typed_refusal_no_write(self, client):
        uid, trip = self._setup()
        v0, c0 = db_service.get_trip(trip.trip_id).version, self._count(uid)
        p1, p2, p3 = self._patches()
        with p1, p2, p3:
            r = self._get(client, uid, trip.trip_id, "2026-10-12", "lunch")
        body = r.json()
        assert r.status_code == 200
        assert body["candidates"] == [] and body["refusal_code"] == "occupied"
        assert body["refusal_copy"]
        assert db_service.get_trip(trip.trip_id).version == v0
        assert self._count(uid) == c0

    def test_invalid_slot_and_date_on_endpoint(self, client):
        uid, trip = self._setup()
        p1, p2, p3 = self._patches()
        with p1, p2, p3:
            bad_slot = self._get(client, uid, trip.trip_id, "2026-10-13", "brunch")
            bad_date = self._get(client, uid, trip.trip_id, "2026-11-30", "dinner")
        assert bad_slot.status_code == 422
        assert bad_date.json()["refusal_code"] == "invalid_date"

    def test_non_owner_404(self, client):
        uid, trip = self._setup()
        r = self._get(client, "someone-else", trip.trip_id, "2026-10-13", "dinner")
        assert r.status_code == 404

    def test_confirm_success_one_node_one_reroute(self, client):
        uid, trip = self._setup()
        v0, c0 = db_service.get_trip(trip.trip_id).version, self._count(uid)
        p1, p2, p3 = self._patches()
        with p1, p2 as llm, p3 as search:
            listed = self._get(client, uid, trip.trip_id, "2026-10-13", "dinner").json()
            vid = listed["candidates"][0]["venue_id"]
            r = self._post(
                client,
                uid,
                trip.trip_id,
                {
                    "mode": "direct_add",
                    "venue_id": vid,
                    "target_date": "2026-10-13",
                    "target_slot": "dinner",
                },
            )
        assert r.status_code == 200, r.text
        nodes = r.json()["updated_nodes"]
        old = {n.node_id: n.model_dump(mode="json") for n in trip.nodes}
        new = [n for n in nodes if n["node_id"] not in old]
        assert len(new) == 1 and new[0]["venue_id"] == vid and new[0]["slot_name"] == "dinner"
        for n in nodes:
            if n["node_id"] in old:
                assert n == old[n["node_id"]]
        assert self._count(uid) == c0 + 1
        assert db_service.get_trip(trip.trip_id).version == v0 + 1
        llm.assert_not_called()
        search.assert_not_called()

    def test_stale_occupied_at_confirm_422_no_write(self, client):
        uid, trip = self._setup()
        p1, p2, p3 = self._patches()
        with p1, p2, p3:
            listed = self._get(client, uid, trip.trip_id, "2026-10-13", "dinner").json()
            vid = listed["candidates"][0]["venue_id"]
            stored = db_service.get_trip(trip.trip_id)
            stored.nodes.append(node("late", "Late Dinner", local(2026, 10, 13, 18), slot="dinner"))
            db_service.save_trip(stored)
            v0, c0 = db_service.get_trip(trip.trip_id).version, self._count(uid)
            before = dumps(db_service.get_trip(trip.trip_id).nodes)
            r = self._post(
                client,
                uid,
                trip.trip_id,
                {
                    "mode": "direct_add",
                    "venue_id": vid,
                    "target_date": "2026-10-13",
                    "target_slot": "dinner",
                },
            )
        assert r.status_code == 422
        assert r.json()["detail"]["error"] == "direct_add_refused"
        assert r.json()["detail"]["code"] == "occupied"
        after = db_service.get_trip(trip.trip_id)
        assert after.version == v0 and self._count(uid) == c0
        assert dumps(after.nodes) == before
