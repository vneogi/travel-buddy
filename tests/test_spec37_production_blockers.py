"""SPEC-37: Production blocker tests -- info_ctx scope, cache geo key,
behavioral warnings, process_event integration, next-eligible-pending.

These tests exercise the state machine through process_event (integration)
and via targeted unit helpers, NOT just prompt strings or file reads.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from models.schemas import (
    EventType,
    NodeStatus,
    RoutingTier,
    TripNode,
    TripState,
)
from services.cache_service import cache_service


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _laos_corridor_trip(now_utc=None):
    """A Vientiane -> Luang Prabang corridor with realistic nodes.

    Oct 5-6 in Vientiane (completed/elapsed), Oct 7-8 in Luang Prabang
    (pending).  A question at Oct 7 06:00Z should resolve to lp1.
    """
    return TripState(
        trip_id="corridor-1",
        user_id="u1",
        geo_region="vientiane_laos",
        nodes=[
            TripNode(
                node_id="v1",
                venue_name="COPE Visitor Centre",
                venue_id="cope",
                duration_minutes=90,
                scheduled_start=datetime(2026, 10, 5, 2, 0, tzinfo=timezone.utc),
                is_locked=False,
                status=NodeStatus.COMPLETED,
                geo_region="vientiane_laos",
            ),
            TripNode(
                node_id="v2",
                venue_name="Ban Anou Night Market",
                venue_id="ban_anou",
                duration_minutes=90,
                scheduled_start=datetime(2026, 10, 6, 11, 0, tzinfo=timezone.utc),
                is_locked=False,
                status=NodeStatus.PENDING,
                geo_region="vientiane_laos",
            ),
            TripNode(
                node_id="lp1",
                venue_name="Wat Xieng Thong",
                venue_id="wat_xieng_thong",
                duration_minutes=90,
                scheduled_start=datetime(2026, 10, 7, 5, 30, tzinfo=timezone.utc),
                is_locked=False,
                status=NodeStatus.PENDING,
                geo_region="luang_prabang_laos",
            ),
            TripNode(
                node_id="lp2",
                venue_name="Kuang Si Falls",
                venue_id="kuang_si",
                duration_minutes=120,
                scheduled_start=datetime(2026, 10, 8, 3, 0, tzinfo=timezone.utc),
                is_locked=False,
                status=NodeStatus.PENDING,
                geo_region="luang_prabang_laos",
            ),
        ],
    )


def _dubai_trip():
    return TripState(
        trip_id="dubai-1",
        user_id="u1",
        geo_region="dubai_uae",
        nodes=[
            TripNode(
                node_id="d1",
                venue_name="Burj Khalifa",
                venue_id="burj_khalifa",
                duration_minutes=60,
                scheduled_start=datetime(2026, 10, 7, 5, 0, tzinfo=timezone.utc),
                is_locked=False,
                status=NodeStatus.PENDING,
                geo_region="dubai_uae",
            ),
        ],
    )


# ------------------------------------------------------------------
# Blocker 1: info_ctx defined before try -- HEAVY LLM failure
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_heavy_llm_failure_returns_canned_response_not_500():
    """When generate_itinerary_response throws on the HEAVY path,
    the except clause must use info_ctx (hoisted before try) and
    return a canned response, not raise.

    We mock venue_search and apply_structural so the ADD_ACTIVITY event
    actually reaches the LLM call with routing_tier == HEAVY.

    (SWAP_ACTIVITY now returns a deterministic response and never calls
    the LLM -- SPEC-41 configured-env guard.)
    """
    from agents.state_machine import state_machine

    trip = _laos_corridor_trip()

    def _passthrough_venue(state):
        """Pretend venue search found one candidate."""
        return state

    def _passthrough_apply(state):
        """Pretend structural apply swapped the node."""
        return state

    captured_fallback_ctx = {}

    def _spy_router(message, routing_tier, context=None):
        captured_fallback_ctx.update(context or {})
        return "Canned fallback after LLM failure."

    with (
        patch("config.settings.settings.litellm_api_key", "fake-key"),
        patch.object(
            state_machine,
            "_node_venue_search",
            side_effect=_passthrough_venue,
        ),
        patch.object(
            state_machine,
            "_node_apply_structural",
            side_effect=_passthrough_apply,
        ),
        patch(
            "services.llm_service.llm_service.generate_itinerary_response",
            new_callable=AsyncMock,
            side_effect=RuntimeError("model overloaded"),
        ),
        patch(
            "agents.router_agent.router_agent.generate_response",
            side_effect=_spy_router,
        ),
    ):
        result = await state_machine.process_event(
            trip_state=trip,
            event_type=EventType.ADD_ACTIVITY.value,
            message="add a quiet temple visit",
            target_node_id="lp1",
            now_utc=datetime(2026, 10, 7, 6, 0, tzinfo=timezone.utc),
        )

    # Must NOT be an empty string or raise -- should be a canned fallback
    assert result["response"], "Response was empty after HEAVY LLM failure"
    assert "500" not in result["response"]
    # Prove info_ctx was available in the except clause: the fallback
    # must have received geo_region from the hoisted context.
    assert captured_fallback_ctx.get("geo_region") == "luang_prabang_laos", (
        f"Expected luang_prabang_laos, got {captured_fallback_ctx.get('geo_region')}"
    )
    # The trip state should still be returned (mutation preserved if any)
    assert result["updated_trip_state"] is not None


# ------------------------------------------------------------------
# Blocker 2: Cache geo-scoped -- sabotage test
# ------------------------------------------------------------------


def test_cache_dubai_answer_not_served_in_vientiane():
    """Cache a response for Dubai context, then query with the same
    text in Vientiane context -- the Dubai answer must NOT be returned."""
    cache_service.clear_all()

    # Store a Dubai answer
    cache_service.store_response(
        "What temples should I visit?",
        "Visit the Jumeirah Mosque in Dubai.",
        geo_region="dubai_uae",
        venue_name="Burj Khalifa",
    )

    # Same question text, different region
    hit = cache_service.check_cache(
        "What temples should I visit?",
        geo_region="vientiane_laos",
        venue_name="COPE Visitor Centre",
    )
    assert hit is None, f"Dubai cache hit served in Vientiane: {hit}"

    # Same region + venue should hit
    hit = cache_service.check_cache(
        "What temples should I visit?",
        geo_region="dubai_uae",
        venue_name="Burj Khalifa",
    )
    assert hit is not None, "Same-region cache miss"
    assert "Jumeirah Mosque" in hit[0]


def test_cache_different_venue_same_region_misses():
    """Even within the same region, different venue context must not collide."""
    cache_service.clear_all()

    cache_service.store_response(
        "Is it open now?",
        "Burj Khalifa is open 24/7.",
        geo_region="dubai_uae",
        venue_name="Burj Khalifa",
    )

    hit = cache_service.check_cache(
        "Is it open now?",
        geo_region="dubai_uae",
        venue_name="Dubai Mall",
    )
    assert hit is None, f"Different-venue cache collision: {hit}"


# ------------------------------------------------------------------
# Blocker 4: Behavioral warnings test (not source-file read)
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_warnings_in_list_not_in_message_text():
    """process_event must return schedule_warnings as a structured
    list AND the response.message must NOT contain 'Heads up:'."""
    from agents.state_machine import state_machine

    trip = _laos_corridor_trip()
    # Manually add a warning-triggering node (outside opening hours)
    trip.nodes.append(
        TripNode(
            node_id="late",
            venue_name="Morning Market",
            venue_id="morning_mkt",
            duration_minutes=60,
            scheduled_start=datetime(2026, 10, 7, 13, 0, tzinfo=timezone.utc),
            is_locked=False,
            status=NodeStatus.PENDING,
            opening_hours="08:00-12:00",
            geo_region="vientiane_laos",
        )
    )
    result = await state_machine.process_event(
        trip_state=trip,
        event_type=EventType.ASK_INFO.value,
        message="tell me about this market",
        target_node_id="late",
    )
    # Response text must not contain warning concatenation
    assert "Heads up:" not in result["response"]
    # schedule_warnings is the structured list (may or may not have
    # warnings depending on ASK_INFO path, but must be a list)
    assert isinstance(result["schedule_warnings"], list)


# ------------------------------------------------------------------
# Blocker 5: _next_eligible_pending skips completed/elapsed
# ------------------------------------------------------------------


def test_next_eligible_skips_completed():
    from agents.state_machine import _next_eligible_pending

    now = datetime(2026, 10, 7, 6, 0, tzinfo=timezone.utc)
    trip = _laos_corridor_trip()
    # v2 (Ban Anou) is PENDING but elapsed (Oct 6 11:00Z + 90min = Oct 6 12:30Z < now)
    # lp1 is our current; next should be lp2, not v2
    current = trip.nodes[2]  # lp1
    result = _next_eligible_pending(trip.nodes, current, now)
    assert result is not None
    assert result.node_id == "lp2"


def test_next_eligible_returns_none_at_end():
    from agents.state_machine import _next_eligible_pending

    now = datetime(2026, 10, 8, 6, 0, tzinfo=timezone.utc)
    trip = _laos_corridor_trip()
    current = trip.nodes[3]  # lp2 (last)
    result = _next_eligible_pending(trip.nodes, current, now)
    assert result is None


# ------------------------------------------------------------------
# Blocker 7: process_event integration -- context for Oct 7 LP
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_event_captures_luang_prabang_context():
    """Run process_event for an ASK_INFO at Oct 7 06:00Z on the
    Laos corridor.  The context passed to generate_info_response
    must have geo_region=luang_prabang_laos and venue_name=Wat Xieng Thong,
    NOT vientiane_laos or Dubai."""
    from agents.state_machine import state_machine

    captured = {}

    async def _capture_info(message, context=None):
        captured.update(context or {})
        return "Mocked LLM response about Luang Prabang temples."

    trip = _laos_corridor_trip()

    with (
        patch("config.settings.settings.litellm_api_key", "fake-key"),
        patch(
            "services.llm_service.llm_service.generate_info_response",
            new_callable=AsyncMock,
            side_effect=_capture_info,
        ),
    ):
        await state_machine.process_event(
            trip_state=trip,
            event_type=EventType.ASK_INFO.value,
            message="What temples should I visit here?",
            now_utc=datetime(2026, 10, 7, 6, 0, tzinfo=timezone.utc),
        )

    assert captured.get("geo_region") == "luang_prabang_laos", (
        f"Expected luang_prabang_laos, got {captured.get('geo_region')}"
    )
    assert captured.get("venue_name") == "Wat Xieng Thong", (
        f"Expected Wat Xieng Thong, got {captured.get('venue_name')}"
    )
    assert "dubai" not in captured.get("geo_region", "").lower()
    assert "vientiane" not in captured.get("geo_region", "").lower()


@pytest.mark.asyncio
async def test_process_event_fallback_preserves_luang_prabang_on_llm_failure():
    """When the LLM fails on the LIGHT path, the router_agent fallback
    must still use Luang Prabang context, not Vientiane or Dubai."""
    from agents.state_machine import state_machine

    captured_ctx = {}

    def _capture_router(message, routing_tier, context=None):
        captured_ctx.update(context or {})
        return "Canned fallback response."

    trip = _laos_corridor_trip()

    with (
        patch("config.settings.settings.litellm_api_key", "fake-key"),
        patch(
            "services.llm_service.llm_service.generate_info_response",
            new_callable=AsyncMock,
            side_effect=RuntimeError("timeout"),
        ),
        patch(
            "agents.router_agent.router_agent.generate_response",
            side_effect=_capture_router,
        ),
    ):
        await state_machine.process_event(
            trip_state=trip,
            event_type=EventType.ASK_INFO.value,
            message="What temples should I visit?",
            now_utc=datetime(2026, 10, 7, 6, 0, tzinfo=timezone.utc),
        )

    assert captured_ctx.get("geo_region") == "luang_prabang_laos", (
        f"Expected luang_prabang_laos, got {captured_ctx.get('geo_region')}"
    )
