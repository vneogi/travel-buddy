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
from typing import Any, Dict, List, Optional

from models.schemas import TripNode, TripState
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
}

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

    # Catalog read for collision only: never attach catalog identity.
    key = normalize_name(name)
    for row in db.list_venues_for_region(ctx.region) or []:
        if key == normalize_name(str(row.get("name") or "")):
            return refuse("catalog_match")
        if name == str(row.get("venue_id") or ""):
            return refuse("invalid_name")
    if any(normalize_name(n.venue_name or "") == key for n in ctx.day_nodes):
        return refuse("duplicate")

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
