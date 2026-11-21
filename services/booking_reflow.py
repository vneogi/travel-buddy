"""SPEC-10 slice 1: create-then-book HITL reflow (proposal and apply).

Bookings define what is possible on a day; intent may only choose among the
remaining slots. This module thins existing flexible nodes only. It never
calls pack_day, never searches the catalog, and never invents venues. The
booking itself is saved immediately by add/edit; the thinning persists only
after the traveller confirms an intent (confirm_booking_reflow).

Affected days for one booking (one entry per local date, this booking only):

- flight / train / tour: the destination-local date of scheduled_start;
- hotel: the check-in local date (remaining at the check-in hour), and the
  checkout local date only when checkout is before 12:00 and no other hotel
  checks in on that date (chained stay). Middle nights are never listed.

A day is listed only when it has flexible nodes outside its conservative
slots. Nothing here logs node or place names.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from models.schemas import NodeStatus, TripNode
from services.booking_constraints import (
    _ensure_aware,
    _local_date_of,
    find_covering_hotel,
    is_hotel_booking,
)
from services.day_slots import SLOT_ORDER, compute_remaining_slots
from services.destination_tz import destination_tz

INTENT_CONSERVATIVE = "conservative"
INTENT_RESTORE_EVENING = "restore_evening"
INTENT_RESTORE_MORNING = "restore_morning"
INTENT_KEEP_OPEN = "keep_open"
BOOKING_REFLOW_INTENTS = (
    INTENT_CONSERVATIVE,
    INTENT_RESTORE_EVENING,
    INTENT_RESTORE_MORNING,
    INTENT_KEEP_OPEN,
)

KIND_ARRIVAL = "arrival"  # late arrival or hotel check-in at 14:00 or later
KIND_MORNING = "morning"  # hotel checkout morning or early departure
KIND_OTHER = "other"

_EVENING_SLOTS = ("afternoon_evening_tour", "dinner")
_MORNING_SLOT = "morning_tour"
_TRAVEL_TYPES = ("flight", "train")


@dataclass(frozen=True)
class ReflowDay:
    local_date: date
    kind: str
    conservative: tuple


def _local(dt: datetime, region: Optional[str]) -> datetime:
    aware = _ensure_aware(dt)
    tz = destination_tz(region)
    return aware.astimezone(tz) if tz is not None else aware


def _node_local_date(node: TripNode, fallback_region: Optional[str]) -> date:
    return _local_date_of(node.scheduled_start, node.geo_region or fallback_region)


def _is_flexible(node: TripNode) -> bool:
    return (
        not node.is_locked
        and node.node_kind != "booking"
        and node.status not in (NodeStatus.SKIPPED, NodeStatus.COMPLETED)
        and bool(node.slot_name)
    )


def _chained_checkin(
    booking: TripNode, nodes: List[TripNode], day: date, region: Optional[str]
) -> bool:
    """True when another hotel booking checks in on *day* (chained stay)."""
    for node in nodes:
        if node.node_id == booking.node_id or not is_hotel_booking(node):
            continue
        if node.status == NodeStatus.SKIPPED:
            continue
        if _node_local_date(node, region) == day:
            return True
    return False


def affected_days(
    booking: TripNode, nodes: List[TripNode], trip_region: Optional[str]
) -> List[ReflowDay]:
    """Candidate days for this booking, before the non-empty extras filter."""
    region = booking.geo_region or trip_region
    start = _local(booking.scheduled_start, region)
    btype = booking.booking_type
    if btype == "hotel":
        # Check-in day: the arrival-hour rows of the table. has_hotel=False so
        # a check-in before noon is not read as the checkout row.
        hour = start.hour
        days = [
            ReflowDay(
                start.date(),
                KIND_ARRIVAL if hour >= 14 else KIND_OTHER,
                tuple(compute_remaining_slots(hour, "hotel", False)),
            )
        ]
        checkout = _local(
            booking.scheduled_start + timedelta(minutes=booking.duration_minutes), region
        )
        if (
            checkout.hour < 12
            and checkout.date() != start.date()
            and not _chained_checkin(booking, nodes, checkout.date(), trip_region)
        ):
            days.append(
                ReflowDay(
                    checkout.date(),
                    KIND_MORNING,
                    tuple(compute_remaining_slots(checkout.hour, "hotel", True)),
                )
            )
        return days

    hour = start.hour
    has_hotel = find_covering_hotel(nodes, region, start.date()) is not None
    if btype in _TRAVEL_TYPES and hour >= 14:
        kind = KIND_ARRIVAL
    elif btype in _TRAVEL_TYPES and hour < 12:
        kind = KIND_MORNING
    else:
        kind = KIND_OTHER
    return [ReflowDay(start.date(), kind, tuple(compute_remaining_slots(hour, btype, has_hotel)))]


def remaining_for(intent: str, day: ReflowDay) -> tuple:
    """Remaining slots on *day* for *intent* (section 3 table, Option A scope)."""
    if intent == INTENT_CONSERVATIVE:
        return day.conservative
    if intent == INTENT_RESTORE_EVENING:
        return _EVENING_SLOTS if day.kind == KIND_ARRIVAL else day.conservative
    if intent == INTENT_RESTORE_MORNING:
        if day.kind != KIND_MORNING or _MORNING_SLOT in day.conservative:
            return day.conservative
        wanted = set(day.conservative) | {_MORNING_SLOT}
        return tuple(s for s in SLOT_ORDER if s in wanted)
    if intent == INTENT_KEEP_OPEN:
        return ()
    raise ValueError("unknown booking reflow intent")


def _flexible_on(day: ReflowDay, nodes: List[TripNode], region: Optional[str]) -> List[TripNode]:
    return [n for n in nodes if _is_flexible(n) and _node_local_date(n, region) == day.local_date]


def _listed_days(booking: TripNode, nodes: List[TripNode], trip_region: Optional[str]):
    """(day, extra nodes) for days whose conservative set squeezes a node."""
    listed = []
    seen = set()
    for day in affected_days(booking, nodes, trip_region):
        if day.local_date in seen:
            continue
        seen.add(day.local_date)
        extra = [
            n for n in _flexible_on(day, nodes, trip_region) if n.slot_name not in day.conservative
        ]
        if extra:
            listed.append((day, extra))
    return listed


def _find_booking(nodes: List[TripNode], booking_node_id: Optional[str]) -> Optional[TripNode]:
    for node in nodes:
        if node.node_id == booking_node_id and node.node_kind == "booking":
            return node
    return None


def build_booking_reflow(
    nodes: List[TripNode], booking_node_id: str, trip_region: Optional[str]
) -> Optional[Dict]:
    """Proposal DTO for this booking, or None when no flexible node is squeezed."""
    booking = _find_booking(nodes, booking_node_id)
    if booking is None or booking.status == NodeStatus.SKIPPED:
        return None
    listed = _listed_days(booking, nodes, trip_region)
    if not listed:
        return None
    kinds = {day.kind for day, _ in listed}
    intents = [INTENT_CONSERVATIVE]
    if KIND_ARRIVAL in kinds:
        intents.append(INTENT_RESTORE_EVENING)
    if KIND_MORNING in kinds:
        intents.append(INTENT_RESTORE_MORNING)
    intents.append(INTENT_KEEP_OPEN)
    return {
        "booking_node_id": booking.node_id,
        "intents": intents,
        "default_intent": INTENT_CONSERVATIVE,
        "days": [
            {
                "local_date": day.local_date.isoformat(),
                "conservative_slots": list(day.conservative),
                "extra_node_ids": [n.node_id for n in extra],
            }
            for day, extra in listed
        ],
    }


def apply_booking_reflow(
    nodes: List[TripNode], booking_node_id: str, intent: str, trip_region: Optional[str]
) -> List[str]:
    """Skip in place (same as unlocked cancel) every flexible node on a listed
    day whose slot is outside the intent's remaining set. Returns skipped ids.
    Idempotent: already-skipped nodes are not flexible and are never counted.
    """
    if intent not in BOOKING_REFLOW_INTENTS:
        raise ValueError("unknown booking reflow intent")
    booking = _find_booking(nodes, booking_node_id)
    if booking is None:
        return []
    listed = _listed_days(booking, nodes, trip_region)
    to_skip: List[TripNode] = []
    for day, _extra in listed:
        remaining = remaining_for(intent, day)
        to_skip.extend(
            n for n in _flexible_on(day, nodes, trip_region) if n.slot_name not in remaining
        )
    for node in to_skip:
        node.status = NodeStatus.SKIPPED
    return [n.node_id for n in to_skip]
