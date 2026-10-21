"""SPEC-42 thin typed Move.

Moves one flexible itinerary node to another destination-local date and
named slot inside the trip span. Only that node's ``scheduled_start`` and
``slot_name`` change. Every predicate reuses production helpers:

* ``day_slots`` slot typing and whole-day tags
* ``catalog_itinerary`` slot floors and slot-band acceptance
* ``opening_hours`` next fitting start + ``hours_for_slot``
* ``transit.walking_minutes`` for flexible neighbours
* ``booking_constraints.fits_next_lock`` for the next locked non-hotel

No LLM, no venue search, no catalog write, no new table.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, List, Optional

from models.schemas import NodeStatus, TripNode, TripState
from services.day_slots import (
    SLOT_ORDER,
    has_matching_slot,
    is_whole_day_excursion,
)

MOVE_MODE = "move"

# Same local day-start the catalog packer uses (09:00 destination-local).
_DAY_START_HOUR = 9

_FOOD_SLOT_NAMES = frozenset({"lunch", "dinner"})
_ACTIVITY_SLOT_NAMES = frozenset({"morning_tour", "afternoon_evening_tour"})

_SLOT_LABELS = {
    "morning_tour": "morning",
    "lunch": "lunch",
    "afternoon_evening_tour": "afternoon",
    "dinner": "dinner",
}

REFUSAL_COPY = {
    "missing_target": "Choose an activity to move.",
    "invalid_mode": "That move request was not recognised. Nothing was changed.",
    "invalid_date": "Choose a valid date for this move.",
    "invalid_slot": "Choose morning, lunch, afternoon, or dinner.",
    "target_not_found": "That activity is no longer in this trip.",
    "locked_target": "Locked bookings cannot be moved.",
    "not_movable_status": "Completed or skipped activities cannot be moved.",
    "whole_day_excursion": "Whole-day excursions cannot be moved yet.",
    "slot_type_mismatch": ("Food stops go in lunch or dinner; sights go in morning or afternoon."),
    "unknown_venue_type": "I can't tell which slots this activity fits, so nothing was moved.",
    "outside_span": "That date is outside this trip.",
    "cross_city_date": "That date is in a different city. Moves stay in the same city.",
    "no_change": "That activity is already in that slot.",
    "slot_occupied": "That slot already has an activity. Nothing was moved.",
    "closed_hours": "It isn't open long enough in that slot. Nothing was moved.",
    "neighbour_unreachable": (
        "There isn't enough time to get there around the other stops that day."
    ),
    "next_lock_unreachable": (
        "Moving it there would put your next booking at risk. Nothing was moved."
    ),
}


@dataclass
class MoveResult:
    ok: bool
    code: str = ""
    message: str = ""
    nodes: List[TripNode] = field(default_factory=list)
    moved: Optional[TripNode] = None


def _refuse(code: str, nodes: List[TripNode]) -> MoveResult:
    return MoveResult(ok=False, code=code, message=REFUSAL_COPY[code], nodes=list(nodes))


def _finite(*vals: Any) -> bool:
    for v in vals:
        if v is None:
            return False
        try:
            if not math.isfinite(v):
                return False
        except TypeError:
            return False
    return True


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _region(node: TripNode, trip: TripState) -> str:
    return node.geo_region or trip.geo_region or ""


def _local_date(node: TripNode, trip: TripState) -> date:
    from services.destination_tz import destination_tz

    tz = destination_tz(_region(node, trip))
    start = _aware(node.scheduled_start)
    return (start.astimezone(tz) if tz is not None else start).date()


def _is_flexible(node: TripNode) -> bool:
    return not node.is_locked and (node.node_kind or "activity") != "booking"


def _is_hotel(node: TripNode) -> bool:
    return (node.node_kind or "") == "booking" and (node.booking_type or "") == "hotel"


def trip_span(trip: TripState) -> Optional[tuple[date, date]]:
    """Inclusive destination-local trip span (SPEC-42 rendering sources)."""
    cc = trip.creation_context
    if cc is not None and cc.start_date_local and cc.end_date_local:
        try:
            return (
                date.fromisoformat(cc.start_date_local),
                date.fromisoformat(cc.end_date_local),
            )
        except ValueError:
            pass
    if trip.segments:
        return (
            min(s.starts_on for s in trip.segments),
            max(s.ends_on for s in trip.segments),
        )
    if trip.nodes:
        dates = [_local_date(n, trip) for n in trip.nodes]
        return (min(dates), max(dates))
    return None


def _is_corridor(trip: TripState) -> bool:
    regions = {s.geo_region for s in trip.segments if s.geo_region}
    regions |= {n.geo_region for n in trip.nodes if n.geo_region}
    return len(regions) > 1


def _venue_profile(node: TripNode, db: Any) -> Optional[dict]:
    """Category + coords + hours for slot typing, from the catalog when known."""
    venue = None
    if node.venue_id and db is not None:
        try:
            venue = db.get_venue_by_id(node.venue_id)
        except Exception:  # pragma: no cover - defensive; catalog read only
            venue = None
    category = getattr(venue, "category", None) if venue is not None else None
    if not category:
        # No catalog row: infer the type from the slot the node already holds.
        if node.slot_name in _FOOD_SLOT_NAMES:
            category = "restaurant"
        elif node.slot_name in _ACTIVITY_SLOT_NAMES:
            category = "experience"
        else:
            return None
    structured = node.opening_hours_structured
    if structured is None and venue is not None:
        structured = getattr(venue, "opening_hours_structured", None)
    return {
        "category": category,
        "vibe_tags": list(node.vibe_tags or []),
        "lat": node.lat,
        "lng": node.lng,
        "opening_hours_structured": structured,
    }


def apply_move(
    trip: TripState,
    target_node_id: Optional[str],
    preferences: Optional[dict],
    db: Any = None,
) -> MoveResult:
    """Validate and apply one typed move. Never partially rewrites."""
    from services.booking_constraints import fits_next_lock
    from services.catalog_itinerary import _slot_accepts_start, _slot_floor_utc
    from services.destination_tz import destination_tz
    from services.opening_hours import HoursResult, hours_for_slot, next_slot_start
    from services.transit import walking_minutes

    nodes = list(trip.nodes)
    prefs = preferences or {}

    # --- payload shape ---------------------------------------------------
    if not target_node_id:
        return _refuse("missing_target", nodes)
    if prefs.get("mode") != MOVE_MODE:
        return _refuse("invalid_mode", nodes)
    raw_date = prefs.get("target_date")
    try:
        if not isinstance(raw_date, str) or len(raw_date) != 10:
            raise ValueError
        target_date = date.fromisoformat(raw_date)
    except ValueError:
        return _refuse("invalid_date", nodes)
    target_slot = prefs.get("target_slot")
    if target_slot not in SLOT_ORDER:
        return _refuse("invalid_slot", nodes)

    # 1. target exists
    node = next((n for n in nodes if n.node_id == target_node_id), None)
    if node is None:
        return _refuse("target_not_found", nodes)
    # 2. locked / booking
    if not _is_flexible(node):
        return _refuse("locked_target", nodes)
    # 3. status
    if node.status in (NodeStatus.COMPLETED, NodeStatus.SKIPPED):
        return _refuse("not_movable_status", nodes)
    # 4. whole-day excursion
    if is_whole_day_excursion({"vibe_tags": node.vibe_tags}):
        return _refuse("whole_day_excursion", nodes)
    # 5. slot type
    venue = _venue_profile(node, db)
    if venue is None:
        return _refuse("unknown_venue_type", nodes)
    if not has_matching_slot(venue, [target_slot]):
        return _refuse("slot_type_mismatch", nodes)

    # 6. span + region
    region = _region(node, trip)
    span = trip_span(trip)
    if span is None or not (span[0] <= target_date <= span[1]):
        return _refuse("outside_span", nodes)
    if _is_corridor(trip):
        same_city = any(
            _region(n, trip) == region and _local_date(n, trip) == target_date for n in nodes
        )
        if not same_city:
            return _refuse("cross_city_date", nodes)

    # 11. no-op
    if _local_date(node, trip) == target_date and node.slot_name == target_slot:
        return _refuse("no_change", nodes)

    others = [n for n in nodes if n.node_id != node.node_id]
    day_others = [
        n
        for n in others
        if _region(n, trip) == region
        and _local_date(n, trip) == target_date
        and n.status != NodeStatus.SKIPPED
    ]

    # 7. occupancy
    if any(_is_flexible(n) and n.slot_name == target_slot for n in day_others):
        return _refuse("slot_occupied", nodes)

    # 8. planned start from the slot floor, then hours
    tz = destination_tz(region)
    if tz is not None:
        local_day = datetime(
            target_date.year, target_date.month, target_date.day, _DAY_START_HOUR, tzinfo=tz
        )
    else:
        local_day = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            _DAY_START_HOUR,
            tzinfo=timezone.utc,
        )
    floor = _slot_floor_utc(target_slot, local_day, tz)
    earliest = max(_aware(floor), local_day.astimezone(timezone.utc))
    dwell = node.duration_minutes

    # 9a. walking from the previous stop on that day (hotels are anchors)
    stops = sorted(
        (n for n in day_others if not _is_hotel(n)),
        key=lambda n: _aware(n.scheduled_start),
    )
    prev = None
    for n in stops:
        if _aware(n.scheduled_start) <= earliest:
            prev = n
    if prev is not None:
        prev_end = _aware(prev.scheduled_start) + timedelta(minutes=prev.duration_minutes)
        if _finite(prev.lat, prev.lng, node.lat, node.lng):
            prev_end += timedelta(minutes=walking_minutes(prev.lat, prev.lng, node.lat, node.lng))
        earliest = max(earliest, prev_end)

    structured = venue.get("opening_hours_structured")
    start = next_slot_start(structured, earliest, dwell, region, local_day)
    if start is None or not _slot_accepts_start(target_slot, start, region):
        return _refuse("closed_hours", nodes)
    if hours_for_slot(structured, start, dwell, region) == HoursResult.CLOSED:
        return _refuse("closed_hours", nodes)
    end = start + timedelta(minutes=dwell)

    # 9b. next flexible stop must still be reachable (locks: rule 10)
    nxt = next(
        (n for n in stops if _aware(n.scheduled_start) >= start and n is not prev),
        None,
    )
    if nxt is not None and _is_flexible(nxt):
        arrive = end
        if _finite(nxt.lat, nxt.lng, node.lat, node.lng):
            arrive += timedelta(minutes=walking_minutes(node.lat, node.lng, nxt.lat, nxt.lng))
        if arrive > _aware(nxt.scheduled_start):
            return _refuse("neighbour_unreachable", nodes)

    # 10. next locked non-hotel on/after placement (shared helper)
    locks = sorted(
        (
            n
            for n in others
            if not _is_flexible(n) and not _is_hotel(n) and _aware(n.scheduled_start) >= start
        ),
        key=lambda n: _aware(n.scheduled_start),
    )
    next_lock = locks[0] if locks else None
    if not fits_next_lock(venue, start, dwell, next_lock, region):
        return _refuse("next_lock_unreachable", nodes)

    moved = node.model_copy(update={"scheduled_start": start, "slot_name": target_slot})
    new_nodes = [moved if n.node_id == node.node_id else n for n in nodes]
    new_nodes.sort(key=lambda n: _aware(n.scheduled_start))

    src = f"{_local_date(node, trip).isoformat()} {_SLOT_LABELS.get(node.slot_name or '', 'slot')}"
    dst = f"{target_date.isoformat()} {_SLOT_LABELS[target_slot]}"
    return MoveResult(
        ok=True,
        message=f"Moved {node.venue_name} from {src} to {dst}.",
        nodes=new_nodes,
        moved=moved,
    )
