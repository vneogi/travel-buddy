"""SPEC-37: Destination timezone tests (ZoneInfo + config.REGIONS).

Proves that a Vientiane 09:00 local node stored as 02:00Z is
displayed and validated as 09:00, regardless of the server or
device timezone.
"""

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from services.destination_tz import destination_tz, to_destination_local


# ------------------------------------------------------------------
# Unit: destination_tz resolver
# ------------------------------------------------------------------


def test_vientiane_resolves_to_asia_vientiane():
    tz = destination_tz("vientiane_laos")
    assert tz is not None
    assert str(tz) == "Asia/Vientiane"


def test_dubai_resolves_to_asia_dubai():
    tz = destination_tz("dubai_uae")
    assert tz is not None
    assert str(tz) == "Asia/Dubai"


def test_unknown_region_returns_none():
    assert destination_tz("atlantis") is None
    assert destination_tz(None) is None


# ------------------------------------------------------------------
# Conversion: UTC -> destination-local
# ------------------------------------------------------------------


def test_vientiane_0200z_renders_0900():
    utc_dt = datetime(2026, 9, 15, 2, 0, tzinfo=timezone.utc)
    local = to_destination_local(utc_dt, "vientiane_laos")
    assert local.hour == 9
    assert local.minute == 0


def test_dubai_0500z_renders_0900():
    utc_dt = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    local = to_destination_local(utc_dt, "dubai_uae")
    assert local.hour == 9
    assert local.minute == 0


def test_naive_utc_is_handled():
    """A naive datetime (no tzinfo) should still convert correctly."""
    naive = datetime(2026, 9, 15, 2, 0)
    local = to_destination_local(naive, "vientiane_laos")
    assert local.hour == 9


def test_vientiane_0200z_displays_0900_with_kolkata_device():
    """Even when the process TZ is Asia/Kolkata (IST +5:30),
    destination-local must still be ICT +7 = 09:00."""
    old_tz = os.environ.get("TZ")
    try:
        os.environ["TZ"] = "Asia/Kolkata"
        # Python caches TZ on import, but ZoneInfo is unaffected
        utc_dt = datetime(2026, 9, 15, 2, 0, tzinfo=timezone.utc)
        local = to_destination_local(utc_dt, "vientiane_laos")
        assert local.hour == 9, f"Expected 09:00 ICT, got {local.hour}:{local.minute}"
    finally:
        if old_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old_tz


# ------------------------------------------------------------------
# Scheduler integration: opening-hours with destination-local
# ------------------------------------------------------------------


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
    assert len(result.warnings) == 0, f"Got: {result.warnings}"


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
