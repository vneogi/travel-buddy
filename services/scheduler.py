"""Travel Buddy - Itinerary Scheduler.

Forward-pass scheduler that keeps a live itinerary self-consistent after an
edit (cancel / swap / add / reroute):

  * LOCKED nodes are fixed anchors -- their reserved start time never moves.
  * Non-locked nodes keep their planned start unless inter-venue transit makes
    that infeasible, in which case they're pushed later (minimal perturbation --
    intentional free time/pacing is preserved; a cancel frees its slot without
    compacting the rest of the day).
  * Transit time between consecutive stops is added from the Distance-Matrix
    estimate (maps_service) whenever both stops have coordinates.
  * Each node's venue opening hours are re-checked at its (possibly shifted)
    time.
  * A HARD conflict is flagged when a locked reservation can no longer be
    reached in time given the preceding activities + transit. The state machine
    uses that signal to try a different candidate (circuit breaker).
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


def reschedule_and_validate(nodes: List[TripNode]) -> ScheduleResult:
    """Recompute start times in list order and validate. See module docstring."""
    warnings: List[str] = []
    has_hard_conflict = False

    active = [n for n in nodes if n.status != NodeStatus.SKIPPED]
    skipped = [n for n in nodes if n.status == NodeStatus.SKIPPED]

    prev = None
    prev_end = None
    for node in active:
        transit_min = 0
        if prev is not None and _has_coords(prev) and _has_coords(node):
            transit_min = maps_service.get_transit_time(prev.lat, prev.lng, node.lat, node.lng)[
                "duration_minutes"
            ]

        earliest = prev_end + timedelta(minutes=transit_min) if prev_end else None

        if node.is_locked:
            if earliest is not None and earliest > node.scheduled_start:
                has_hard_conflict = True
                over = int((earliest - node.scheduled_start).total_seconds() // 60)
                warnings.append(
                    f"Locked '{node.venue_name}' at "
                    f"{node.scheduled_start.strftime('%H:%M')} is unreachable \u2014 "
                    f"the previous stop + {transit_min} min transit runs {over} min over."
                )
            start = node.scheduled_start  # anchor stays fixed
        else:
            # Keep the planned time unless transit pushes it later.
            if earliest is not None and earliest > node.scheduled_start:
                start = earliest
            else:
                start = node.scheduled_start
            node.scheduled_start = start

        # Opening-hours re-validation at the (possibly shifted) time.
        if node.opening_hours:
            end_dt = start + timedelta(minutes=node.duration_minutes)
            if not (
                maps_service.check_venue_open(node.opening_hours, start)
                and maps_service.check_venue_open(node.opening_hours, end_dt)
            ):
                warnings.append(
                    f"'{node.venue_name}' may be closed at its scheduled time "
                    f"({start.strftime('%H:%M')}, hours {node.opening_hours})."
                )

        prev = node
        prev_end = start + timedelta(minutes=node.duration_minutes)

    # Skipped nodes are kept (unchanged) so callers still see them.
    return ScheduleResult(
        nodes=active + skipped,
        warnings=warnings,
        has_hard_conflict=has_hard_conflict,
    )
