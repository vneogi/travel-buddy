"""SPEC-42 trip-private uncatalogued Add -- backend tests.

R17 sabotage: let confirm upsert the posted name into the venue list ->
``TestCatalogIsolation::test_catalog_unchanged_after_success`` fails.
"""

import asyncio
import copy
import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from agents.state_machine import state_machine
from models.schemas import EventType, TripNode, TripSegment, TripState
from services.database_service import db_service
from services.uncatalogued_add_service import apply_uncatalogued_add
from tests.conftest import auth
from tests.test_spec42_direct_add import (
    BASE,
    CONTRACT_KEYS,
    FAR,
    FOOD,
    LPQ,
    VTE,
    FakeDb,
    base_trip,
    dumps,
    local,
    node,
    v,
)

CATALOG = FOOD + [v("a1", "Temple One", "temple")]


def prefs(**over):
    p = {
        "mode": "uncatalogued_add",
        "name": "Papao viewpoint",
        "target_date": "2026-10-13",
        "target_slot": "afternoon_evening_tour",
        "typical_dwell_minutes": 60,
        "micro_location": "east bank",
        "lat": BASE[0],
        "lng": BASE[1],
    }
    p.update(over)
    return {k: val for k, val in p.items() if val is not ...}


class TestApply:
    def test_success_inserts_one_trip_private_node(self):
        trip = base_trip()
        before = dumps(trip.nodes)
        r = apply_uncatalogued_add(
            trip, prefs(scheduled_start="2026-10-13T01:00:00Z", venue_id="x"), FakeDb(CATALOG)
        )
        assert r.ok, r.code
        assert len(r.nodes) == len(trip.nodes) + 1
        n = r.added
        assert n.node_id not in before
        assert n.venue_id is None
        assert n.place_source == "trip_private"
        assert n.venue_name == "Papao viewpoint"
        assert n.duration_minutes == 60
        assert n.slot_name == "afternoon_evening_tour"
        assert n.geo_region == VTE
        assert n.scheduled_start == local(2026, 10, 13, 14)  # server floor, client ignored
        assert n.opening_hours is None and n.opening_hours_structured is None
        assert (n.lat, n.lng) == BASE and n.micro_location == "east bank"
        assert not n.is_locked and n.node_kind == "activity"
        assert {k: d for k, d in dumps(r.nodes).items() if k != n.node_id} == before

    def test_true_empty_day_may_omit_coords(self):
        r = apply_uncatalogued_add(
            base_trip(), prefs(lat=..., lng=..., micro_location=...), FakeDb(CATALOG)
        )
        assert r.ok, r.code
        assert r.added.lat is None and r.added.lng is None and r.added.micro_location is None

    def test_corridor_date_uses_segment_region(self):
        trip = base_trip()
        trip.creation_context = None
        trip.segments = [
            TripSegment(geo_region=VTE, starts_on=date(2026, 10, 12), ends_on=date(2026, 10, 13)),
            TripSegment(geo_region=LPQ, starts_on=date(2026, 10, 14), ends_on=date(2026, 10, 15)),
        ]
        r = apply_uncatalogued_add(trip, prefs(target_date="2026-10-14"), FakeDb(CATALOG))
        assert r.ok, r.code
        assert r.added.geo_region == LPQ

    def test_matching_catalog_name_refuses(self):
        trip = base_trip()
        r = apply_uncatalogued_add(trip, prefs(name="  food   a "), FakeDb(CATALOG))
        assert not r.ok and r.code == "catalog_match"
        assert dumps(r.nodes) == dumps(trip.nodes)

    def test_catalog_name_other_region_is_allowed(self):
        rows = [v("lp", "Papao Viewpoint", "viewpoint", geo=LPQ)]
        r = apply_uncatalogued_add(base_trip(), prefs(), FakeDb(rows))
        assert r.ok, r.code

    def test_name_equal_to_catalog_venue_id_refuses(self):
        r = apply_uncatalogued_add(base_trip(), prefs(name="f3"), FakeDb(CATALOG))
        assert not r.ok and r.code == "invalid_name"

    def test_same_name_same_date_duplicate(self):
        trip = base_trip()
        r = apply_uncatalogued_add(
            trip,
            prefs(name="wat si  saket", target_date="2026-10-12", target_slot="dinner"),
            FakeDb(CATALOG),
        )
        assert not r.ok and r.code == "duplicate"

    def test_previous_neighbour_missing_coords_refuses_reachability(self):
        trip = base_trip()  # Oct 12 has an afternoon stop before dinner
        r = apply_uncatalogued_add(
            trip,
            prefs(target_date="2026-10-12", target_slot="dinner", lat=..., lng=...),
            FakeDb(CATALOG),
        )
        assert not r.ok and r.code == "reachability"

    def test_previous_walk_respected(self):
        trip = base_trip()
        r = apply_uncatalogued_add(
            trip,
            prefs(target_date="2026-10-12", target_slot="dinner", lat=FAR[0], lng=FAR[1]),
            FakeDb(CATALOG),
        )
        assert r.ok, r.code
        # aft ends 15:30; dinner floor 17:00 dominates the ~55 min walk
        assert r.added.scheduled_start == local(2026, 10, 12, 17)

    def test_next_lock_unreachable_refuses(self):
        tour = node(
            "tour",
            "Booked Tour",
            local(2026, 10, 13, 15),
            at=FAR,
            is_locked=True,
            node_kind="booking",
            booking_type="tour",
        )
        r = apply_uncatalogued_add(base_trip([tour]), prefs(), FakeDb(CATALOG))
        assert not r.ok and r.code == "reachability"

    @pytest.mark.parametrize(
        "over,code",
        [
            ({"mode": "direct_add"}, "invalid_mode"),
            ({"mode": "Uncatalogued_add"}, "invalid_mode"),
            ({"name": ...}, "invalid_name"),
            ({"name": " x "}, "invalid_name"),
            ({"name": "y" * 81}, "invalid_name"),
            ({"name": 42}, "invalid_name"),
            ({"typical_dwell_minutes": ...}, "invalid_dwell"),
            ({"typical_dwell_minutes": 14}, "invalid_dwell"),
            ({"typical_dwell_minutes": 241}, "invalid_dwell"),
            ({"typical_dwell_minutes": 60.5}, "invalid_dwell"),
            ({"typical_dwell_minutes": float("nan")}, "invalid_dwell"),
            ({"typical_dwell_minutes": True}, "invalid_dwell"),
            ({"typical_dwell_minutes": "60"}, "invalid_dwell"),
            ({"lat": ...}, "invalid_coords"),
            ({"lng": float("inf")}, "invalid_coords"),
            ({"target_slot": "brunch"}, "invalid_slot"),
            ({"target_slot": ...}, "invalid_slot"),
            ({"target_date": "13/10/2026"}, "invalid_date"),
            ({"target_date": "2026-10-20"}, "invalid_date"),
            ({"target_date": "2026-10-12", "target_slot": "lunch"}, "occupied"),
        ],
    )
    def test_invalid_or_infeasible_refuses_without_change(self, over, code):
        trip = base_trip()
        r = apply_uncatalogued_add(trip, prefs(**over), FakeDb(CATALOG))
        assert not r.ok and r.code == code
        assert dumps(r.nodes) == dumps(trip.nodes)

    def test_dwell_float_integer_accepted(self):
        r = apply_uncatalogued_add(base_trip(), prefs(typical_dwell_minutes=45.0), FakeDb(CATALOG))
        assert r.ok and r.added.duration_minutes == 45


class TestSchema:
    def test_old_node_without_field_loads_as_catalog(self):
        raw = node("x", "X", local(2026, 10, 12, 9)).model_dump(mode="json")
        raw.pop("place_source")
        assert TripNode(**raw).place_source == "catalog"

    def test_round_trip_trip_private(self):
        n = TripNode(
            venue_name="P", scheduled_start=local(2026, 10, 13, 14), place_source="trip_private"
        )
        assert TripNode(**n.model_dump(mode="json")).place_source == "trip_private"


class TestProcessEvent:
    def _run(self, trip, p):
        with (
            patch.object(
                db_service, "list_venues_for_region", FakeDb(CATALOG).list_venues_for_region
            ),
            patch("services.llm_service.llm_service.complete", new_callable=AsyncMock) as llm,
            patch.object(db_service, "hybrid_venue_search") as search,
            patch.object(db_service, "add_venue") as add_venue,
        ):
            res = asyncio.run(
                state_machine.process_event(
                    trip_state=trip,
                    event_type=EventType.ADD_ACTIVITY.value,
                    message="Add",
                    preferences=p,
                )
            )
        llm.assert_not_called()
        search.assert_not_called()
        add_venue.assert_not_called()
        return res

    def test_contract_success(self):
        res = self._run(base_trip(), prefs())
        assert CONTRACT_KEYS <= set(res) and "trip_state" not in res
        assert "uncatalogued_add_refused" not in res
        assert len(res["updated_trip_state"].nodes) == 4

    def test_contract_refusal(self):
        trip = base_trip()
        res = self._run(trip, prefs(typical_dwell_minutes=...))
        assert CONTRACT_KEYS <= set(res) and "trip_state" not in res
        assert res["uncatalogued_add_refused"] is True
        assert res["uncatalogued_add_refusal_code"] == "invalid_dwell"
        assert dumps(res["updated_trip_state"].nodes) == dumps(trip.nodes)

    def test_direct_add_still_dispatches(self):
        res = self._run(
            base_trip(),
            {
                "mode": "direct_add",
                "venue_id": "f0",
                "target_date": "2026-10-13",
                "target_slot": "dinner",
            },
        )
        assert "direct_add_refused" not in res
        added = [n for n in res["updated_trip_state"].nodes if n.venue_id == "f0"]
        assert len(added) == 1 and added[0].place_source == "catalog"

    def test_ask_to_add_still_dispatched(self):
        trip = base_trip()
        with patch.object(type(state_machine), "_handle_typed_add", new_callable=AsyncMock) as t:
            t.return_value = {"updated_trip_state": trip}
            asyncio.run(
                state_machine.process_event(
                    trip_state=trip,
                    event_type=EventType.ADD_ACTIVITY.value,
                    message="Add",
                    preferences={"mode": "ask_to_add", "venue_id": "f0"},
                )
            )
        t.assert_awaited_once()

    def test_bare_add_still_refuses(self):
        trip = base_trip()
        res = self._run(trip, {"name": "Papao viewpoint"})
        assert res["ask_response"]["tier"] == "refuse"
        assert dumps(res["updated_trip_state"].nodes) == dumps(trip.nodes)


class TestCatalogIsolation:
    """In-memory catalog: real venue list, real trip write."""

    def _seed(self):
        uid = f"uca-{uuid.uuid4().hex[:8]}"
        trip = base_trip(user_id=uid)
        db_service.save_trip(trip)
        return uid, trip

    def _post(self, client, uid, trip_id, p):
        return client.post(
            "/api/v1/trip/event",
            headers=auth(uid),
            json={
                "trip_id": trip_id,
                "event_type": "add_activity",
                "message": "Add",
                "preferences": p,
            },
        )

    def _count(self, uid):
        return db_service.get_or_create_user(uid).daily_reroute_count

    def test_catalog_unchanged_after_success(self, client):
        """R17 target: confirm must never write the shared venue list."""
        uid, trip = self._seed()
        name = f"Papao viewpoint {uuid.uuid4().hex[:6]}"
        venues_before = copy.deepcopy(db_service._venues)
        region_before = db_service.list_venues_for_region(VTE)
        with (
            patch("services.llm_service.llm_service.complete", new_callable=AsyncMock) as llm,
            patch.object(db_service, "hybrid_venue_search") as search,
        ):
            r = self._post(client, uid, trip.trip_id, prefs(name=name))
        assert r.status_code == 200, r.text
        llm.assert_not_called()
        search.assert_not_called()
        assert db_service._venues == venues_before
        region_after = db_service.list_venues_for_region(VTE)
        assert region_after == region_before
        assert all(name.casefold() != (row.get("name") or "").casefold() for row in region_after)
        assert db_service.resolve_venue_by_name(name) is None

        # Another trip in the same region does not see it as a catalog venue.
        from services.direct_add_service import evaluate

        other = base_trip(user_id=f"other-{uuid.uuid4().hex[:6]}")
        ev = evaluate(
            other, "2026-10-13", "afternoon_evening_tour", db_service.list_venues_for_region
        )
        assert all(c.row.get("name") != name for c in ev.candidates)

    def test_http_success_one_node_one_reroute(self, client):
        uid, trip = self._seed()
        v0, c0 = db_service.get_trip(trip.trip_id).version, self._count(uid)
        r = self._post(client, uid, trip.trip_id, prefs(name="Hidden noodle stall"))
        assert r.status_code == 200, r.text
        old = {n.node_id: n.model_dump(mode="json") for n in trip.nodes}
        nodes = r.json()["updated_nodes"]
        new = [n for n in nodes if n["node_id"] not in old]
        assert len(new) == 1
        assert new[0]["venue_id"] is None and new[0]["place_source"] == "trip_private"
        for n in nodes:
            if n["node_id"] in old:
                assert n == old[n["node_id"]]
        stored = db_service.get_trip(trip.trip_id)
        assert stored.version == v0 + 1 and self._count(uid) == c0 + 1
        assert [n for n in stored.nodes if n.place_source == "trip_private"][0].venue_name == (
            "Hidden noodle stall"
        )

    @pytest.mark.parametrize(
        "over,code",
        [
            ({"target_date": "2026-10-12", "target_slot": "lunch"}, "occupied"),
            ({"typical_dwell_minutes": ...}, "invalid_dwell"),
            ({"name": "a"}, "invalid_name"),
            ({"target_slot": "brunch"}, "invalid_slot"),
        ],
    )
    def test_http_refusal_422_no_write(self, client, over, code):
        uid, trip = self._seed()
        v0, c0 = db_service.get_trip(trip.trip_id).version, self._count(uid)
        before = dumps(db_service.get_trip(trip.trip_id).nodes)
        r = self._post(client, uid, trip.trip_id, prefs(**over))
        assert r.status_code == 422, r.text
        assert r.json()["detail"]["error"] == "uncatalogued_add_refused"
        assert r.json()["detail"]["code"] == code
        assert r.json()["detail"]["message"]
        after = db_service.get_trip(trip.trip_id)
        assert after.version == v0 and self._count(uid) == c0
        assert dumps(after.nodes) == before

    def test_catalog_name_http_refusal(self, client):
        uid, trip = self._seed()
        rows = db_service.list_venues_for_region(VTE)
        if not rows:
            pytest.skip("in-memory catalog has no Vientiane rows")
        v0 = db_service.get_trip(trip.trip_id).version
        r = self._post(client, uid, trip.trip_id, prefs(name=rows[0]["name"].upper()))
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "catalog_match"
        assert db_service.get_trip(trip.trip_id).version == v0
