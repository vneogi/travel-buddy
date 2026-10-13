"""SPEC-25 Phase B: Field intent tests.

Tests for TODAY_TONIGHT, NEARBY_OPTION, PRACTICAL_RULE, COMPARE,
retrieval miss, PLAN_CHANGE no-write, cache no plaintext, R17 sabotage.
"""

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from services.ask_service import (
    AskBudget,
    AskCache,
    AskIntent,
    AskPath,
    AskService,
    TrustTier,
    _cache_key,
    classify_ask_intent,
    format_today_tonight,
    load_practical_rules,
    retrieve_nearby_options,
    retrieve_practical_rule,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _FakeDB:
    """Minimal fake that serves list_venues_for_region."""

    def __init__(self, venues=None):
        self._venues = venues or []

    def list_venues_for_region(self, geo_region):
        return [v for v in self._venues if v.get("geo_region") == geo_region]


_LP_CAFE = {
    "venue_id": "joma_lp",
    "name": "Joma Bakery Cafe",
    "category": "cafe",
    "description": "Popular bakery with wifi and air conditioning.",
    "micro_location": "peninsula_old_town",
    "geo_region": "luang_prabang_laos",
    "vibe_tags": ["lively", "local_favourite"],
}

_LP_RESTAURANT = {
    "venue_id": "tamarind_lp",
    "name": "Tamarind Restaurant",
    "category": "restaurant",
    "description": "Traditional Lao tasting menu with cooking class option.",
    "micro_location": "nam_khan_riverfront",
    "geo_region": "luang_prabang_laos",
    "vibe_tags": ["authentic"],
}

_LP_TEMPLE = {
    "venue_id": "wat_xieng_thong",
    "name": "Wat Xieng Thong",
    "category": "temple",
    "description": "16th-century riverside temple complex.",
    "micro_location": "peninsula_old_town",
    "geo_region": "luang_prabang_laos",
}

_DUBAI_RESTAURANT = {
    "venue_id": "dubai_rest",
    "name": "Al Mahara",
    "category": "restaurant",
    "description": "Fine dining at Burj Al Arab.",
    "micro_location": "Jumeirah",
    "geo_region": "dubai_uae",
}


def _make_node(
    name,
    start,
    duration=60,
    geo_region="luang_prabang_laos",
    status="pending",
    venue_id=None,
):
    return {
        "venue_name": name,
        "venue_id": venue_id or name.lower().replace(" ", "_"),
        "scheduled_start": start,
        "duration_minutes": duration,
        "geo_region": geo_region,
        "status": status,
    }


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class TestClassifier:
    def test_today_tonight_intent(self):
        assert classify_ask_intent("what's left today?") == AskIntent.TODAY_TONIGHT

    def test_tonight_intent(self):
        assert classify_ask_intent("what's on tonight?") == AskIntent.TODAY_TONIGHT

    def test_nearby_coffee(self):
        assert classify_ask_intent("where can I find coffee nearby?") == AskIntent.NEARBY_OPTION

    def test_nearby_work(self):
        assert classify_ask_intent("where can I work with wifi?") == AskIntent.NEARBY_OPTION

    def test_practical_temple(self):
        assert classify_ask_intent("what do I wear at the temple?") == AskIntent.PRACTICAL_RULE

    def test_practical_payment(self):
        assert classify_ask_intent("how do I pay, cash or card?") == AskIntent.PRACTICAL_RULE

    def test_compare_intent(self):
        assert classify_ask_intent("compare the cafes for me") == AskIntent.COMPARE

    def test_transport_is_practical_rule(self):
        """Proof: transport question must classify as PRACTICAL_RULE, not PLACE_IDENTITY."""
        assert classify_ask_intent("how do I get around?") == AskIntent.PRACTICAL_RULE

    def test_wifi_work_is_nearby_option(self):
        """Proof: wifi/work question must classify as NEARBY_OPTION, not PRACTICAL_RULE."""
        assert classify_ask_intent("where can I work with wifi?") == AskIntent.NEARBY_OPTION


# ---------------------------------------------------------------------------
# TODAY_TONIGHT
# ---------------------------------------------------------------------------


class TestTodayTonight:
    def test_remaining_today_cites_node_venues(self):
        # Use a fixed morning time so both nodes stay within today.
        now = datetime.now(tz=timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0)
        nodes = [
            _make_node("Wat Xieng Thong", now + timedelta(hours=1)),
            _make_node("Tamarind Dinner", now + timedelta(hours=4)),
        ]
        result = format_today_tonight(nodes, now, "luang_prabang_laos")
        assert result is not None
        answer, sids = result
        assert "Wat Xieng Thong" in answer
        assert "Tamarind Dinner" in answer
        assert len(sids) == 2

    def test_tomorrow_nodes_not_invented_tonight(self):
        # Use morning UTC so ICT (UTC+7) is same calendar day
        now = datetime.now(tz=timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0)
        # Node 2 days out -- definitely tomorrow even in ICT
        future_start = (now + timedelta(days=2)).replace(hour=8, minute=0, second=0)
        nodes = [_make_node("Morning Walk", future_start)]
        result = format_today_tonight(nodes, now, "luang_prabang_laos")
        assert result is None

    def test_completed_node_excluded(self):
        now = datetime.now(tz=timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0)
        nodes = [
            _make_node("Done Place", now + timedelta(hours=1), status="completed"),
            _make_node("Still Pending", now + timedelta(hours=2)),
        ]
        result = format_today_tonight(nodes, now, "luang_prabang_laos")
        assert result is not None
        answer, _ = result
        assert "Done Place" not in answer
        assert "Still Pending" in answer

    def test_handle_ask_today_tonight(self):
        svc = AskService(db=_FakeDB(), cache=AskCache(), budget=AskBudget())
        now = datetime.now(tz=timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0)
        nodes = [_make_node("Evening Temple", now + timedelta(hours=2))]
        resp = _run(
            svc.handle_ask(
                question="what's left today?",
                geo_region="luang_prabang_laos",
                user_id="u1",
                trip_nodes=nodes,
                now_utc=now,
            )
        )
        assert resp.intent == AskIntent.TODAY_TONIGHT
        assert resp.path == AskPath.GROUNDED_DETERMINISTIC
        assert "Evening Temple" in resp.answer

    def test_handle_ask_today_tonight_miss(self):
        svc = AskService(db=_FakeDB(), cache=AskCache(), budget=AskBudget())
        resp = _run(
            svc.handle_ask(
                question="what's left today?",
                geo_region="luang_prabang_laos",
                user_id="u1",
                trip_nodes=[],
            )
        )
        assert resp.intent == AskIntent.TODAY_TONIGHT
        assert resp.path == AskPath.RETRIEVAL_MISS


# ---------------------------------------------------------------------------
# NEARBY_OPTION
# ---------------------------------------------------------------------------


class TestNearbyOption:
    def test_returns_only_geo_region_venues(self):
        db = _FakeDB([_LP_CAFE, _LP_RESTAURANT, _DUBAI_RESTAURANT])
        facts = retrieve_nearby_options("where can I work with coffee?", "luang_prabang_laos", db)
        assert len(facts) >= 1
        for f in facts:
            assert f.geo_region == "luang_prabang_laos"

    def test_dubai_venue_cannot_appear_on_lp_trip(self):
        db = _FakeDB([_LP_CAFE, _DUBAI_RESTAURANT])
        facts = retrieve_nearby_options("where can I eat?", "luang_prabang_laos", db)
        ids = [f.source_id for f in facts]
        assert "dubai_rest" not in ids

    def test_handle_ask_nearby(self):
        db = _FakeDB([_LP_CAFE])
        svc = AskService(db=db, cache=AskCache(), budget=AskBudget())
        resp = _run(
            svc.handle_ask(
                question="where can I find coffee nearby?",
                geo_region="luang_prabang_laos",
                user_id="u1",
            )
        )
        assert resp.intent == AskIntent.NEARBY_OPTION
        assert resp.path == AskPath.GROUNDED_DETERMINISTIC
        assert "Joma" in resp.answer
        assert resp.source_ids == ["joma_lp"]


# ---------------------------------------------------------------------------
# PRACTICAL_RULE
# ---------------------------------------------------------------------------


class TestPracticalRule:
    def test_temple_etiquette_grounded(self):
        fact = retrieve_practical_rule("what do I wear at the temple?", "luang_prabang_laos")
        assert fact is not None
        assert "shoulder" in fact.text.lower() or "knee" in fact.text.lower()
        assert fact.source_id == "laos_temple_dress_v1"

    def test_empty_rules_is_retrieval_miss(self, monkeypatch):
        """R17 sabotage: if the rule table is empty, must be retrieval_miss."""
        monkeypatch.setattr("services.ask_service.load_practical_rules", lambda: [])
        fact = retrieve_practical_rule("what do I wear at the temple?", "luang_prabang_laos")
        assert fact is None

    def test_handle_ask_practical_rule(self):
        svc = AskService(db=_FakeDB(), cache=AskCache(), budget=AskBudget())
        resp = _run(
            svc.handle_ask(
                question="what do I wear at the temple?",
                geo_region="luang_prabang_laos",
                user_id="u1",
            )
        )
        assert resp.intent == AskIntent.PRACTICAL_RULE
        assert resp.path == AskPath.GROUNDED_DETERMINISTIC
        assert resp.source_ids == ["laos_temple_dress_v1"]

    def test_empty_rules_goes_red_on_confident(self, monkeypatch):
        """R17 sabotage: empty rule table -> test goes red if fake
        confident answer is returned."""
        monkeypatch.setattr("services.ask_service.load_practical_rules", lambda: [])
        svc = AskService(db=_FakeDB(), cache=AskCache(), budget=AskBudget())
        resp = _run(
            svc.handle_ask(
                question="what do I wear at the temple?",
                geo_region="luang_prabang_laos",
                user_id="u1",
            )
        )
        # Must NOT be grounded when rules are empty
        assert resp.path == AskPath.RETRIEVAL_MISS


# ---------------------------------------------------------------------------
# COMPARE
# ---------------------------------------------------------------------------


class TestCompare:
    def test_at_most_3_options(self):
        venues = [{**_LP_CAFE, "venue_id": f"v{i}", "name": f"Cafe {i}"} for i in range(5)]
        db = _FakeDB(venues)
        facts = retrieve_nearby_options("compare cafes", "luang_prabang_laos", db)
        assert len(facts) <= 3

    def test_compare_returns_source_ids(self):
        db = _FakeDB([_LP_CAFE, _LP_RESTAURANT])
        svc = AskService(db=db, cache=AskCache(), budget=AskBudget())
        resp = _run(
            svc.handle_ask(
                question="compare the cafes for lunch",
                geo_region="luang_prabang_laos",
                user_id="u1",
            )
        )
        assert resp.intent == AskIntent.COMPARE
        assert resp.path == AskPath.GROUNDED_DETERMINISTIC
        assert 1 <= len(resp.source_ids) <= 3
        assert all(isinstance(s, str) for s in resp.source_ids)


# ---------------------------------------------------------------------------
# Retrieval miss: no generation
# ---------------------------------------------------------------------------


class TestRetrievalMiss:
    def test_miss_invokes_no_generation(self):
        """Retrieval miss must not call any LLM generation function."""
        svc = AskService(db=_FakeDB(), cache=AskCache(), budget=AskBudget())
        # Question that won't match any catalog
        resp = _run(
            svc.handle_ask(
                question="what do I wear at the temple?",
                geo_region="unknown_region_xyz",
                user_id="u1",
            )
        )
        assert resp.path == AskPath.RETRIEVAL_MISS
        # No llm attribute should have been called
        assert svc.llm is None


# ---------------------------------------------------------------------------
# PLAN_CHANGE: still does not write trip_node rows
# ---------------------------------------------------------------------------


class TestPlanChangeNoWrite:
    def test_add_cafe_does_not_write(self):
        mock_db = MagicMock()
        svc = AskService(db=mock_db, cache=AskCache(), budget=AskBudget())
        resp = _run(
            svc.handle_ask(
                question="add this cafe to my trip",
                geo_region="luang_prabang_laos",
                user_id="u1",
            )
        )
        assert resp.intent == AskIntent.PLAN_CHANGE
        # Verify no writes to trip nodes
        mock_db.save_trip_nodes.assert_not_called()
        mock_db.save_trip.assert_not_called()


# ---------------------------------------------------------------------------
# Cache keys: no question plaintext, no secrets
# ---------------------------------------------------------------------------


class TestCacheKeyHygiene:
    def test_cache_key_is_hash_not_plaintext(self):
        question = "what are the opening hours?"
        key = _cache_key(question, "luang_prabang_laos", "venue1")
        # Key must be a hex hash, not contain the question
        assert question not in key
        assert len(key) == 64  # SHA-256 hex

    def test_cache_key_deterministic(self):
        k1 = _cache_key("test q", "region", "v1")
        k2 = _cache_key("test q", "region", "v1")
        assert k1 == k2

    def test_telemetry_has_no_question_text(self):
        svc = AskService(db=_FakeDB(), cache=AskCache(), budget=AskBudget())
        _run(
            svc.handle_ask(
                question="what do I wear at the temple?",
                geo_region="luang_prabang_laos",
                user_id="u1",
            )
        )
        for tel in svc.telemetry_log:
            # Telemetry record must not contain question text
            assert not hasattr(tel, "question_text") or tel.question_text == ""
            tel_dict = tel.__dict__
            for v in tel_dict.values():
                if isinstance(v, str):
                    assert "wear at the temple" not in v


# ---------------------------------------------------------------------------
# Existing spec25 grounded tests must not regress
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# HTTP integration: TODAY_TONIGHT via state machine
# ---------------------------------------------------------------------------


class TestHTTPTodayTonight:
    """POST /api/v1/trip/event ask_info 'what\'s left today?' must include
    the pending venue name when the trip has a remaining node today."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from datetime import datetime, timezone

        from main import app
        from models.schemas import NodeStatus, TripNode, TripState
        from services.database_service import db_service
        from services.destination_tz import to_destination_local

        self.client = TestClient(app)
        # Schedule node 30 min from real now -- still pending and same ICT date
        real_now = datetime.now(tz=timezone.utc)
        node_start = real_now + timedelta(minutes=30)
        # Verify same ICT date (precondition)
        now_ict = to_destination_local(real_now, "luang_prabang_laos")
        node_ict = to_destination_local(node_start, "luang_prabang_laos")
        assert now_ict.date() == node_ict.date(), (
            f"Test precondition: {now_ict} and {node_ict} must share ICT date"
        )
        self.trip = TripState(
            trip_id="today-trip-1",
            user_id="test-user-today",
            geo_region="luang_prabang_laos",
            nodes=[
                TripNode(
                    node_id="tt1",
                    venue_name="Saffron Coffee",
                    venue_id="saffron_coffee",
                    duration_minutes=60,
                    scheduled_start=node_start,
                    is_locked=False,
                    status=NodeStatus.PENDING,
                    geo_region="luang_prabang_laos",
                ),
            ],
        )
        db_service.save_trip(self.trip)
        self.headers = {"X-Debug-User-Id": "test-user-today"}
        yield
        db_service._trips.pop("today-trip-1", None)

    def test_today_tonight_includes_venue_name(self):
        r = self.client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": "today-trip-1",
                "event_type": "ask_info",
                "message": "what's left today?",
            },
            headers=self.headers,
        )
        assert r.status_code == 200
        data = r.json()
        ask = data.get("ask_response")
        assert ask is not None, "ask_response must be present"
        assert ask["intent"] == "today_tonight"
        assert ask["path"] == "grounded_deterministic"
        assert "Saffron Coffee" in ask["answer"]


class TestExistingIntentsStillWork:
    def test_place_identity_classified(self):
        assert classify_ask_intent("tell me about Joma Bakery") == AskIntent.PLACE_IDENTITY

    def test_opening_hours_classified(self):
        assert classify_ask_intent("what time does it open?") == AskIntent.OPENING_HOURS

    def test_dish_fact_classified(self):
        assert classify_ask_intent("what food should I try?") == AskIntent.DISH_FACT

    def test_plan_change_classified(self):
        assert classify_ask_intent("swap this for something else") == AskIntent.PLAN_CHANGE

    def test_out_of_scope(self):
        assert classify_ask_intent("translate this sentence to French") == AskIntent.OUT_OF_SCOPE
