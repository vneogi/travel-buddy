"""SPEC-46 Phase A: What Now deterministic handler tests.

Tests cover:
 - Region isolation
 - Exclusions (infrastructure, itinerary, context, missing venue_id)
 - Available-window guard (dwell + walk > budget)
 - Opening hours (structured key)
 - Missing coords: no walk-based reason codes
 - Booking reachability (candidate -> lock walking)
 - Hotel not treated as next booking
 - Region-anchor copy (no "nearby")
 - Invalid context refusal
 - Reason predicates allowlist
 - Retrieval miss
 - Zero LLM calls + budget unchanged (live state-machine path)
 - Cache & telemetry isolation (live state-machine path)
 - Envelope contract
 - Validation
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from agents.state_machine import state_machine
from models.schemas import (
    AskResponseEnvelope,
    EventType,
    NodeStatus,
    TripNode,
    TripState,
)
from services.ask_service import (
    AskIntent,
    AskPath,
    TrustTier,
    WhatNowRequest,
    handle_what_now,
)

OPEN_ALL_DAY = {d: [["08:00", "22:00"]] for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}
CLOSED_ALL_DAY = {d: [] for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}


def _make_trip(ctx_node, now_utc):
    """Build a TripState from a context node dict."""
    return TripState(
        trip_id="trip-wn",
        user_id="u-wn",
        geo_region="vientiane_laos",
        nodes=[
            TripNode(
                node_id=ctx_node["node_id"],
                venue_name=ctx_node["venue_name"],
                venue_id=ctx_node["venue_id"],
                scheduled_start=datetime.fromisoformat(ctx_node["scheduled_start"]),
                duration_minutes=ctx_node["duration_minutes"],
                geo_region=ctx_node["geo_region"],
                micro_location=ctx_node.get("micro_location", ""),
                lat=ctx_node.get("lat"),
                lng=ctx_node.get("lng"),
                is_locked=False,
                status=NodeStatus.PENDING,
            )
        ],
    )


class FakeDb:
    def __init__(self, rows: dict[str, list[dict]]):
        self._rows = rows
        self.calls: list[str] = []

    def list_venues_for_region(self, geo_region: str):
        self.calls.append(geo_region)
        return [dict(r) for r in self._rows.get(geo_region, [])]


@pytest.fixture
def now_utc():
    # Friday 2026-10-02 04:00 UTC = 11:00 ICT (Vientiane)
    return datetime(2026, 10, 2, 4, 0, tzinfo=timezone.utc)


@pytest.fixture
def ctx_node(now_utc):
    return {
        "node_id": "n1",
        "venue_name": "Context Temple",
        "venue_id": "ctx-1",
        "scheduled_start": (now_utc - timedelta(minutes=30)).isoformat(),
        "duration_minutes": 60,
        "geo_region": "vientiane_laos",
        "micro_location": "nam_phou_fountain",
        "lat": 17.96345,
        "lng": 102.61112,
        "vibe_tags": ["quiet", "culture"],
        "is_locked": False,
        "node_kind": "activity",
    }


def _v(
    vid,
    name,
    *,
    geo="vientiane_laos",
    cat="temple",
    ml="nam_phou_fountain",
    lat=17.9640,
    lng=102.6120,
    dwell=45,
    hours_structured=None,
    hours=None,
    vibes=None,
    indoor="mixed",
    aircon=False,
):
    return {
        "venue_id": vid,
        "name": name,
        "geo_region": geo,
        "category": cat,
        "micro_location": ml,
        "lat": lat,
        "lng": lng,
        "typical_dwell_minutes": dwell,
        "opening_hours_structured": hours_structured
        if hours_structured is not None
        else OPEN_ALL_DAY,
        "opening_hours": hours or "09:00-22:00",
        "vibe_tags": vibes or [],
        "indoor_outdoor": indoor,
        "has_aircon": aircon,
    }


# -----------------------------------------------------------------
# Core handler tests (unit, via handle_what_now directly)
# -----------------------------------------------------------------


class TestRegionIsolation:
    def test_vientiane_never_returns_other_regions(self, now_utc, ctx_node):
        db = FakeDb(
            {
                "vientiane_laos": [_v("vt-1", "Wat Si Saket")],
                "dubai_uae": [_v("dxb", "Dubai Mall", geo="dubai_uae")],
            }
        )
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90, intent="culture"),
            [ctx_node],
            now_utc,
            "vientiane_laos",
            db,
        )
        assert db.calls == ["vientiane_laos"]
        assert [c["name"] for c in resp.what_now["candidates"]] == ["Wat Si Saket"]


class TestExclusions:
    def test_infrastructure_itinerary_context_excluded(self, now_utc, ctx_node):
        itin = {
            **ctx_node,
            "node_id": "n2",
            "venue_name": "Planned Cafe",
            "venue_id": "it-1",
            "scheduled_start": (now_utc + timedelta(hours=2)).isoformat(),
        }
        db = FakeDb(
            {
                "vientiane_laos": [
                    _v("ctx-1", "Context Temple"),
                    _v("it-1", "Planned Cafe", cat="cafe"),
                    _v("ph-1", "Pharmacy", cat="pharmacy"),
                    _v("ok-1", "Saffron", cat="cafe"),
                ]
            }
        )
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90, intent="anything"),
            [ctx_node, itin],
            now_utc,
            "vientiane_laos",
            db,
        )
        assert [c["venue_id"] for c in resp.what_now["candidates"]] == ["ok-1"]


class TestAvailableWindow:
    def test_90min_rejects_dwell_plus_walking_over_90(self, now_utc, ctx_node):
        db = FakeDb(
            {
                "vientiane_laos": [
                    _v("near", "Near", dwell=45),
                    _v(
                        "far",
                        "Far",
                        cat="museum",
                        dwell=65,
                        lat=17.98545,
                        lng=102.61112,
                    ),
                ]
            }
        )
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90, walking="longer"),
            [ctx_node],
            now_utc,
            "vientiane_laos",
            db,
        )
        ids = [c["venue_id"] for c in resp.what_now["candidates"]]
        assert "near" in ids
        assert "far" not in ids


class TestOpeningHoursStructured:
    """Fix 1: production-shaped opening_hours_structured."""

    def test_closed_via_structured_hours_excluded(self, now_utc, ctx_node):
        db = FakeDb(
            {
                "vientiane_laos": [
                    _v("open", "Open Museum", cat="museum"),
                    _v("shut", "Shut Temple", hours_structured=CLOSED_ALL_DAY),
                ]
            }
        )
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90),
            [ctx_node],
            now_utc,
            "vientiane_laos",
            db,
        )
        ids = [c["venue_id"] for c in resp.what_now["candidates"]]
        assert "open" in ids
        assert "shut" not in ids


class TestMissingCoordsReasonCodes:
    """Fix 2: unknown walking_time must not emit fits/keeps claims."""

    def test_no_fits_available_window_without_coords(self, now_utc, ctx_node):
        db = FakeDb(
            {"vientiane_laos": [_v("unk", "No Coords", cat="museum", lat=None, lng=None, dwell=45)]}
        )
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90),
            [ctx_node],
            now_utc,
            "vientiane_laos",
            db,
        )
        c = resp.what_now["candidates"][0]
        assert "fits_available_window" not in c["reason_codes"]
        assert "short_walk_from_context" not in c["reason_codes"]
        assert "walking_time" in c["unknown_fields"]

    def test_no_keeps_next_booking_without_coords(self, now_utc, ctx_node):
        """Candidate with no coords + next lock = excluded (cannot prove walk to lock)."""
        booking = {
            "node_id": "b1",
            "venue_name": "Train",
            "venue_id": "bk-1",
            "scheduled_start": (now_utc + timedelta(hours=3)).isoformat(),
            "duration_minutes": 30,
            "geo_region": "vientiane_laos",
            "is_locked": True,
            "node_kind": "booking",
            "booking_type": "train",
            "lat": 17.9640,
            "lng": 102.6120,
        }
        db = FakeDb(
            {"vientiane_laos": [_v("unk", "No Coords", cat="cafe", lat=None, lng=None, dwell=30)]}
        )
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90),
            [ctx_node, booking],
            now_utc,
            "vientiane_laos",
            db,
        )
        # Cannot prove candidate can walk to the lock -> excluded -> retrieval miss
        assert resp.path == AskPath.RETRIEVAL_MISS


class TestBookingReachability:
    """Fix 3: candidate -> lock walking in _violates_next_booking."""

    def test_walk_to_next_booking_breaks_reachability(self, now_utc, ctx_node):
        """activity_end + walk(candidate -> lock) > lock.start -> excluded.

        Lock at (17.975, 102.625), scheduled +60 min from now.
        "s" (near ctx AND near lock): 5+30+23 = 58 <= 60 -> fits.
        "l" (near ctx but FAR from lock): 28+30+51 = 109 > 60 -> excluded.
        Weakened (no cand->lock walk): "l" gets 28+30=58 <= 60 -> would pass.
        """
        booking = {
            "node_id": "b1",
            "venue_name": "Train Station",
            "venue_id": "bk-1",
            "scheduled_start": (now_utc + timedelta(minutes=60)).isoformat(),
            "duration_minutes": 30,
            "geo_region": "vientiane_laos",
            "is_locked": True,
            "node_kind": "booking",
            "booking_type": "train",
            "lat": 17.975,
            "lng": 102.625,
        }
        db = FakeDb(
            {
                "vientiane_laos": [
                    _v("s", "Quick", cat="cafe", dwell=30),
                    _v(
                        "l",
                        "Far From Lock",
                        cat="museum",
                        dwell=30,
                        lat=17.950,
                        lng=102.595,
                    ),
                ]
            }
        )
        resp = handle_what_now(
            WhatNowRequest(available_minutes=120, walking="longer"),
            [ctx_node, booking],
            now_utc,
            "vientiane_laos",
            db,
        )
        ids = [c["venue_id"] for c in resp.what_now["candidates"]]
        assert "s" in ids
        assert "l" not in ids

    def test_hotel_not_treated_as_next_booking(self, now_utc, ctx_node):
        hotel = {
            "node_id": "h1",
            "venue_name": "Hotel Laos",
            "venue_id": "hot-1",
            "scheduled_start": (now_utc + timedelta(minutes=50)).isoformat(),
            "duration_minutes": 720,
            "geo_region": "vientiane_laos",
            "is_locked": True,
            "node_kind": "booking",
            "booking_type": "hotel",
            "lat": 17.964,
            "lng": 102.611,
        }
        db = FakeDb({"vientiane_laos": [_v("v1", "Long Cafe", cat="cafe", dwell=60)]})
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90),
            [ctx_node, hotel],
            now_utc,
            "vientiane_laos",
            db,
        )
        ids = [c["venue_id"] for c in resp.what_now["candidates"]]
        assert "v1" in ids


class TestRegionAnchorCopy:
    """Fix 4: no 'nearby' or distance wording for region_anchor."""

    def test_region_anchor_answer_no_nearby(self, now_utc):
        db = FakeDb({"vientiane_laos": [_v("vt", "Wat Si Saket")]})
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90, intent="culture"),
            [],
            now_utc,
            "vientiane_laos",
            db,
        )
        assert resp.what_now["location_source"] == "region_anchor"
        low = resp.answer.lower()
        assert "nearby" not in low
        assert "within reach" not in low
        assert "wat si saket" in low

    def test_region_anchor_no_walk_claims(self, now_utc):
        db = FakeDb({"vientiane_laos": [_v("vt", "Wat Si Saket")]})
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90, intent="culture"),
            [],
            now_utc,
            "vientiane_laos",
            db,
        )
        c = resp.what_now["candidates"][0]
        assert "short_walk_from_context" not in c["reason_codes"]
        assert "same_neighbourhood" not in c["reason_codes"]


class TestMissingVenueId:
    """Fix 5: exclude venues with missing or malformed venue_id."""

    def test_missing_venue_id_excluded(self, now_utc, ctx_node):
        db = FakeDb(
            {
                "vientiane_laos": [
                    _v(None, "No ID"),
                    _v("", "Empty ID"),
                    _v("  ", "Whitespace ID"),
                    _v("ok-1", "Valid Venue"),
                ]
            }
        )
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90),
            [ctx_node],
            now_utc,
            "vientiane_laos",
            db,
        )
        assert [c["venue_id"] for c in resp.what_now["candidates"]] == ["ok-1"]


class TestInvalidContext:
    def test_foreign_node_refuses(self, now_utc, ctx_node):
        db = FakeDb({"vientiane_laos": [_v("vt", "Wat")]})
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90, context_node_id="foreign"),
            [ctx_node],
            now_utc,
            "vientiane_laos",
            db,
        )
        assert resp.path == AskPath.RETRIEVAL_MISS
        assert resp.tier == TrustTier.REFUSE
        assert resp.what_now is None


class TestReasonPredicates:
    def test_every_emitted_code_has_predicate(self, now_utc, ctx_node):
        db = FakeDb({"vientiane_laos": [_v("vt", "Wat Si Saket", vibes=["quiet"])]})
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90, intent="culture"),
            [ctx_node],
            now_utc,
            "vientiane_laos",
            db,
        )
        allowed = {
            "fits_available_window",
            "open_for_planned_time",
            "keeps_next_booking_reachable",
            "matches_requested_type",
            "matches_trip_interest",
            "same_neighbourhood",
            "short_walk_from_context",
            "lower_typical_dwell",
            "indoor_option",
        }
        for c in resp.what_now["candidates"]:
            for code in c["reason_codes"]:
                assert code in allowed, f"Unknown reason code: {code}"


class TestRetrievalMiss:
    def test_no_feasible_returns_miss(self, now_utc, ctx_node):
        db = FakeDb(
            {
                "vientiane_laos": [
                    _v("x", "Closed", hours_structured=CLOSED_ALL_DAY),
                    _v("y", "Huge", dwell=180, cat="museum"),
                ]
            }
        )
        resp = handle_what_now(
            WhatNowRequest(available_minutes=45, walking="short"),
            [ctx_node],
            now_utc,
            "vientiane_laos",
            db,
        )
        assert resp.path == AskPath.RETRIEVAL_MISS
        assert resp.tier == TrustTier.REFUSE


# -----------------------------------------------------------------
# Integration tests (route through process_event / state machine)
# -----------------------------------------------------------------


class TestNoLLMAndBudget:
    """Route through process_event -> what_now. llm.complete never called."""

    def test_zero_llm_calls_budget_unchanged(self, now_utc, ctx_node):
        from services.ask_service import AskBudget, _shared_cache

        trip = _make_trip(ctx_node, now_utc)
        budget = AskBudget()
        before = budget.remaining("u-wn-llm")
        cache_before = len(_shared_cache._store)

        with patch(
            "services.llm_service.llm_service.complete",
            side_effect=AssertionError("llm.complete called during what_now"),
        ):
            result = asyncio.run(
                state_machine.process_event(
                    trip_state=trip,
                    event_type=EventType.ASK_INFO.value,
                    message="What now?",
                    preferences={
                        "mode": "what_now",
                        "available_minutes": 90,
                        "intent": "culture",
                    },
                    now_utc=now_utc,
                    user_id="u-wn-llm",
                )
            )

        ask_resp = result.get("ask_response", {})
        assert ask_resp.get("intent") == "what_now"
        assert budget.remaining("u-wn-llm") == before
        assert len(_shared_cache._store) == cache_before


class TestCacheAndTelemetryIsolation:
    """Cache keys and event-log payload through live state-machine path."""

    def test_what_now_cache_unchanged_and_log_event_clean(self, now_utc, ctx_node):
        """Route through process_event. Shared cache must not grow.
        db_service.log_event must not be called (it lives in trip_router,
        not state_machine). Spy on the live db_service to prove this."""
        from services.ask_service import _shared_cache
        from services.db_provider import db_service as _live_db

        trip = _make_trip(ctx_node, now_utc)
        cache_before = len(_shared_cache._store)
        log_before = len(_live_db._event_log)

        asyncio.run(
            state_machine.process_event(
                trip_state=trip,
                event_type=EventType.ASK_INFO.value,
                message="What now?",
                preferences={
                    "mode": "what_now",
                    "available_minutes": 90,
                    "energy": "low",
                    "walking": "short",
                    "intent": "food",
                },
                now_utc=now_utc,
                user_id="u-wn-cache",
            )
        )

        # Cache unchanged
        assert len(_shared_cache._store) == cache_before

        # log_event not called during process_event (only trip_router calls it)
        assert len(_live_db._event_log) == log_before, (
            "log_event was called during process_event; "
            f"before={log_before}, after={len(_live_db._event_log)}"
        )

        # If any events were logged (e.g. from prior tests), verify none
        # contain what_now preferences in their payload
        for entry in _live_db._event_log:
            payload = entry.get("payload") or {}
            for forbidden in ("energy", "walking", "intent", "available_minutes"):
                assert forbidden not in payload, f"{forbidden} leaked into log_event payload"


class TestEnvelopeContract:
    def test_pydantic_envelope_accepts_what_now(self):
        env = AskResponseEnvelope(
            answer="Found 1",
            tier="hedge",
            path="grounded_deterministic",
            intent="what_now",
            source_ids=["vt-1"],
            source_class="curated_catalog",
            what_now={
                "location_source": "trip_position",
                "context_label": "Using your trip position",
                "candidates": [
                    {
                        "candidate_id": "what_now:vt-1",
                        "venue_id": "vt-1",
                        "name": "Wat",
                        "reason_codes": ["fits_available_window"],
                        "unknown_fields": ["price"],
                    }
                ],
            },
        )
        assert env.what_now.location_source == "trip_position"


class TestValidation:
    def test_invalid_duration_rejects(self):
        with pytest.raises(ValueError):
            WhatNowRequest(available_minutes=30)

    def test_invalid_energy_rejects(self):
        with pytest.raises(ValueError):
            WhatNowRequest(available_minutes=90, energy="extreme")
