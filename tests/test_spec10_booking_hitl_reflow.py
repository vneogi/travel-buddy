"""SPEC-10 slice 1: create-then-book HITL reflow, driven through the API.

Every add, edit and confirm goes through POST /api/v1/trip/event. Trips use
the in-memory create path, which packs each day with the four named
flexible slots. Zanzibar is UTC+3; booking times are sent as naive
destination-local wall time (SPEC-10 convention).
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from tests.conftest import auth

GEO = "zanzibar_tanzania"
SLOTS = ("morning_tour", "lunch", "afternoon_evening_tour", "dinner")


def _create(client, user, start="2026-12-25", end="2026-12-27"):
    r = client.post(
        "/api/v1/trip/create",
        headers=auth(user),
        json={"geo_region": GEO, "start_date": start, "end_date": end},
    )
    assert r.status_code == 200, r.text
    return r.json()["trip_id"]


def _event(client, user, trip_id, event_type, preferences=None, target=None):
    body = {"trip_id": trip_id, "event_type": event_type, "message": event_type}
    if preferences is not None:
        body["preferences"] = preferences
    if target is not None:
        body["target_node_id"] = target
    return client.post("/api/v1/trip/event", headers=auth(user), json=body)


def _add(client, user, trip_id, booking_type, start_local, minutes, **extra):
    prefs = {
        "venue_name": f"{booking_type} booking",
        "booking_type": booking_type,
        "scheduled_start": start_local,
        "duration_minutes": minutes,
    }
    prefs.update(extra)
    r = _event(client, user, trip_id, "add_booking", preferences=prefs)
    assert r.status_code == 200, r.text
    return r


def _confirm(client, user, trip_id, booking_id, intent):
    return _event(
        client,
        user,
        trip_id,
        "confirm_booking_reflow",
        preferences={"intent": intent},
        target=booking_id,
    )


def _local_date(node):
    utc = datetime.fromisoformat(node["scheduled_start"].replace("Z", "+00:00"))
    return (utc + timedelta(hours=3)).date().isoformat()


def _flexible(nodes, local_date):
    return {
        n["slot_name"]: n
        for n in nodes
        if n["node_kind"] != "booking" and n.get("slot_name") and _local_date(n) == local_date
    }


def _stored_nodes(client, user, trip_id):
    r = client.get(f"/api/v1/trip/{trip_id}", headers=auth(user))
    assert r.status_code == 200, r.text
    return r.json()["nodes"]


def _booking(nodes, booking_type):
    return next(
        n for n in nodes if n["node_kind"] == "booking" and n["booking_type"] == booking_type
    )


def _status_map(nodes):
    return {n["node_id"]: n["status"] for n in nodes}


def _evening_flight(client, user, local_date="2026-12-25"):
    trip_id = _create(client, user)
    r = _add(client, user, trip_id, "flight", f"{local_date}T18:00:00", 120)
    nodes = r.json()["updated_nodes"]
    return trip_id, _booking(nodes, "flight"), _flexible(nodes, local_date), r.json()


class TestProposal:
    def test_add_evening_flight_proposes_without_skipping(self, client):
        trip_id, booking, day, body = _evening_flight(client, "hitl-1")
        assert set(day) == set(SLOTS)
        assert all(n["status"] == "pending" for n in day.values())
        stored = _stored_nodes(client, "hitl-1", trip_id)
        assert booking["node_id"] in {n["node_id"] for n in stored}
        proposal = body["booking_reflow"]
        assert proposal["booking_node_id"] == booking["node_id"]
        assert proposal["default_intent"] == "conservative"
        assert "restore_evening" in proposal["intents"] and "keep_open" in proposal["intents"]
        assert proposal["intents"][0] == "conservative"
        assert len(proposal["days"]) == 1
        only = proposal["days"][0]
        assert only["local_date"] == "2026-12-25"
        assert only["conservative_slots"] == ["dinner"]
        expected = {day[s]["node_id"] for s in ("morning_tour", "lunch", "afternoon_evening_tour")}
        assert set(only["extra_node_ids"]) == expected
        assert set(proposal) == {"booking_node_id", "intents", "default_intent", "days"}

    def test_reload_without_confirm_keeps_flexible_pending(self, client):
        trip_id, _booking_node, day, _body = _evening_flight(client, "hitl-2")
        stored = _flexible(_stored_nodes(client, "hitl-2", trip_id), "2026-12-25")
        assert {s: n["status"] for s, n in stored.items()} == {s: "pending" for s in SLOTS}
        assert {n["node_id"] for n in stored.values()} == {n["node_id"] for n in day.values()}

    def test_edit_noon_flight_to_evening_proposes(self, client):
        trip_id = _create(client, "hitl-8")
        added = _add(client, "hitl-8", trip_id, "flight", "2026-12-25T12:00:00", 120)
        assert added.json().get("booking_reflow") is None
        booking = _booking(added.json()["updated_nodes"], "flight")
        r = _event(
            client,
            "hitl-8",
            trip_id,
            "edit_booking",
            preferences={"scheduled_start": "2026-12-25T18:00:00"},
            target=booking["node_id"],
        )
        assert r.status_code == 200, r.text
        assert r.json()["booking_reflow"]["days"][0]["conservative_slots"] == ["dinner"]
        day = _flexible(_stored_nodes(client, "hitl-8", trip_id), "2026-12-25")
        assert all(n["status"] == "pending" for n in day.values())

    def test_booking_that_squeezes_nothing_has_no_proposal(self, client):
        trip_id = _create(client, "hitl-9")
        r = _add(client, "hitl-9", trip_id, "flight", "2026-12-25T12:00:00", 120)
        assert r.json().get("booking_reflow") is None
        day = _flexible(r.json()["updated_nodes"], "2026-12-25")
        assert all(n["status"] == "pending" for n in day.values())

    def test_locked_and_skipped_nodes_never_in_extras(self, client):
        user = "hitl-10"
        trip_id = _create(client, user)
        nodes = _stored_nodes(client, user, trip_id)
        lunch = _flexible(nodes, "2026-12-25")["lunch"]
        r = _event(client, user, trip_id, "cancel_activity", target=lunch["node_id"])
        assert r.status_code == 200, r.text
        tour = _add(client, user, trip_id, "tour", "2026-12-25T10:00:00", 60)
        tour_id = _booking(tour.json()["updated_nodes"], "tour")["node_id"]
        r = _add(client, user, trip_id, "flight", "2026-12-25T18:00:00", 120)
        nodes = r.json()["updated_nodes"]
        flight_id = _booking(nodes, "flight")["node_id"]
        day = _flexible(nodes, "2026-12-25")
        extra = set(r.json()["booking_reflow"]["days"][0]["extra_node_ids"])
        assert extra == {day["morning_tour"]["node_id"], day["afternoon_evening_tour"]["node_id"]}
        assert lunch["node_id"] not in extra
        assert tour_id not in extra and flight_id not in extra

    def test_hotel_checkin_and_checkout_days(self, client):
        # Check-in 25 Dec 15:00, checkout 26 Dec 11:00 (owner default).
        trip_id = _create(client, "hitl-11")
        r = _add(client, "hitl-11", trip_id, "hotel", "2026-12-25T15:00:00", 20 * 60)
        nodes = r.json()["updated_nodes"]
        proposal = r.json()["booking_reflow"]
        assert [d["local_date"] for d in proposal["days"]] == ["2026-12-25", "2026-12-26"]
        checkin, checkout = proposal["days"]
        assert checkin["conservative_slots"] == ["afternoon_evening_tour", "dinner"]
        d25 = _flexible(nodes, "2026-12-25")
        assert set(checkin["extra_node_ids"]) == {
            d25["morning_tour"]["node_id"],
            d25["lunch"]["node_id"],
        }
        assert checkout["conservative_slots"] == ["morning_tour"]
        d26 = _flexible(nodes, "2026-12-26")
        assert set(checkout["extra_node_ids"]) == {
            d26[s]["node_id"] for s in ("lunch", "afternoon_evening_tour", "dinner")
        }
        assert proposal["intents"] == [
            "conservative",
            "restore_evening",
            "restore_morning",
            "keep_open",
        ]

    def test_three_night_hotel_keep_open_leaves_middle_nights(self, client):
        user = "hitl-11b"
        trip_id = _create(client, user, end="2026-12-28")
        r = _add(client, user, trip_id, "hotel", "2026-12-25T15:00:00", 3 * 24 * 60 - 4 * 60)
        hotel_id = _booking(r.json()["updated_nodes"], "hotel")["node_id"]
        dates = [d["local_date"] for d in r.json()["booking_reflow"]["days"]]
        assert dates == ["2026-12-25", "2026-12-28"]
        c = _confirm(client, user, trip_id, hotel_id, "keep_open")
        assert c.status_code == 200, c.text
        nodes = _stored_nodes(client, user, trip_id)
        for middle in ("2026-12-26", "2026-12-27"):
            day = _flexible(nodes, middle)
            assert set(day) == set(SLOTS)
            assert all(n["status"] == "pending" for n in day.values()), middle
        # keep_open skips every flexible stop on the listed check-in day.
        assert all(n["status"] == "skipped" for n in _flexible(nodes, "2026-12-25").values())

    def test_chained_stay_omits_checkout_entry(self, client):
        user = "hitl-11c"
        trip_id = _create(client, user, end="2026-12-29")
        nungwi = _add(
            client,
            user,
            trip_id,
            "hotel",
            "2026-12-29T12:00:00",
            23 * 60,
            geo_region="nungwi_tanzania",
        )
        assert nungwi.json().get("booking_reflow") is None
        stone = _add(client, user, trip_id, "hotel", "2026-12-27T15:00:00", 44 * 60)
        dates = [d["local_date"] for d in stone.json()["booking_reflow"]["days"]]
        assert "2026-12-29" not in dates
        assert dates == ["2026-12-27"]

    def test_noon_checkin_lists_only_checkout_day(self, client):
        trip_id = _create(client, "hitl-11d")
        r = _add(client, "hitl-11d", trip_id, "hotel", "2026-12-25T12:00:00", 23 * 60)
        proposal = r.json()["booking_reflow"]
        assert [d["local_date"] for d in proposal["days"]] == ["2026-12-26"]
        assert proposal["days"][0]["conservative_slots"] == ["morning_tour"]
        assert proposal["intents"] == ["conservative", "restore_morning", "keep_open"]


class TestConfirm:
    def test_confirm_conservative_skips_extras_in_place(self, client):
        trip_id, booking, day, _body = _evening_flight(client, "hitl-3")
        before = _stored_nodes(client, "hitl-3", trip_id)
        r = _confirm(client, "hitl-3", trip_id, booking["node_id"], "conservative")
        assert r.status_code == 200, r.text
        assert r.json().get("booking_reflow") is None
        after = _flexible(_stored_nodes(client, "hitl-3", trip_id), "2026-12-25")
        assert after["dinner"]["status"] == "pending"
        for slot in ("morning_tour", "lunch", "afternoon_evening_tour"):
            assert after[slot]["status"] == "skipped", slot
            assert after[slot]["node_id"] == day[slot]["node_id"]
        assert len(_stored_nodes(client, "hitl-3", trip_id)) == len(before)

    def test_confirm_restore_evening(self, client):
        trip_id, booking, _day, _body = _evening_flight(client, "hitl-4")
        r = _confirm(client, "hitl-4", trip_id, booking["node_id"], "restore_evening")
        assert r.status_code == 200, r.text
        after = _flexible(_stored_nodes(client, "hitl-4", trip_id), "2026-12-25")
        assert {s: after[s]["status"] for s in SLOTS} == {
            "morning_tour": "skipped",
            "lunch": "skipped",
            "afternoon_evening_tour": "pending",
            "dinner": "pending",
        }

    def test_confirm_keep_open_skips_all_flexible(self, client):
        trip_id, booking, _day, _body = _evening_flight(client, "hitl-5")
        r = _confirm(client, "hitl-5", trip_id, booking["node_id"], "keep_open")
        assert r.status_code == 200, r.text
        nodes = _stored_nodes(client, "hitl-5", trip_id)
        assert all(n["status"] == "skipped" for n in _flexible(nodes, "2026-12-25").values())
        assert _booking(nodes, "flight")["status"] == "pending"

    def test_confirm_missing_or_non_booking_is_409(self, client):
        trip_id, _booking_node, day, _body = _evening_flight(client, "hitl-6")
        before = _status_map(_stored_nodes(client, "hitl-6", trip_id))
        for target in ("no-such-node", day["lunch"]["node_id"]):
            r = _confirm(client, "hitl-6", trip_id, target, "conservative")
            assert r.status_code == 409, r.text
        assert _status_map(_stored_nodes(client, "hitl-6", trip_id)) == before

    def test_confirm_unknown_intent_is_422(self, client):
        trip_id, booking, _day, _body = _evening_flight(client, "hitl-7")
        before = _status_map(_stored_nodes(client, "hitl-7", trip_id))
        r = _confirm(client, "hitl-7", trip_id, booking["node_id"], "nights_out")
        assert r.status_code == 422, r.text
        r = _event(
            client,
            "hitl-7",
            trip_id,
            "confirm_booking_reflow",
            preferences={},
            target=booking["node_id"],
        )
        assert r.status_code == 422, r.text
        assert _status_map(_stored_nodes(client, "hitl-7", trip_id)) == before

    def test_confirm_does_not_use_reroute_quota(self, client):
        trip_id, booking, _day, _body = _evening_flight(client, "hitl-12")

        def remaining():
            r = client.get("/api/v1/user/status", headers=auth("hitl-12"))
            assert r.status_code == 200, r.text
            return r.json()["daily_reroutes_remaining"]

        before = remaining()
        assert (
            _confirm(client, "hitl-12", trip_id, booking["node_id"], "conservative").status_code
            == 200
        )
        assert remaining() == before

    def test_confirm_is_light_and_calls_no_llm(self, client):
        trip_id, booking, _day, _body = _evening_flight(client, "hitl-13")
        with patch(
            "agents.state_machine.llm_service.generate_info_response",
            new_callable=AsyncMock,
        ) as generate:
            r = _confirm(client, "hitl-13", trip_id, booking["node_id"], "conservative")
        generate.assert_not_awaited()
        assert r.status_code == 200, r.text
        assert r.json()["routing_tier_used"] == "light"
        assert r.json()["message"] == "Day adjusted around your booking."

    def test_second_confirm_is_idempotent(self, client):
        trip_id, booking, day, _body = _evening_flight(client, "hitl-14")
        first = _confirm(client, "hitl-14", trip_id, booking["node_id"], "conservative")
        assert first.status_code == 200, first.text
        skipped_once = {
            n["node_id"]
            for n in _stored_nodes(client, "hitl-14", trip_id)
            if n["status"] == "skipped"
        }
        assert skipped_once == {
            day[s]["node_id"] for s in ("morning_tour", "lunch", "afternoon_evening_tour")
        }
        second = _confirm(client, "hitl-14", trip_id, booking["node_id"], "conservative")
        assert second.status_code == 200, second.text
        nodes = _stored_nodes(client, "hitl-14", trip_id)
        assert {n["node_id"] for n in nodes if n["status"] == "skipped"} == skipped_once
        assert _flexible(nodes, "2026-12-25")["dinner"]["status"] == "pending"
