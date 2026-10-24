"""SPEC-42 empty-day catalog Add (``add_activity`` + ``mode=direct_add``).

One pure evaluator is shared by ``GET /trip/{id}/add_candidates`` and the
confirm path, so listing is never a weaker preview of apply. Catalog rows
come from ``list_venues_for_region`` on either backend; the evaluator itself
never touches a database, venue search, or an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from models.schemas import NodeStatus, TripNode, TripState
from services.day_slots import SLOT_ORDER, is_whole_day_excursion, venue_fits_slot
from services.move_service import (
    _DAY_START_HOUR,
    _aware,
    _finite,
    _is_flexible,
    _is_hotel,
    _local_date,
    _region,
    trip_span,
)

DIRECT_ADD_MODE = "direct_add"
MAX_CANDIDATES = 5
_MIN_DWELL = 10
_MAX_DWELL = 300

# Listing refusal codes (closed set) plus apply-only payload codes.
REFUSAL_COPY: Dict[str, str] = {
    "no_catalog": "No catalog places fit that slot on this day.",
    "duplicate": "Every place that fits that slot is already on your trip.",
    "hours": "Nothing that fits is open in that slot on this day.",
    "reachability": "Nothing that fits can be reached around your other plans that day.",
    "occupied": "That slot already has an activity on this day.",
    "invalid_date": "That date isn't part of this trip.",
    "invalid_mode": "That add request was not recognised. Nothing was changed.",
    "invalid_slot": "Choose morning, lunch, afternoon, or dinner.",
    "invalid_venue": "That place can't be added to this slot. Nothing was changed.",
}

_SLOT_LABELS = {
    "morning_tour": "morning",
    "lunch": "lunch",
    "afternoon_evening_tour": "afternoon",
    "dinner": "dinner",
}


@dataclass
class Candidate:
    venue_id: str
    row: dict
    start_utc: datetime
    dwell: int
    score: float


@dataclass
class Evaluation:
    geo_region: Optional[str]
    candidates: List[Candidate] = field(default_factory=list)
    refusal_code: Optional[str] = None

    @property
    def refusal_copy(self) -> Optional[str]:
        return REFUSAL_COPY.get(self.refusal_code) if self.refusal_code else None


def parse_target_date(raw: Any) -> Optional[date]:
    if not isinstance(raw, str) or len(raw) != 10:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def resolve_target_region(trip: TripState, target_date: date) -> Optional[str]:
    """Single city -> trip region; corridor -> the one containing segment."""
    span = trip_span(trip)
    if span is None or not (span[0] <= target_date <= span[1]):
        return None
    if trip.segments:
        containing = [s for s in trip.segments if s.starts_on <= target_date <= s.ends_on]
        if len(containing) != 1:
            return None  # gap or ambiguous overlap
        return containing[0].geo_region
    return trip.geo_region or None


def canonical_dwell(row: dict) -> Optional[int]:
    """Catalog dwell only; missing/invalid -> None (never the default 90)."""
    dwell = row.get("typical_dwell_minutes")
    if isinstance(dwell, bool):
        return None
    if isinstance(dwell, (int, float)) and _MIN_DWELL <= dwell <= _MAX_DWELL:
        return int(dwell)
    return None


def _walk(a_lat, a_lng, b_lat, b_lng) -> Optional[int]:
    from services.transit import walking_minutes

    if not _finite(a_lat, a_lng, b_lat, b_lng):
        return None
    return walking_minutes(a_lat, a_lng, b_lat, b_lng)


def _evaluate_row(
    row: dict,
    *,
    target_slot: str,
    region: str,
    local_day: datetime,
    floor_utc: datetime,
    stops: Sequence[TripNode],
    locks_after: Sequence[TripNode],
) -> tuple[Optional[Candidate], str]:
    """Run predicates 4-10 for one already region/infra/duplicate-clean row."""
    from services.booking_constraints import fits_next_lock
    from services.catalog_itinerary import _slot_accepts_start
    from services.opening_hours import HoursResult, hours_for_slot, next_slot_start

    # 4. slot type (whole-day excursions out of this slice)
    if is_whole_day_excursion(row) or not venue_fits_slot(row, target_slot, list(SLOT_ORDER)):
        return None, "no_catalog"
    # 5. canonical dwell
    dwell = canonical_dwell(row)
    if dwell is None:
        return None, "no_catalog"
    lat, lng = row.get("lat"), row.get("lng")

    # 7. earliest start: slot floor, then previous non-hotel dwell + walk
    earliest = floor_utc
    prev = None
    for n in stops:
        if _aware(n.scheduled_start) <= earliest:
            prev = n
    if prev is not None:
        walk = _walk(prev.lat, prev.lng, lat, lng)
        if walk is None:
            return None, "reachability"  # transfer required, walk unknown
        prev_end = _aware(prev.scheduled_start) + timedelta(minutes=prev.duration_minutes)
        earliest = max(earliest, prev_end + timedelta(minutes=walk))

    structured = row.get("opening_hours_structured")
    start = next_slot_start(structured, earliest, dwell, region, local_day)
    if start is None or not _slot_accepts_start(target_slot, start, region):
        return None, "hours"
    # 8. known hours must fit start + canonical dwell
    if hours_for_slot(structured, start, dwell, region) == HoursResult.CLOSED:
        return None, "hours"
    end = start + timedelta(minutes=dwell)

    # 9. neighbour reachability (no overlap, walk both sides)
    for n in stops:
        n_start = _aware(n.scheduled_start)
        n_end = n_start + timedelta(minutes=n.duration_minutes)
        if n_start < end and start < n_end:
            return None, "reachability"
    before = [n for n in stops if _aware(n.scheduled_start) < start]
    if before and before[-1] is not prev:
        p = before[-1]
        walk = _walk(p.lat, p.lng, lat, lng)
        p_end = _aware(p.scheduled_start) + timedelta(minutes=p.duration_minutes)
        if walk is None or p_end + timedelta(minutes=walk) > start:
            return None, "reachability"
    nxt = next((n for n in stops if _aware(n.scheduled_start) >= end), None)
    if nxt is not None and _is_flexible(nxt):
        walk = _walk(lat, lng, nxt.lat, nxt.lng)
        if walk is None or end + timedelta(minutes=walk) > _aware(nxt.scheduled_start):
            return None, "reachability"

    # 10. next locked non-hotel via the shared helper (flight cutoff included)
    next_lock = next((n for n in locks_after if _aware(n.scheduled_start) >= start), None)
    if not fits_next_lock(row, start, dwell, next_lock, region):
        return None, "reachability"

    return Candidate(
        venue_id=str(row["venue_id"]), row=row, start_utc=start, dwell=dwell, score=0.0
    ), ""


def evaluate(
    trip: TripState,
    target_date_raw: Any,
    target_slot: Any,
    rows_for_region,
    *,
    venue_id: Optional[str] = None,
) -> Evaluation:
    """Shared evaluator. ``rows_for_region(region) -> list[dict]``."""
    from services.catalog_itinerary import (
        INFRASTRUCTURE_CATEGORIES,
        _interest_score,
        _slot_floor_utc,
    )
    from services.destination_tz import destination_tz

    if target_slot not in SLOT_ORDER:
        return Evaluation(geo_region=None, refusal_code="invalid_slot")
    target_date = parse_target_date(target_date_raw)
    if target_date is None:
        return Evaluation(geo_region=None, refusal_code="invalid_date")
    region = resolve_target_region(trip, target_date)
    if not region:
        return Evaluation(geo_region=None, refusal_code="invalid_date")

    day_nodes = [
        n
        for n in trip.nodes
        if _region(n, trip) == region
        and _local_date(n, trip) == target_date
        and n.status != NodeStatus.SKIPPED
    ]
    # 6. occupancy
    if any(_is_flexible(n) and n.slot_name == target_slot for n in day_nodes):
        return Evaluation(geo_region=region, refusal_code="occupied")

    tz = destination_tz(region)
    local_day = datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        _DAY_START_HOUR,
        tzinfo=tz or timezone.utc,
    )
    floor_utc = max(
        _aware(_slot_floor_utc(target_slot, local_day, tz)),
        local_day.astimezone(timezone.utc),
    )
    stops = sorted(
        (n for n in day_nodes if not _is_hotel(n)),
        key=lambda n: _aware(n.scheduled_start),
    )
    locks_after = sorted(
        (n for n in trip.nodes if not _is_flexible(n) and not _is_hotel(n)),
        key=lambda n: _aware(n.scheduled_start),
    )
    existing_ids = {n.venue_id for n in trip.nodes if n.venue_id}
    interest_ids = list(getattr(trip.creation_context, "interest_ids", None) or [])

    rows = list(rows_for_region(region) or [])
    if venue_id is not None:
        rows = [r for r in rows if str(r.get("venue_id") or "") == venue_id]
        if not rows:
            return Evaluation(geo_region=region, refusal_code="invalid_venue")

    counts = {"duplicate": 0, "hours": 0, "reachability": 0}
    found: List[Candidate] = []
    for row in rows:
        vid = str(row.get("venue_id") or "").strip()
        # 1. stable id + same region
        if not vid or row.get("geo_region") != region or not (row.get("name") or "").strip():
            continue
        # 2. infrastructure
        if (row.get("category") or "experience").lower() in INFRASTRUCTURE_CATEGORIES:
            continue
        # 3. duplicate
        if vid in existing_ids:
            counts["duplicate"] += 1
            continue
        cand, why = _evaluate_row(
            row,
            target_slot=target_slot,
            region=region,
            local_day=local_day,
            floor_utc=floor_utc,
            stops=stops,
            locks_after=locks_after,
        )
        if cand is None:
            if why in counts:
                counts[why] += 1
            continue
        cand.score = _interest_score(row, interest_ids)
        found.append(cand)

    def _key(c: Candidate):
        local = c.start_utc.astimezone(tz) if tz is not None else c.start_utc
        return (-c.score, local, (c.row.get("name") or "").strip().casefold(), c.venue_id)

    found.sort(key=_key)
    if venue_id is not None:
        if not found:
            worst = max(counts, key=lambda k: counts[k])
            return Evaluation(
                geo_region=region,
                refusal_code=worst if counts[worst] else "invalid_venue",
            )
        return Evaluation(geo_region=region, candidates=found[:1])
    if not found:
        worst = max(("duplicate", "hours", "reachability"), key=lambda k: counts[k])
        return Evaluation(
            geo_region=region,
            refusal_code=worst if counts[worst] else "no_catalog",
        )
    return Evaluation(geo_region=region, candidates=found[:MAX_CANDIDATES])


def candidates_response(trip: TripState, target_date: str, target_slot: str, db: Any) -> dict:
    """Read-only listing payload (closed DTO shape)."""
    from services.destination_tz import destination_tz

    ev = evaluate(trip, target_date, target_slot, db.list_venues_for_region)
    tz = destination_tz(ev.geo_region) if ev.geo_region else None
    return {
        "target_date": target_date,
        "target_slot": target_slot,
        "geo_region": ev.geo_region,
        "candidates": [
            {
                "venue_id": c.venue_id,
                "name": c.row.get("name") or "",
                "category": c.row.get("category") or "",
                "micro_location": c.row.get("micro_location"),
                "vibe_tags": list(c.row.get("vibe_tags") or []),
                "planned_start": (c.start_utc.astimezone(tz) if tz else c.start_utc).isoformat(),
                "typical_dwell_minutes": c.dwell,
            }
            for c in ev.candidates
        ],
        "refusal_code": ev.refusal_code,
        "refusal_copy": ev.refusal_copy,
    }


@dataclass
class DirectAddResult:
    ok: bool
    code: str = ""
    message: str = ""
    nodes: List[TripNode] = field(default_factory=list)
    added: Optional[TripNode] = None


def apply_direct_add(trip: TripState, preferences: Optional[dict], db: Any) -> DirectAddResult:
    """Confirm path: same evaluator, exact venue, server-computed start."""
    from services.catalog_itinerary import _make_node

    prefs = preferences or {}
    nodes = list(trip.nodes)

    def refuse(code: str) -> DirectAddResult:
        return DirectAddResult(ok=False, code=code, message=REFUSAL_COPY[code], nodes=nodes)

    if prefs.get("mode") != DIRECT_ADD_MODE:
        return refuse("invalid_mode")
    venue_id = prefs.get("venue_id")
    if not isinstance(venue_id, str) or not venue_id.strip():
        return refuse("invalid_venue")
    ev = evaluate(
        trip,
        prefs.get("target_date"),
        prefs.get("target_slot"),
        db.list_venues_for_region,
        venue_id=venue_id.strip(),
    )
    if not ev.candidates:
        return refuse(ev.refusal_code or "invalid_venue")
    cand = ev.candidates[0]
    slot = prefs["target_slot"]
    node = _make_node(cand.row, cand.start_utc, ev.geo_region, slot_name=slot)
    node = node.model_copy(update={"duration_minutes": cand.dwell})
    new_nodes = nodes + [node]
    new_nodes.sort(key=lambda n: _aware(n.scheduled_start))
    return DirectAddResult(
        ok=True,
        message=(f"Added {node.venue_name} to {prefs['target_date']} {_SLOT_LABELS[slot]}."),
        nodes=new_nodes,
        added=node,
    )
