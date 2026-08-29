"""Travel Buddy - Itinerary Scheduler.

Forward-pass scheduler that keeps a live itinerary self-consistent after an
edit (cancel / swap / add / reroute):

  * LOCKED nodes are fixed anchors -- their reserved start time never moves.
  * Non-locked nodes keep their planned start unless inter-venue transit makes
    that infeasible, in which case they are pushed later.
  * Transit time between consecutive stops is added from the Distance-Matrix
    estimate (maps_service) whenever both stops have coordinates.
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
from typing import List

from models.schemas import TripNode, NodeStatus
from services.maps_service import maps_service


@dataclass
class ScheduleResult:
    nodes: List[TripNode]
    warnings: List[str] = field(default_factory=list)
    has_hard_conflict: bool = False


def _has_coords(node: TripNode) -> bool:
    return node.lat is not None and node.lng is not None


def _is_background_anchor(node: TripNode) -> bool:
    """True for bookings that occupy a calendar slot but should not push
    later activities (e.g. multi-night hotels).  Flights, trains and tours
    still occupy the timeline."""
    return node.node_kind == "booking" and node.booking_type == "hotel"


def reschedule_and_validate(nodes: List[TripNode]) -> ScheduleResult:
    """Recompute start times preserving original positions.

    Skipped nodes stay at their original index/time (cancel correctness).
    Active nodes are forward-scheduled around them.
    """
    warnings: List[str] = []
    has_hard_conflict = False

    # Process in original order, skipping over SKIPPED nodes for transit calc
    prev_active = None
    prev_active_end = None

    for node in nodes:
        if node.status == NodeStatus.SKIPPED:
            # Skipped nodes keep their original position and time
            continue

        transit_min = 0
        if prev_active is not None and _has_coords(prev_active) and _has_coords(node):
            transit_min = maps_service.get_transit_time(
                prev_active.lat, prev_active.lng, node.lat, node.lng
            )["duration_minutes"]

        earliest = prev_active_end + timedelta(minutes=transit_min) if prev_active_end else None

        if node.is_locked:
            if earliest is not None and earliest > node.scheduled_start:
                has_hard_conflict = True
                # Internal feasibility flag only. Synthetic transit claims
                # (minutes, distance, "unreachable") must never reach user copy.
            start = node.scheduled_start  # anchor stays fixed
        else:
            if earliest is not None and earliest > node.scheduled_start:
                start = earliest
            else:
                start = node.scheduled_start
            node.scheduled_start = start

        # Opening-hours re-validation (hedged per SPEC-29 D7)
        if node.opening_hours:
            end_dt = start + timedelta(minutes=node.duration_minutes)
            if not (
                maps_service.check_venue_open(node.opening_hours, start)
                and maps_service.check_venue_open(node.opening_hours, end_dt)
            ):
                warnings.append(
                    f"Based on saved venue hours, '{node.venue_name}' may be "
                    f"closed at its scheduled time "
                    f"({start.strftime('%H:%M')}). Verify locally."
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
