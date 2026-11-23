"""SPEC-42 trip-private uncatalogued Add (``add_activity`` + ``mode=uncatalogued_add``).

Confirm-only. Inserts one trip-private ``TripNode`` on an empty-day slot,
reusing the catalog direct-add day context (region, occupancy) and timing
(slot floor, previous dwell + walk, neighbour reachability, ``fits_next_lock``).
Never writes the shared catalog, never invents opening hours, never mints a
catalog ``venue_id``. The catalog is read only to refuse a name collision.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, List, Optional

from models.schemas import NodeStatus, TripNode, TripState
from services.day_slots import _WHOLE_DAY_CONSUMED, SLOT_ORDER
from services.direct_add_service import day_context, place_timing
from services.move_service import _aware

UNCATALOGUED_ADD_MODE = "uncatalogued_add"
TRIP_PRIVATE = "trip_private"
NAME_MIN, NAME_MAX = 2, 80
DWELL_MIN, DWELL_MAX = 15, 240

REFUSAL_COPY: Dict[str, str] = {
    "invalid_mode": "That add request was not recognised. Nothing was changed.",
    "invalid_name": "Give the place a name between 2 and 80 characters.",
    "invalid_dwell": "Choose how long you plan to stay (15 to 240 minutes).",
    "invalid_coords": "That location could not be used. Nothing was changed.",
    "invalid_slot": "Choose morning, lunch, afternoon, or dinner.",
    "invalid_date": "That date isn't part of this trip.",
    "occupied": "That slot already has an activity on this day.",
    "duplicate": "A place with that name is already on this day.",
    "catalog_match": "That place is in the catalog. Pick it from the list instead.",
    "reachability": "It can't fit in that slot around your other plans that day.",
    "invalid_window": "Choose morning, afternoon, or whole day.",
    "locked_conflict": "A booking is already in that window.",
    "needs_review": "Adding this would skip other stops on that day.",
    "stale": "This day changed. Review again.",
}

# SPEC-42 unknown-time excursion windows (closed set). Dinner is never
# consumed. whole_day reuses the SPEC-41 whole-day set.
TIME_WINDOWS: Dict[str, tuple] = {
    "morning": ("morning_tour", "lunch"),
    "afternoon": ("afternoon_evening_tour",),
    "whole_day": tuple(s for s in SLOT_ORDER if s in _WHOLE_DAY_CONSUMED),
}
_WINDOW_LABELS = {"morning": "morning", "afternoon": "afternoon", "whole_day": "whole day"}

_SLOT_LABELS = {
    "morning_tour": "morning",
    "lunch": "lunch",
    "afternoon_evening_tour": "afternoon",
    "dinner": "dinner",
}


def normalize_name(name: str) -> str:
    return " ".join(name.split()).casefold()


def _clean_name(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    name = " ".join(raw.split())
    if not (NAME_MIN <= len(name) <= NAME_MAX):
        return None
    return name


def _clean_dwell(raw: Any) -> Optional[int]:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    if isinstance(raw, float) and (not math.isfinite(raw) or not raw.is_integer()):
        return None
    dwell = int(raw)
    return dwell if DWELL_MIN <= dwell <= DWELL_MAX else None


def _clean_coords(lat: Any, lng: Any) -> tuple[bool, Optional[float], Optional[float]]:
    if lat is None and lng is None:
        return True, None, None
    ok = all(
        not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)
        for v in (lat, lng)
    )
    if not ok or not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return False, None, None
    return True, float(lat), float(lng)


@dataclass
class UncataloguedAddResult:
    ok: bool
    code: str = ""
    message: str = ""
    nodes: List[TripNode] = field(default_factory=list)
    added: Optional[TripNode] = None
    review: Optional[Dict[str, Any]] = None  # SPEC-42 needs_review payload
    warnings: List[str] = field(default_factory=list)


def apply_uncatalogued_add(
    trip: TripState, preferences: Optional[dict], db: Any
) -> UncataloguedAddResult:
    """Validate, check feasibility, and build one trip-private node (pure)."""
    prefs = preferences or {}
    nodes = list(trip.nodes)

    def refuse(code: str) -> UncataloguedAddResult:
        return UncataloguedAddResult(ok=False, code=code, message=REFUSAL_COPY[code], nodes=nodes)

    if prefs.get("mode") != UNCATALOGUED_ADD_MODE:
        return refuse("invalid_mode")
    name = _clean_name(prefs.get("name"))
    if name is None:
        return refuse("invalid_name")
    if prefs.get("time_window") is not None:
        return _apply_window(trip, prefs, db, name, nodes, refuse)
    dwell = _clean_dwell(prefs.get("typical_dwell_minutes"))
    if dwell is None:
        return refuse("invalid_dwell")
    coords_ok, lat, lng = _clean_coords(prefs.get("lat"), prefs.get("lng"))
    if not coords_ok:
        return refuse("invalid_coords")
    raw_micro = prefs.get("micro_location")
    micro = " ".join(raw_micro.split()) if isinstance(raw_micro, str) else None
    micro = micro or None

    ctx, code = day_context(trip, prefs.get("target_date"), prefs.get("target_slot"))
    if ctx is None or code:
        return refuse(code or "invalid_date")

    collision = _collision_code(name, ctx, db)
    if collision:
        return refuse(collision)

    start, _why = place_timing(
        ctx, lat=lat, lng=lng, dwell=dwell, structured=None, check_hours=False
    )
    if start is None:
        return refuse("reachability")

    slot = ctx.target_slot
    node = TripNode(
        venue_name=name,
        venue_id=None,
        scheduled_start=start,
        duration_minutes=dwell,
        micro_location=micro,
        lat=lat,
        lng=lng,
        geo_region=ctx.region,
        slot_name=slot,
        place_source=TRIP_PRIVATE,
    )
    new_nodes = nodes + [node]
    new_nodes.sort(key=lambda n: _aware(n.scheduled_start))
    return UncataloguedAddResult(
        ok=True,
        message=f"Added {name} to {prefs['target_date']} {_SLOT_LABELS[slot]} (only on this trip).",
        nodes=new_nodes,
        added=node,
    )


def _collision_code(name: str, ctx: Any, db: Any) -> Optional[str]:
    """Catalog read for collision only: never attach catalog identity."""
    key = normalize_name(name)
    for row in db.list_venues_for_region(ctx.region) or []:
        if key == normalize_name(str(row.get("name") or "")):
            return "catalog_match"
        if name == str(row.get("venue_id") or ""):
            return "invalid_name"
    if any(normalize_name(n.venue_name or "") == key for n in ctx.day_nodes):
        return "duplicate"
    return None


def _is_hotel(node: TripNode) -> bool:
    return (node.node_kind or "") == "booking" and (node.booking_type or "") == "hotel"


def active_window_overlap(
    nodes: List[TripNode],
    start: Any,
    duration_minutes: int,
    booking_type: Optional[str],
    ignore_node_id: Optional[str] = None,
) -> Optional[TripNode]:
    """SPEC-42: the first active excursion window a booking span overlaps.

    Mirrors locked_conflict the other way round. Hotels never overlap.
    Overlap is strict: touching the window's start or end is not a clash.
    """
    if booking_type == "hotel":
        return None
    b_start = _aware(start)
    b_end = b_start + timedelta(minutes=int(duration_minutes))
    for n in nodes:
        if n.node_id == ignore_node_id or not n.time_window:
            continue
        if n.status not in (NodeStatus.PENDING, NodeStatus.ACTIVE):
            continue
        w_start = _aware(n.scheduled_start)
        w_end = w_start + timedelta(minutes=n.duration_minutes)
        if b_start < w_end and b_end > w_start:
            return n
    return None


def booking_over_window_message(window: TripNode, start: Any, region: Optional[str]) -> str:
    """Refusal copy naming the excursion, its window and the local date."""
    from datetime import timezone

    from services.destination_tz import destination_tz

    tz = destination_tz(region or "") or timezone.utc
    local_date = _aware(start).astimezone(tz).date().isoformat()
    label = _WINDOW_LABELS.get(window.time_window or "", window.time_window or "")
    return (
        f"This overlaps {window.venue_name} ({label}, {local_date}). "
        "Cancel the excursion first, then add the booking."
    )


def _apply_window(
    trip: TripState, prefs: dict, db: Any, name: str, nodes: List[TripNode], refuse
) -> UncataloguedAddResult:
    """SPEC-42 unknown-time excursion: a window instead of a slot plus dwell.

    No clock promise: the node spans the consumed slots from the first slot
    floor to the floor of the slot after the last consumed one. Flexible
    stops in those slots are skipped in place only after a confirmed review.
    """
    from services.catalog_itinerary import _slot_floor_utc
    from services.scheduler import reschedule_and_validate

    if prefs.get("target_slot") is not None:
        return refuse("invalid_slot")
    window = prefs.get("time_window")
    consumed = TIME_WINDOWS.get(window) if isinstance(window, str) else None
    if consumed is None:
        return refuse("invalid_window")
    if "typical_dwell_minutes" in prefs:
        return refuse("invalid_dwell")
    coords_ok, lat, lng = _clean_coords(prefs.get("lat"), prefs.get("lng"))
    if not coords_ok:
        return refuse("invalid_coords")
    raw_micro = prefs.get("micro_location")
    micro = " ".join(raw_micro.split()) if isinstance(raw_micro, str) else None
    micro = micro or None

    # The window's own occupancy is decided below, so "occupied" is not final.
    ctx, code = day_context(trip, prefs.get("target_date"), consumed[0])
    if ctx is None:
        return refuse(code or "invalid_date")
    collision = _collision_code(name, ctx, db)
    if collision:
        return refuse(collision)

    end_slot = SLOT_ORDER[SLOT_ORDER.index(consumed[-1]) + 1]
    start = _aware(ctx.floor_utc)
    end = _aware(_slot_floor_utc(end_slot, ctx.local_day, ctx.tz))

    for n in ctx.day_nodes:
        if not (n.is_locked or (n.node_kind or "") == "booking") or _is_hotel(n):
            continue
        n_start = _aware(n.scheduled_start)
        n_end = n_start + timedelta(minutes=n.duration_minutes)
        if n.slot_name in consumed or (n_start < end and n_end > start):
            return refuse("locked_conflict")

    day_ids = {n.node_id for n in ctx.day_nodes}
    conflicts = [
        n.node_id
        for n in nodes
        if n.node_id in day_ids
        and not n.is_locked
        and (n.node_kind or "activity") != "booking"
        and n.status in (NodeStatus.PENDING, NodeStatus.ACTIVE)
        and n.slot_name in consumed
    ]
    confirm = prefs.get("confirm_skip_node_ids")
    if confirm is None:
        if conflicts:
            return UncataloguedAddResult(
                ok=False,
                code="needs_review",
                message=REFUSAL_COPY["needs_review"],
                nodes=nodes,
                review={"time_window": window, "skip_node_ids": conflicts},
            )
    elif (
        not isinstance(confirm, list)
        or len(set(map(str, confirm))) != len(confirm)
        or set(map(str, confirm)) != set(conflicts)
    ):
        return refuse("stale")

    node = TripNode(
        venue_name=name,
        venue_id=None,
        scheduled_start=start,
        duration_minutes=int((end - start).total_seconds() // 60),
        micro_location=micro,
        lat=lat,
        lng=lng,
        geo_region=ctx.region,
        slot_name=consumed[0],
        place_source=TRIP_PRIVATE,
        time_window=window,
    )
    skip = set(conflicts)
    new_nodes = [
        # SPEC-42: tag each stop with the window that skipped it, so a later
        # cancel of this excursion can bring exactly these stops back.
        n.model_copy(update={"status": NodeStatus.SKIPPED, "skipped_by_window_id": node.node_id})
        if n.node_id in skip
        else n
        for n in nodes
    ] + [node]
    new_nodes.sort(key=lambda n: _aware(n.scheduled_start))
    warnings: List[str] = []
    if skip:
        # Same in-place skip as unlocked cancel, then one reschedule.
        result = reschedule_and_validate(new_nodes, mutated_node_ids={node.node_id, *skip})
        new_nodes, warnings = result.nodes, result.warnings
    return UncataloguedAddResult(
        ok=True,
        message=(
            f"Added {name} to {prefs['target_date']} {_WINDOW_LABELS[window]} (only on this trip)."
        ),
        nodes=new_nodes,
        added=node,
        warnings=warnings,
    )
