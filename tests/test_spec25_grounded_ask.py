"""SPEC-25 correction pass: fail-closed tests.

Each production bug has a test that fails if the bug is reintroduced.
Each named path has exactly one fixture that can only take that path.
Includes HTTP integration tests via TestClient.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

from services.ask_service import (
    AskBudget,
    AskCache,
    AskIntent,
    AskPath,
    AskResponse,
    AskService,
    AskTelemetry,
    TrustTier,
    classify_ask_intent,
    load_dish_glossary,
    _region_matches,
    _is_dietary_question,
    _render_structured_hours,
    _validate_structured_hours,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class FakeDB:
    def __init__(self, venues=None):
        self._venues = venues or []

    def list_venues_for_region(self, geo_region):
        return [v for v in self._venues if v.get("geo_region") == geo_region]


LAOS_VENUE = {
    "venue_id": "lp-v1",
    "name": "Ban Anou Night Market",
    "description": "Popular night market in Vientiane.",
    "micro_location": "Ban Anou, central Vientiane",
    "opening_hours": "17:00-23:00",
    "opening_hours_structured": {
        "mon": [["17:00", "23:00"]],
        "tue": [["17:00", "23:00"]],
        "wed": [["17:00", "23:00"]],
        "thu": [["17:00", "23:00"]],
        "fri": [["17:00", "23:00"]],
        "sat": [["17:00", "23:00"]],
        "sun": [["17:00", "23:00"]],
    },
    "geo_region": "vientiane_laos",
}

LAOS_VENUE_DEFAULT_HOURS = {
    "venue_id": "lp-v2",
    "name": "Default Hours Venue",
    "description": "A venue with default hours.",
    "micro_location": "Somewhere",
    "opening_hours": "09:00-22:00",
    "geo_region": "vientiane_laos",
}

DUBAI_VENUE = {
    "venue_id": "dubai-v1",
    "name": "Spice Souk",
    "description": "Traditional spice market in Deira.",
    "micro_location": "Deira, Old Dubai",
    "opening_hours": "09:00-22:00",
    "geo_region": "dubai_uae",
}


def _laos_glossary():
    path = Path(__file__).resolve().parent.parent / "data" / "laos_dish_glossary.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {
        "region": "laos",
        "dishes": [
            {
                "dish_key": "khao_niaw",
                "name_en": "Lao Sticky Rice",
                "name_roman": "khao niaw",
                "description": "Steamed glutinous rice.",
                "contains": [],
                "suitable_for": ["vegetarian", "vegan"],
            }
        ],
    }


def _svc(venues=None, glossary=None, dish_glossary=None):
    """Create an AskService with isolated cache/budget per test."""
    return AskService(
        db=FakeDB(venues=venues or []),
        dish_glossary=dish_glossary or glossary,
        cache=AskCache(),
        budget=AskBudget(),
    )


# ===========================================================================
# Path: GROUNDED_DETERMINISTIC -- known Laos venue hours
# ===========================================================================


class TestGroundedDeterministic:
    @pytest.mark.asyncio
    async def test_hours_cites_source(self):
        svc = _svc(venues=[LAOS_VENUE])
        resp = await svc.handle_ask(
            question="What are the opening hours?",
            geo_region="vientiane_laos",
            user_id="u1",
            venue_name="Ban Anou Night Market",
        )
        assert resp.path == AskPath.GROUNDED_DETERMINISTIC
        assert resp.tier == TrustTier.HEDGE
        assert "lp-v1" in resp.source_ids
        assert "17:00-23:00" in resp.answer or "catalog hours" in resp.answer

    @pytest.mark.asyncio
    async def test_dish_cites_source(self):
        svc = _svc(dish_glossary=_laos_glossary())
        resp = await svc.handle_ask(
            question="What food should I try?",
            geo_region="vientiane_laos",
            user_id="u1",
        )
        assert resp.path == AskPath.GROUNDED_DETERMINISTIC
        assert resp.source_ids
        assert resp.source_class == "curated_catalog"

    @pytest.mark.asyncio
    async def test_place_returns_description(self):
        svc = _svc(venues=[LAOS_VENUE])
        resp = await svc.handle_ask(
            question="Tell me about Ban Anou Night Market",
            geo_region="vientiane_laos",
            user_id="u1",
            venue_name="Ban Anou Night Market",
        )
        assert resp.path == AskPath.GROUNDED_DETERMINISTIC
        assert "Ban Anou" in resp.answer


# ===========================================================================
# Path: CACHE_HIT -- repeat catalog question
# ===========================================================================


class TestCacheHit:
    @pytest.mark.asyncio
    async def test_repeat_catalog_question_zero_retrieval(self):
        svc = _svc(venues=[LAOS_VENUE])
        r1 = await svc.handle_ask(
            question="What are the opening hours?",
            geo_region="vientiane_laos",
            user_id="u1",
            venue_name="Ban Anou Night Market",
        )
        assert r1.path == AskPath.GROUNDED_DETERMINISTIC
        r2 = await svc.handle_ask(
            question="What are the opening hours?",
            geo_region="vientiane_laos",
            user_id="u1",
            venue_name="Ban Anou Night Market",
        )
        assert r2.path == AskPath.CACHE_HIT
        assert r2.from_cache is True


# ===========================================================================
# Path: RETRIEVAL_MISS -- unknown venue / empty region
# ===========================================================================


class TestRetrievalMiss:
    @pytest.mark.asyncio
    async def test_unknown_venue_refuses(self):
        svc = _svc()  # empty DB
        resp = await svc.handle_ask(
            question="What time does it open?",
            geo_region="vientiane_laos",
            user_id="u1",
            venue_name="NonExistent",
        )
        assert resp.path == AskPath.RETRIEVAL_MISS
        assert resp.tier == TrustTier.REFUSE

    @pytest.mark.asyncio
    async def test_empty_region_refuses(self):
        svc = _svc(venues=[LAOS_VENUE])
        resp = await svc.handle_ask(
            question="What time does it open?",
            geo_region="",
            user_id="u1",
            venue_name="Ban Anou Night Market",
        )
        assert resp.path == AskPath.RETRIEVAL_MISS


# ===========================================================================
# Path: OUT_OF_SCOPE -- joke / weather / live price
# ===========================================================================


class TestOutOfScope:
    @pytest.mark.asyncio
    async def test_joke_is_refused(self):
        svc = _svc()
        resp = await svc.handle_ask(
            question="Tell me a joke",
            geo_region="vientiane_laos",
            user_id="u1",
        )
        assert resp.path == AskPath.OUT_OF_SCOPE
        assert resp.tier == TrustTier.REFUSE


# ===========================================================================
# Path: PLAN_CHANGE -- typed HITL proposal
# ===========================================================================


class TestPlanChange:
    @pytest.mark.asyncio
    async def test_swap_returns_typed_proposal(self):
        svc = _svc()
        resp = await svc.handle_ask(
            question="Can you swap this activity?",
            geo_region="vientiane_laos",
            user_id="u1",
            target_node_id="node-42",
        )
        assert resp.intent == AskIntent.PLAN_CHANGE
        assert resp.tier == TrustTier.DEFER
        assert resp.proposal is not None
        assert resp.proposal["event_type"] == "swap_activity"
        assert resp.proposal["target_node_id"] == "node-42"
        assert not hasattr(resp, "updated_nodes")

    @pytest.mark.asyncio
    async def test_cancel_returns_cancel_proposal(self):
        svc = _svc()
        resp = await svc.handle_ask(
            question="Cancel this activity",
            geo_region="vientiane_laos",
            user_id="u1",
            target_node_id="node-7",
        )
        assert resp.intent == AskIntent.PLAN_CHANGE
        assert resp.proposal is not None
        assert resp.proposal["event_type"] == "cancel_activity"

    @pytest.mark.asyncio
    async def test_ambiguous_defers_without_proposal(self):
        """swap + cancel both score 1 -> ambiguous -> no proposal."""
        svc = _svc()
        resp = await svc.handle_ask(
            question="Swap or cancel this activity",
            geo_region="vientiane_laos",
            user_id="u1",
        )
        assert resp.intent == AskIntent.PLAN_CHANGE
        assert resp.tier == TrustTier.DEFER
        assert resp.proposal is None
        assert "clarify" in resp.answer.lower()

    @pytest.mark.asyncio
    async def test_remove_reaches_plan_change(self):
        """'remove' must reach PLAN_CHANGE via main classifier."""
        svc = _svc()
        resp = await svc.handle_ask(
            question="Remove this activity",
            geo_region="vientiane_laos",
            user_id="u1",
            target_node_id="n1",
        )
        assert resp.intent == AskIntent.PLAN_CHANGE
        assert resp.proposal is not None
        assert resp.proposal["event_type"] == "cancel_activity"

    @pytest.mark.asyncio
    async def test_shift_reaches_plan_change(self):
        """'shift' must reach PLAN_CHANGE and map to reroute."""
        svc = _svc()
        resp = await svc.handle_ask(
            question="Shift this to later",
            geo_region="vientiane_laos",
            user_id="u1",
        )
        assert resp.intent == AskIntent.PLAN_CHANGE
        assert resp.proposal is not None
        assert resp.proposal["event_type"] == "reroute"

    @pytest.mark.asyncio
    async def test_switch_reaches_plan_change(self):
        """'switch' must reach PLAN_CHANGE and map to swap_activity."""
        svc = _svc()
        resp = await svc.handle_ask(
            question="Switch this for something else",
            geo_region="vientiane_laos",
            user_id="u1",
        )
        assert resp.intent == AskIntent.PLAN_CHANGE
        assert resp.proposal is not None
        assert resp.proposal["event_type"] == "swap_activity"

    @pytest.mark.asyncio
    async def test_insert_reaches_plan_change(self):
        """'insert' must reach PLAN_CHANGE and map to add_activity."""
        svc = _svc()
        resp = await svc.handle_ask(
            question="Insert a visit to the museum",
            geo_region="vientiane_laos",
            user_id="u1",
        )
        assert resp.intent == AskIntent.PLAN_CHANGE
        assert resp.proposal is not None
        assert resp.proposal["event_type"] == "add_activity"


# ===========================================================================
# Bug #4: Cache isolation -- TRIP_CURRENT_NEXT never cached
# ===========================================================================


class TestCacheIsolation:
    @pytest.mark.asyncio
    async def test_current_next_never_cached(self):
        svc = _svc()
        r1 = await svc.handle_ask(
            question="What's next on my trip?",
            geo_region="vientiane_laos",
            user_id="user-A",
            current_node_summary="Wat Xieng Thong at 09:00 (90 min)",
        )
        assert r1.path == AskPath.GROUNDED_DETERMINISTIC
        assert svc.cache.size() == 0  # Must not be cached

    @pytest.mark.asyncio
    async def test_two_users_different_trips_no_leak(self):
        """User B must not see User A's itinerary schedule."""
        svc = _svc()
        await svc.handle_ask(
            question="What's next on my trip?",
            geo_region="vientiane_laos",
            user_id="user-A",
            current_node_summary="Secret Place A at 10:00 (60 min)",
        )
        r2 = await svc.handle_ask(
            question="What's next on my trip?",
            geo_region="vientiane_laos",
            user_id="user-B",
            current_node_summary="Secret Place B at 14:00 (45 min)",
        )
        assert "Secret Place A" not in r2.answer
        assert "Secret Place B" in r2.answer


# ===========================================================================
# Bug #5: SPEC-14 dietary claims
# ===========================================================================


class TestSpec14Dietary:
    @pytest.mark.asyncio
    async def test_dish_answer_has_no_suitable_for(self):
        svc = _svc(dish_glossary=_laos_glossary())
        resp = await svc.handle_ask(
            question="What food should I try?",
            geo_region="vientiane_laos",
            user_id="u1",
        )
        answer_lower = resp.answer.lower()
        assert "suitable for" not in answer_lower
        assert "vegetarian" not in answer_lower
        assert "vegan" not in answer_lower
        assert "halal" not in answer_lower

    @pytest.mark.asyncio
    async def test_dietary_question_hedges_with_disclaimer(self):
        svc = _svc(dish_glossary=_laos_glossary())
        resp = await svc.handle_ask(
            question="Is the food vegetarian?",
            geo_region="vientiane_laos",
            user_id="u1",
        )
        assert resp.tier == TrustTier.HEDGE
        assert resp.food_disclaimer is not None
        assert "cannot confirm dietary suitability" in resp.answer.lower()

    @pytest.mark.asyncio
    async def test_dish_answer_includes_food_disclaimer(self):
        svc = _svc(dish_glossary=_laos_glossary())
        resp = await svc.handle_ask(
            question="What food should I try?",
            geo_region="vientiane_laos",
            user_id="u1",
        )
        assert resp.food_disclaimer is not None


# ===========================================================================
# Bug #6: Hours authority -- default hours refused
# ===========================================================================


class TestHoursAuthority:
    @pytest.mark.asyncio
    async def test_default_hours_returns_miss(self):
        svc = _svc(venues=[LAOS_VENUE_DEFAULT_HOURS])
        resp = await svc.handle_ask(
            question="What time does it open?",
            geo_region="vientiane_laos",
            user_id="u1",
            venue_name="Default Hours Venue",
        )
        # Default hours (09:00-22:00) without structured -> miss
        assert resp.path == AskPath.RETRIEVAL_MISS

    @pytest.mark.asyncio
    async def test_structured_hours_returns_hedge(self):
        svc = _svc(venues=[LAOS_VENUE])  # has structured
        resp = await svc.handle_ask(
            question="What time does it open?",
            geo_region="vientiane_laos",
            user_id="u1",
            venue_name="Ban Anou Night Market",
        )
        assert resp.path == AskPath.GROUNDED_DETERMINISTIC
        assert resp.tier == TrustTier.HEDGE
        assert resp.tier != TrustTier.ASSERT
        # Blocker 4: structured hours must be rendered directly
        assert "Mon 17:00-23:00" in resp.answer
        assert "Tue 17:00-23:00" in resp.answer

    @pytest.mark.asyncio
    async def test_malformed_structured_hours_returns_miss(self):
        """Partial weekdays (missing days) must produce RETRIEVAL_MISS."""
        venue = {
            **LAOS_VENUE,
            "venue_id": "partial-v",
            "opening_hours_structured": {"mon": [["09:00", "17:00"]]},
        }
        svc = _svc(venues=[venue])
        resp = await svc.handle_ask(
            question="What time does it open?",
            geo_region="vientiane_laos",
            user_id="u1",
            venue_name="Ban Anou Night Market",
        )
        assert resp.path == AskPath.RETRIEVAL_MISS

    @pytest.mark.asyncio
    async def test_empty_dict_structured_hours_returns_miss(self):
        venue = {
            **LAOS_VENUE,
            "venue_id": "empty-v",
            "opening_hours_structured": {},
        }
        svc = _svc(venues=[venue])
        resp = await svc.handle_ask(
            question="What time does it open?",
            geo_region="vientiane_laos",
            user_id="u1",
            venue_name="Ban Anou Night Market",
        )
        assert resp.path == AskPath.RETRIEVAL_MISS

    def test_validate_valid(self):
        assert _validate_structured_hours(LAOS_VENUE["opening_hours_structured"])

    def test_validate_missing_days(self):
        assert not _validate_structured_hours({"mon": [["09:00", "17:00"]]})

    def test_validate_bad_slot_format(self):
        bad = {
            d: [["9am", "5pm"]]
            for d in [
                "mon",
                "tue",
                "wed",
                "thu",
                "fri",
                "sat",
                "sun",
            ]
        }
        assert not _validate_structured_hours(bad)

    def test_render_full_week(self):
        result = _render_structured_hours(LAOS_VENUE["opening_hours_structured"])
        assert "Mon 17:00-23:00" in result
        assert "Sun 17:00-23:00" in result


# ===========================================================================
# Bug #9: Region stickiness -- exact match
# ===========================================================================


class TestRegionMatch:
    def test_empty_region_never_matches(self):
        assert not _region_matches("", "vientiane_laos")
        assert not _region_matches("laos", "")

    def test_laos_matches_vientiane_laos(self):
        assert _region_matches("laos", "vientiane_laos")

    def test_laos_matches_luang_prabang_laos(self):
        assert _region_matches("laos", "luang_prabang_laos")

    def test_dubai_does_not_match_vientiane(self):
        assert not _region_matches("dubai", "vientiane_laos")

    def test_substring_false_positive_blocked(self):
        # 'ao' is in 'laos' but not a component
        assert not _region_matches("ao", "vientiane_laos")

    @pytest.mark.asyncio
    async def test_laos_trip_no_dubai_venues(self):
        svc = _svc(venues=[DUBAI_VENUE, LAOS_VENUE])
        resp = await svc.handle_ask(
            question="What are the opening hours?",
            geo_region="vientiane_laos",
            user_id="u1",
            venue_name="Spice Souk",  # Dubai venue
        )
        assert "dubai-v1" not in resp.source_ids

    @pytest.mark.asyncio
    async def test_dubai_glossary_not_used_for_laos(self):
        dubai_glossary = {
            "region": "dubai",
            "dishes": [
                {
                    "dish_key": "shawarma",
                    "name_en": "Shawarma",
                    "description": "Middle Eastern wrap.",
                    "contains": [],
                    "suitable_for": ["halal"],
                }
            ],
        }
        svc = _svc(dish_glossary=dubai_glossary)
        resp = await svc.handle_ask(
            question="What food should I try?",
            geo_region="vientiane_laos",
            user_id="u1",
        )
        assert "Shawarma" not in resp.answer
        assert resp.path == AskPath.RETRIEVAL_MISS

    def test_load_glossary_empty_region_returns_none(self):
        assert load_dish_glossary("") is None


# ===========================================================================
# Bug #3: Identity budget -- per-user, not collapsed
# ===========================================================================


class TestIdentityBudget:
    def test_anonymous_lower_than_signed_in(self):
        b = AskBudget()
        assert b.remaining("x", is_anonymous=True) < b.remaining("x", is_anonymous=False)

    def test_two_users_independent_budgets(self):
        b = AskBudget()
        for _ in range(5):
            b.consume("anon-1", is_anonymous=True)
        assert b.remaining("anon-1", is_anonymous=True) == 0
        assert b.remaining("anon-2", is_anonymous=True) == 5
        assert b.remaining("signed-1", is_anonymous=False) == 20


# ===========================================================================
# Bug #10: Telemetry has no question text
# ===========================================================================


class TestTelemetry:
    @pytest.mark.asyncio
    async def test_telemetry_no_question_text(self):
        svc = _svc(venues=[LAOS_VENUE])
        question = "What are the opening hours of Ban Anou Night Market?"
        await svc.handle_ask(
            question=question,
            geo_region="vientiane_laos",
            user_id="u1",
            venue_name="Ban Anou Night Market",
        )
        assert len(svc.telemetry_log) == 1
        tel = svc.telemetry_log[0]
        tel_str = json.dumps(tel.__dict__)
        assert question not in tel_str
        assert "opening_hours" not in tel_str or "intent" in tel_str
        assert tel.intent == "opening_hours"
        assert tel.path == "grounded_deterministic"
        assert tel.geo_region == "vientiane_laos"
        assert tel.source_ids

    @pytest.mark.asyncio
    async def test_telemetry_emitted_to_logger(self, caplog):
        """Prove _emit_telemetry actually calls logger.info."""
        svc = _svc(venues=[LAOS_VENUE])
        with caplog.at_level(logging.INFO, logger="ask_service"):
            await svc.handle_ask(
                question="What are the opening hours?",
                geo_region="vientiane_laos",
                user_id="u1",
                venue_name="Ban Anou Night Market",
            )
        assert any("ask_telemetry" in r.message for r in caplog.records)


# ===========================================================================
# HTTP integration: Bug #1 (envelope present), Bug #2 (no save_trip)
# ===========================================================================


class TestHTTPIntegration:
    """TestClient integration tests for POST /api/v1/trip/event ASK_INFO."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from main import app
        from services.database_service import db_service
        from models.schemas import TripState, TripNode, NodeStatus
        from datetime import datetime, timezone

        self.client = TestClient(app)
        self.trip = TripState(
            trip_id="ask-trip-1",
            user_id="test-user-001",
            geo_region="vientiane_laos",
            nodes=[
                TripNode(
                    node_id="n1",
                    venue_name="Ban Anou Night Market",
                    venue_id="ban_anou",
                    duration_minutes=90,
                    scheduled_start=datetime(2026, 10, 5, 11, 0, tzinfo=timezone.utc),
                    is_locked=False,
                    status=NodeStatus.PENDING,
                    geo_region="vientiane_laos",
                ),
            ],
        )
        db_service.save_trip(self.trip)
        self.headers = {"X-Debug-User-Id": "test-user-001"}
        yield
        db_service._trips.clear()

    def test_ask_info_returns_typed_envelope(self):
        r = self.client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": "ask-trip-1",
                "event_type": "ask_info",
                "message": "Tell me a joke",
            },
            headers=self.headers,
        )
        assert r.status_code == 200
        data = r.json()
        ask = data.get("ask_response")
        assert ask is not None, "ask_response must be present"
        assert "tier" in ask
        assert "path" in ask
        assert "intent" in ask

    def test_ask_info_does_not_save_trip(self):
        from services.database_service import db_service

        original_updated_at = self.trip.updated_at
        self.client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": "ask-trip-1",
                "event_type": "ask_info",
                "message": "What time does it open?",
            },
            headers=self.headers,
        )
        stored = db_service.get_trip("ask-trip-1")
        assert stored.updated_at == original_updated_at

    def test_ask_info_returns_empty_updated_nodes(self):
        r = self.client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": "ask-trip-1",
                "event_type": "ask_info",
                "message": "What time does it open?",
            },
            headers=self.headers,
        )
        data = r.json()
        assert data["updated_nodes"] == []

    def test_http_second_catalog_request_returns_cache_hit(self):
        """Proof: two identical HTTP ASK_INFO requests; second is cache_hit."""
        payload = {
            "trip_id": "ask-trip-1",
            "event_type": "ask_info",
            "message": "Tell me about Ban Anou Night Market",
        }
        r1 = self.client.post("/api/v1/trip/event", json=payload, headers=self.headers)
        assert r1.status_code == 200
        ask1 = r1.json().get("ask_response")
        assert ask1 is not None
        assert ask1["path"] != "cache_hit"

        r2 = self.client.post("/api/v1/trip/event", json=payload, headers=self.headers)
        assert r2.status_code == 200
        ask2 = r2.json().get("ask_response")
        assert ask2 is not None
        assert ask2["path"] == "cache_hit", f"Expected cache_hit, got {ask2['path']}"
        assert ask2["from_cache"] is True


# ===========================================================================
# Cache-hit telemetry carries source_ids
# ===========================================================================


class TestCacheHitTelemetry:
    @pytest.mark.asyncio
    async def test_cache_hit_telemetry_has_source_ids(self):
        """Cache-hit telemetry must carry the cached source_ids."""
        svc = _svc(venues=[LAOS_VENUE])
        # First call populates cache
        r1 = await svc.handle_ask(
            question="What are the opening hours?",
            geo_region="vientiane_laos",
            user_id="u1",
            venue_name="Ban Anou Night Market",
        )
        assert r1.source_ids  # non-empty
        original_ids = list(r1.source_ids)

        # Second call is cache hit
        await svc.handle_ask(
            question="What are the opening hours?",
            geo_region="vientiane_laos",
            user_id="u1",
            venue_name="Ban Anou Night Market",
        )
        # Telemetry for the cache hit (second entry)
        assert len(svc.telemetry_log) == 2
        tel_hit = svc.telemetry_log[1]
        assert tel_hit.cache_status == "hit"
        assert tel_hit.source_ids == original_ids


# ===========================================================================
# Named path coverage
# ===========================================================================


class TestSingletonPersistence:
    """Blocker 1: cache/budget must survive across AskService instances."""

    def test_shared_cache_persists_across_instances(self):
        cache = AskCache()
        svc1 = AskService(db=FakeDB(), cache=cache, budget=AskBudget())
        svc2 = AskService(db=FakeDB(), cache=cache, budget=AskBudget())
        # svc1 writes to cache
        resp = AskResponse(
            answer="test",
            tier=TrustTier.HEDGE,
            path=AskPath.GROUNDED_DETERMINISTIC,
            intent=AskIntent.PLACE_IDENTITY,
            source_ids=["v1"],
        )
        svc1.cache.put("q", "r", "v", resp)
        # svc2 reads from the same cache
        hit = svc2.cache.get("q", "r", "v")
        assert hit is not None
        assert hit.from_cache is True

    def test_shared_budget_persists_across_instances(self):
        budget = AskBudget()
        svc1 = AskService(db=FakeDB(), cache=AskCache(), budget=budget)
        svc2 = AskService(db=FakeDB(), cache=AskCache(), budget=budget)
        for _ in range(5):
            svc1.budget.consume("u1", is_anonymous=True)
        assert svc2.budget.remaining("u1", is_anonymous=True) == 0


class TestCacheVersion:
    """Cache key includes catalog version to invalidate stale data."""

    def test_different_versions_do_not_collide(self):
        from services.ask_service import _cache_key

        k1 = _cache_key("q", "r", "v", catalog_version="v1")
        k2 = _cache_key("q", "r", "v", catalog_version="v2")
        assert k1 != k2


class TestNamedPaths:
    def test_all_paths_distinct(self):
        paths = [p.value for p in AskPath]
        assert len(paths) == len(set(paths))

    def test_all_tiers_present(self):
        tiers = {t.value for t in TrustTier}
        assert tiers == {"assert", "hedge", "ask", "defer", "refuse"}

    def test_all_intents_present(self):
        intents = {i.value for i in AskIntent}
        assert intents == {
            "place_identity",
            "opening_hours",
            "dish_fact",
            "trip_current_next",
            "plan_change",
            "out_of_scope",
        }
