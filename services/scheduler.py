"""Travel Buddy - Itinerary Scheduler.

Forward-pass scheduler that keeps a live itinerary self-consistent after an
edit (cancel / swap / add / reroute):

  * LOCKED nodes are fixed anchors -- their reserved start time never moves.
  * Non-locked nodes keep their planned start unless inter-venue transit makes
    that infeasible, in which case they are pushed later.
  * Transit time between consecutive active stops uses the deterministic
    walking_minutes helper (SPEC-41 A3b). No random, no clock, no Maps API.
  * Each node venue opening hours are re-checked at its (possibly shifted)
    time.
  * A HARD conflict is flagged when a locked reservation can no longer be
    reached in time given the preceding activities + transit.
  * CANCEL FIX (SPEC-29): Skipped nodes remain at their original index and
    time. They do not participate in forward scheduling but are not moved to
    the bottom of the list.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import List, Optional, Set

from models.schemas import TripNode, NodeStatus
from services.destination_tz import destination_tz as _dest_tz
from services.opening_hours import HoursResult, hours_for_slot
from services.transit import walking_minutes


@dataclass
class ScheduleResult:
    nodes: List[TripNode]
    warnings: List[str] = field(default_factory=list)
    has_hard_conflict: bool = False


def _has_coords(node: TripNode) -> bool:
    return node.lat is not None and node.lng is not None


def _same_region_and_local_day(a: TripNode, b: TripNode) -> bool:
    """True when both nodes share geo_region AND destination-local calendar date.

    Cross-city or cross-day transitions are NOT walking transfers; the scheduler
    must preserve the next node's planned start instead of pushing it.
    """
    a_region = getattr(a, "geo_region", None)
    b_region = getattr(b, "geo_region", None)
    if not a_region or not b_region or a_region != b_region:
        return False
    tz = _dest_tz(a_region)
    if tz is None:
        return a.scheduled_start.date() == b.scheduled_start.date()
    return a.scheduled_start.astimezone(tz).date() == b.scheduled_start.astimezone(tz).date()


def _is_background_anchor(node: TripNode) -> bool:
    """True for bookings that occupy a calendar slot but should not push
    later activities (e.g. multi-night hotels).  Flights, trains and tours
    still occupy the timeline."""
    return node.node_kind == "booking" and node.booking_type == "hotel"


def reschedule_and_validate(
    nodes: List[TripNode],
    mutated_node_ids: Optional[Set[str]] = None,
) -> ScheduleResult:
    """Recompute start times preserving original positions.

    Skipped nodes stay at their original index/time (cancel correctness).
    Active nodes are forward-scheduled around them.

    When *mutated_node_ids* is given, hours checks apply to those nodes
    **and** any downstream node whose ``scheduled_start`` was shifted.
    CLOSED on a checked node sets ``has_hard_conflict`` -- the circuit
    breaker should try the next candidate or refuse.
    """
    warnings: List[str] = []
    has_hard_conflict = False

    # Snapshot original start times to detect shifted nodes.
    original_starts = {n.node_id: n.scheduled_start for n in nodes}

    prev_active = None
    prev_active_end = None

    for node in nodes:
        if node.status == NodeStatus.SKIPPED:
            continue

        transit_min = 0
        if (
            prev_active is not None
            and _same_region_and_local_day(prev_active, node)
            and _has_coords(prev_active)
            and _has_coords(node)
        ):
            transit_min = walking_minutes(prev_active.lat, prev_active.lng, node.lat, node.lng)

        earliest = prev_active_end + timedelta(minutes=transit_min) if prev_active_end else None

        if node.is_locked:
            if earliest is not None and earliest > node.scheduled_start:
                has_hard_conflict = True
            start = node.scheduled_start
        else:
            if earliest is not None and earliest > node.scheduled_start:
                start = earliest
            else:
                start = node.scheduled_start
            node.scheduled_start = start

        # Hours check: mutated node, shifted downstream, or unscoped.
        # Booking nodes (flights, hotels, trains, tours) are locked calendar
        # anchors without venue opening hours -- skip hours evaluation.
        _is_booking = getattr(node, "node_kind", "activity") == "booking"
        _is_shifted = node.scheduled_start != original_starts.get(node.node_id)
        _should_check = not _is_booking and (
            mutated_node_ids is None or node.node_id in mutated_node_ids or _is_shifted
        )
        if _should_check:
            structured = getattr(node, "opening_hours_structured", None)
            geo = getattr(node, "geo_region", None)
            hr = hours_for_slot(structured, start, node.duration_minutes, geo)
            if hr == HoursResult.CLOSED:
                has_hard_conflict = True
                warnings.append(
                    f"'{node.venue_name}' is closed at its scheduled time. Consider swapping it."
                )
            elif hr == HoursResult.UNKNOWN:
                warnings.append(
                    f"Opening hours for '{node.venue_name}' are unknown; verify locally."
                )

        prev_active = node
        prev_active_end = (
            start
            if _is_background_anchor(node)
            else start + timedelta(minutes=node.duration_minutes)
        )

    return ScheduleResult(
        nodes=nodes,
        warnings=warnings,
        has_hard_conflict=has_hard_conflict,
    )
