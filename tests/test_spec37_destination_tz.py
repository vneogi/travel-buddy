"""SPEC-37: Destination timezone tests.

Proves that a Vientiane 09:00 local node stored as 02:00Z is
displayed and validated as 09:00, regardless of the server or
device timezone.
"""

from datetime import datetime, timezone, timedelta

from services.destination_tz import (
    destination_offset,
    to_destination_local,
    REGION_OFFSETS,
)


def test_vientiane_offset_is_7():
    off = destination_offset("vientiane_laos")
    assert off == timedelta(hours=7)


def test_dubai_offset_is_4():
    off = destination_offset("dubai_uae")
    assert off == timedelta(hours=4)


def test_unknown_region_returns_none():
    assert destination_offset("atlantis") is None
    assert destination_offset(None) is None


def test_vientiane_0200z_renders_0900():
    """Backend stores Vientiane 09:00 as 02:00Z.
    to_destination_local must return 09:00."""
    utc_dt = datetime(2026, 9, 15, 2, 0, tzinfo=timezone.utc)
    local = to_destination_local(utc_dt, "vientiane_laos")
    assert local.hour == 9
    assert local.minute == 0


def test_dubai_0500z_renders_0900():
    utc_dt = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    local = to_destination_local(utc_dt, "dubai_uae")
    assert local.hour == 9
    assert local.minute == 0


def test_scheduler_opening_hours_uses_destination_tz():
    """A Vientiane venue open 08:00-22:00 with a 02:00Z start
    (= 09:00 ICT) must NOT trigger a warning."""
    from models.schemas import TripNode, NodeStatus
    from services.scheduler import reschedule_and_validate

    node = TripNode(
        node_id="n1",
        venue_name="Ban Anou Night Market",
        venue_id="ban_anou",
        duration_minutes=60,
        scheduled_start=datetime(2026, 9, 15, 2, 0, tzinfo=timezone.utc),
        is_locked=False,
        status=NodeStatus.PENDING,
        opening_hours="08:00-22:00",
        geo_region="vientiane_laos",
    )
    result = reschedule_and_validate([node])
    assert len(result.warnings) == 0, f"Should have no warnings, got: {result.warnings}"


def test_scheduler_warns_when_actually_closed():
    """A Vientiane venue open 08:00-17:00 with a 13:00Z start
    (= 20:00 ICT) IS outside hours and should warn."""
    from models.schemas import TripNode, NodeStatus
    from services.scheduler import reschedule_and_validate

    node = TripNode(
        node_id="n2",
        venue_name="Morning Market",
        venue_id="morning_mkt",
        duration_minutes=60,
        scheduled_start=datetime(2026, 9, 15, 13, 0, tzinfo=timezone.utc),
        is_locked=False,
        status=NodeStatus.PENDING,
        opening_hours="08:00-17:00",
        geo_region="vientiane_laos",
    )
    result = reschedule_and_validate([node])
    assert len(result.warnings) == 1
    assert "Morning Market" in result.warnings[0]
