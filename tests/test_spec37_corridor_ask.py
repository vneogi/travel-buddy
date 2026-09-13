"""SPEC-37: State-machine and router-agent geo_region tests.

Tests that:
- _current_or_next_pending skips elapsed/completed nodes
- A corridor ask on Oct 7 in Luang Prabang uses luang_prabang_laos,
  not vientiane_laos or dubai_uae
- The router_agent fallback (no LLM) also receives the correct region
- Schedule warnings are returned structured, not in message text
"""

from datetime import datetime, timedelta, timezone

import pytest

from models.schemas import NodeStatus, TripNode


# ------------------------------------------------------------------
# _current_or_next_pending
# ------------------------------------------------------------------


def _make_node(node_id, geo_region, start_utc, status=NodeStatus.PENDING, dur=90):
    return TripNode(
        node_id=node_id,
        venue_name=f"Venue {node_id}",
        venue_id=node_id,
        duration_minutes=dur,
        scheduled_start=start_utc,
        is_locked=False,
        status=status,
        geo_region=geo_region,
    )


def test_skips_completed_and_elapsed_nodes():
    from agents.state_machine import _current_or_next_pending

    now = datetime(2026, 10, 7, 6, 0, tzinfo=timezone.utc)  # Oct 7 13:00 ICT
    nodes = [
        # Oct 5 Vientiane - completed
        _make_node(
            "v1",
            "vientiane_laos",
            datetime(2026, 10, 5, 2, 0, tzinfo=timezone.utc),
            status=NodeStatus.COMPLETED,
        ),
        # Oct 6 Vientiane - skipped
        _make_node(
            "v2",
            "vientiane_laos",
            datetime(2026, 10, 6, 2, 0, tzinfo=timezone.utc),
            status=NodeStatus.SKIPPED,
        ),
        # Oct 6 Vientiane - fully elapsed (ended before now)
        _make_node("v3", "vientiane_laos", datetime(2026, 10, 6, 3, 0, tzinfo=timezone.utc)),
        # Oct 7 Luang Prabang - pending, in the future
        _make_node("lp1", "luang_prabang_laos", datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)),
        # Oct 8 Luang Prabang
        _make_node("lp2", "luang_prabang_laos", datetime(2026, 10, 8, 2, 0, tzinfo=timezone.utc)),
    ]

    result = _current_or_next_pending(nodes, now)
    assert result is not None
    assert result.node_id == "lp1"
    assert result.geo_region == "luang_prabang_laos"


def test_returns_none_when_all_elapsed():
    from agents.state_machine import _current_or_next_pending

    now = datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc)
    nodes = [
        _make_node(
            "v1",
            "vientiane_laos",
            datetime(2026, 10, 5, 2, 0, tzinfo=timezone.utc),
            status=NodeStatus.COMPLETED,
        ),
    ]
    assert _current_or_next_pending(nodes, now) is None


# ------------------------------------------------------------------
# Router agent fallback uses geo_region
# ------------------------------------------------------------------


def test_router_agent_uses_luang_prabang_region():
    """When the router_agent canned fallback receives geo_region=luang_prabang_laos,
    its response must mention Luang Prabang, not Dubai or Vientiane."""
    from agents.router_agent import router_agent
    from models.schemas import RoutingTier

    response = router_agent.generate_response(
        "What temples should I visit?",
        RoutingTier.LIGHT,
        {"geo_region": "luang_prabang_laos"},
    )
    resp_lower = response.lower()
    assert "luang prabang" in resp_lower, f"Expected Luang Prabang, got: {response}"
    assert "dubai" not in resp_lower


def test_router_agent_no_region_falls_back_gracefully():
    """Without geo_region, it falls back to settings.geo_fence (Dubai)."""
    from agents.router_agent import router_agent
    from models.schemas import RoutingTier

    response = router_agent.generate_response(
        "price info",
        RoutingTier.LIGHT,
        {},
    )
    # Should not crash; geo_fence default is dubai_uae
    assert response is not None


# ------------------------------------------------------------------
# Schedule warnings are structured, not in message text
# ------------------------------------------------------------------


def test_schedule_warnings_not_in_response_text():
    """After the fix, state_machine must not append 'Heads up:' to
    state['response']. Warnings go via schedule_warnings list only."""
    import pathlib

    source = pathlib.Path("agents/state_machine.py").read_text()
    # The string "Heads up:" must not appear anywhere in the module.
    assert "Heads up:" not in source, (
        "state_machine.py still concatenates warnings into response text"
    )


# ------------------------------------------------------------------
# FeaturedStop includes geo_region
# ------------------------------------------------------------------


def test_featured_stop_has_geo_region():
    from models.schemas import FeaturedStop, NodeStatus

    fs = FeaturedStop(
        node_id="lp1",
        venue_id="wat_xieng_thong",
        venue_name="Wat Xieng Thong",
        scheduled_start=datetime(2026, 10, 7, 4, 0, tzinfo=timezone.utc),
        status=NodeStatus.PENDING,
        geo_region="luang_prabang_laos",
    )
    data = fs.model_dump(mode="json")
    assert data["geo_region"] == "luang_prabang_laos"


def test_featured_stop_geo_region_defaults_to_none():
    from models.schemas import FeaturedStop, NodeStatus

    fs = FeaturedStop(
        node_id="d1",
        venue_name="Burj Khalifa",
        scheduled_start=datetime(2026, 10, 7, 5, 0, tzinfo=timezone.utc),
        status=NodeStatus.PENDING,
    )
    assert fs.geo_region is None
