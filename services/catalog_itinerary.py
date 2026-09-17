"""Deterministic one-day itinerary seed from a city venue catalog (SPEC-32).

Create-trip reads venues by geo_region. It does not call hybrid search, the
LLM, or the reroute quota path.
"""

from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Sequence

from config.interests import VENUES_PER_DAY
from config.regions import REGIONS, require_region
from models.schemas import CurrentContext, TripNode
from services.opening_hours import HoursResult as _HoursResult
from services.opening_hours import hours_for_slot as _hours_for_slot
from services.opening_hours import next_slot_start as _next_slot_start

INFRASTRUCTURE_CATEGORIES = frozenset({"hospital", "pharmacy", "transport_hub"})
TARGET_STOPS = 5
MIN_STOPS = 4
DEFAULT_DURATION_MINUTES = 90

# Prefer one venue from each bucket, then fill remaining slots by name.
CATEGORY_BUCKETS: Sequence[frozenset[str]] = (
    frozenset({"temple", "museum", "gallery"}),
    frozenset({"cafe", "restaurant", "street_food"}),
    frozenset({"market", "craft_workshop"}),
    frozenset({"viewpoint", "nature", "walking_area", "river_activity"}),
    frozenset({"massage_spa", "bar", "community_space", "experience"}),
)

# Names that prove the Dubai fixture leaked into a Laos (or catalog) day.
DUBAI_FIXTURE_NAMES = frozenset(
    {
        "Dubai Museum (Al Fahidi Fort)",
        "XVA Art Gallery & Cafe",
        "La Petite Maison (DIFC)",
        "Alserkal Avenue Galleries",
        "Drift Beach Dubai",
    }
)


class InsufficientCatalog(ValueError):
    """Not enough eligible venues to seed a day for this region."""


def flatten_opening_hours(raw) -> str | None:
    if isinstance(raw, str) and raw.strip():
        return raw
    if isinstance(raw, dict):
        for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"):
            windows = raw.get(day) or []
            if windows and windows[0] and len(windows[0]) >= 2:
                return f"{windows[0][0]}-{windows[0][1]}"
    return None


def eligible_venues(rows: Iterable[dict]) -> List[dict]:
    eligible = []
    for row in rows:
        category = (row.get("category") or "experience").lower()
        if category in INFRASTRUCTURE_CATEGORIES:
            continue
        if row.get("lat") is None or row.get("lng") is None:
            continue
        if not (row.get("name") or "").strip():
            continue
        eligible.append(row)
    eligible.sort(key=lambda row: ((row.get("name") or "").lower(), str(row.get("venue_id") or "")))
    return eligible


def eligible_corridor_venues(rows) -> list:
    """Like eligible_venues but also requires a stable venue_id."""
    return [r for r in eligible_venues(rows) if r.get("venue_id")]


def select_day_venues(rows: Sequence[dict]) -> List[dict]:
    pool = eligible_corridor_venues(rows)
    if len(pool) < MIN_STOPS:
        raise InsufficientCatalog(f"need at least {MIN_STOPS} eligible venues, have {len(pool)}")

    chosen: List[dict] = []
    used_ids: set[str] = set()
    used_names: set[str] = set()

    def _take(row: dict) -> None:
        key = str(row.get("venue_id") or row["name"])
        name = row["name"]
        if key in used_ids or name in used_names:
            return
        used_ids.add(key)
        used_names.add(name)
        chosen.append(row)

    for bucket in CATEGORY_BUCKETS:
        if len(chosen) >= TARGET_STOPS:
            break
        match = next(
            (row for row in pool if (row.get("category") or "experience").lower() in bucket),
            None,
        )
        if match is not None:
            _take(match)

    for row in pool:
        if len(chosen) >= TARGET_STOPS:
            break
        _take(row)

    if len(chosen) < MIN_STOPS:
        raise InsufficientCatalog(f"need at least {MIN_STOPS} eligible venues, have {len(chosen)}")
    return chosen[:TARGET_STOPS]


def duration_for(row: dict) -> int:
    dwell = row.get("typical_dwell_minutes")
    if isinstance(dwell, int) and 10 <= dwell <= 300:
        return dwell
    if isinstance(dwell, float) and 10 <= dwell <= 300:
        return int(dwell)
    return DEFAULT_DURATION_MINUTES


def _make_node(row: dict, cursor: datetime, geo_region: str) -> TripNode:
    """Build a TripNode from a venue dict, carrying structured hours."""
    duration = duration_for(row)
    hours = flatten_opening_hours(row.get("opening_hours"))
    return TripNode(
        venue_name=row["name"],
        venue_id=str(row["venue_id"]) if row.get("venue_id") else None,
        scheduled_start=cursor,
        duration_minutes=duration,
        micro_location=row.get("micro_location"),
        vibe_tags=list(row.get("vibe_tags") or []),
        lat=float(row["lat"]),
        lng=float(row["lng"]),
        opening_hours=hours,
        opening_hours_structured=row.get("opening_hours_structured"),
        geo_region=geo_region,
        names_local=row.get("names_local"),
        landmarks_local=row.get("landmarks_local"),
        nearest_landmark=row.get("nearest_landmark"),
    )


def _is_hours_eligible(row: dict, cursor: datetime, geo_region: str) -> bool:
    """True unless the venue is definitely CLOSED at *cursor*."""
    structured = row.get("opening_hours_structured")
    result = _hours_for_slot(structured, cursor, duration_for(row), geo_region)
    return result != _HoursResult.CLOSED


# ---------------------------------------------------------------------------
# SPEC-41 A3a: Shared deterministic day planner
# ---------------------------------------------------------------------------


def _has_venue_coords(venue: dict) -> bool:
    """True if the venue dict has finite lat and lng (rejects None, NaN, inf)."""
    import math as _m

    lat = venue.get("lat")
    lng = venue.get("lng")
    if lat is None or lng is None:
        return False
    try:
        return _m.isfinite(lat) and _m.isfinite(lng)
    except TypeError:
        return False


def pack_day(
    candidates: Sequence[dict],
    target_count: int,
    day_start_utc: datetime,
    geo_region: str,
    used_ids: set[str],
    interest_ids: Sequence[str] = (),
    bucket_diversity: bool = True,
    next_locked_booking: Optional[TripNode] = None,
) -> tuple[List[TripNode], set[str]]:
    """Fill one day with up to *target_count* venues using window packing.

    Shared by ``nodes_from_catalog``, ``range_nodes_from_catalog``, and
    ``build_corridor_nodes``.

    Algorithm per stop:

    1. Exclude used IDs, infrastructure, and identity/geometry invalids
       (already filtered in *candidates*).
    2. For every remaining candidate, compute its per-candidate earliest
       start = prev_end + walking_minutes(prev, C).  First stop of the
       day has no transfer.
    3. Pass that earliest start into ``next_slot_start``.
    4. Select the candidate with the earliest fitting start; for ties,
       retain the deterministic rank order.
    5. If a next_locked_booking exists on the same day, verify the
       candidate can walk there before the lock starts.
    6. Repeat until target_count or no candidate fits.

    Returns (nodes, new_used_ids) without mutating caller inputs.
    """
    from services.destination_tz import destination_tz as _dest_tz
    from services.transit import walking_minutes as _walking_minutes
    from zoneinfo import ZoneInfo

    tz = _dest_tz(geo_region)
    if tz is not None:
        local_day = day_start_utc.astimezone(tz)
    else:
        local_day = day_start_utc
    # Pre-score and sort candidates for deterministic tie-breaking.
    scored = sorted(
        candidates,
        key=lambda v: (
            -_interest_score(v, interest_ids),
            (v.get("name") or "").lower(),
            str(v.get("venue_id") or ""),
        ),
    )

    nodes: List[TripNode] = []
    new_used: set[str] = set(used_ids)  # copy
    used_buckets: set[int] = set()

    # Previous-node tracking for walking transfer
    prev_node: Optional[TripNode] = None

    def _candidate_earliest(venue: dict) -> Optional[datetime]:
        """Compute candidate's earliest arrival accounting for walking transfer."""
        if prev_node is None:
            return day_start_utc
        if prev_node.lat is None or prev_node.lng is None:
            return None  # prev has no coords -> ineligible
        if not _has_venue_coords(venue):
            return None  # candidate has no coords -> ineligible
        prev_end = prev_node.scheduled_start + timedelta(minutes=prev_node.duration_minutes)
        transfer = _walking_minutes(prev_node.lat, prev_node.lng, venue["lat"], venue["lng"])
        return prev_end + timedelta(minutes=transfer)

    def _fits_next_lock(venue: dict, slot: datetime, dwell: int) -> bool:
        """True if the candidate can reach the next locked booking in time.

        Ignores the lock when it is a hotel (background anchor), belongs to a
        different geo_region, or falls on a different destination-local day.
        """
        if next_locked_booking is None:
            return True
        lock = next_locked_booking
        # Hotels are background anchors, not reachability targets.
        if (
            getattr(lock, "node_kind", "activity") == "booking"
            and getattr(lock, "booking_type", "") == "hotel"
        ):
            return True
        # Different region -> not a same-city constraint.
        lock_region = getattr(lock, "geo_region", None)
        if lock_region and lock_region != geo_region:
            return True
        # Different local day -> not a same-day constraint.
        if tz is not None:
            lock_local_day = lock.scheduled_start.astimezone(tz).date()
            slot_local_day = slot.astimezone(tz).date()
        else:
            lock_local_day = lock.scheduled_start.date()
            slot_local_day = slot.date()
        if lock_local_day != slot_local_day:
            return True
        # Relevant same-day, same-region, non-hotel lock: require coords.
        import math as _m

        if (
            lock.lat is None
            or lock.lng is None
            or not _m.isfinite(lock.lat)
            or not _m.isfinite(lock.lng)
        ):
            return False  # missing lock coords -> ineligible
        if not _has_venue_coords(venue):
            return False
        cand_end = slot + timedelta(minutes=dwell)
        transfer = _walking_minutes(venue["lat"], venue["lng"], lock.lat, lock.lng)
        return cand_end + timedelta(minutes=transfer) <= lock.scheduled_start

    for _stop in range(target_count):
        best_candidate = None
        best_start: Optional[datetime] = None
        best_rank = -1

        for rank, venue in enumerate(scored):
            vk = _venue_key(venue)
            if vk in new_used:
                continue

            # Geometry eligibility: candidate must have coordinates
            if not _has_venue_coords(venue):
                continue

            # Compute per-candidate earliest arrival from previous node
            earliest = _candidate_earliest(venue)
            if earliest is None:
                continue

            dwell = duration_for(venue)
            structured = venue.get("opening_hours_structured")
            slot = _next_slot_start(structured, earliest, dwell, geo_region, local_day)
            if slot is None:
                continue

            # Next-locked-booking check
            if not _fits_next_lock(venue, slot, dwell):
                continue

            # Bucket diversity: in pass 1, prefer unfilled buckets
            if bucket_diversity and len(nodes) < min(target_count, len(CATEGORY_BUCKETS)):
                bidx = _bucket_index(venue)
                if bidx in used_buckets:
                    pass

            if best_start is None or slot < best_start:
                best_candidate = venue
                best_start = slot
                best_rank = rank
            elif slot == best_start and rank < best_rank:
                best_candidate = venue
                best_start = slot
                best_rank = rank

        if best_candidate is None:
            break

        # Apply bucket diversity: if a bucket-fresh candidate has the same
        # earliest start, prefer it.
        if bucket_diversity and len(nodes) < min(target_count, len(CATEGORY_BUCKETS)):
            best_bidx = _bucket_index(best_candidate)
            if best_bidx in used_buckets:
                for rank, venue in enumerate(scored):
                    vk = _venue_key(venue)
                    if vk in new_used:
                        continue
                    if not _has_venue_coords(venue):
                        continue
                    bidx = _bucket_index(venue)
                    if bidx in used_buckets:
                        continue
                    earliest = _candidate_earliest(venue)
                    if earliest is None:
                        continue
                    dwell = duration_for(venue)
                    structured = venue.get("opening_hours_structured")
                    slot = _next_slot_start(structured, earliest, dwell, geo_region, local_day)
                    if slot is not None and slot == best_start:
                        if not _fits_next_lock(venue, slot, dwell):
                            continue
                        best_candidate = venue
                        best_start = slot
                        best_rank = rank
                        best_bidx = bidx
                        break

            used_buckets.add(_bucket_index(best_candidate))

        vk = _venue_key(best_candidate)
        new_used.add(vk)
        node = _make_node(best_candidate, best_start, geo_region)
        nodes.append(node)
        prev_node = node

    return nodes, new_used


def nodes_from_catalog(
    *,
    geo_region: str,
    start: datetime,
    rows: Sequence[dict],
) -> List[TripNode]:
    pool = eligible_corridor_venues(rows)
    if len(pool) < MIN_STOPS:
        raise InsufficientCatalog(f"need at least {MIN_STOPS} eligible venues, have {len(pool)}")

    nodes, _used = pack_day(
        candidates=pool,
        target_count=TARGET_STOPS,
        day_start_utc=start,
        geo_region=geo_region,
        used_ids=set(),
    )

    if len(nodes) < MIN_STOPS:
        raise InsufficientCatalog(f"need at least {MIN_STOPS} eligible venues, have {len(nodes)}")
    return nodes[:TARGET_STOPS]


def context_for_region(geo_region: str, mood: str | None) -> CurrentContext:
    region = require_region(geo_region)
    return CurrentContext(
        location_lat=region.default_lat,
        location_lng=region.default_lng,
        mood=mood or "exploratory",
    )


def advertised_regions(list_venues) -> List[str]:
    """Regions we can actually seed, in a stable order."""
    preferred = [
        "dubai_uae",
        "luang_prabang_laos",
        "vang_vieng_laos",
        "vientiane_laos",
    ]
    ready = []
    for code in preferred:
        if code not in REGIONS:
            continue
        try:
            select_day_venues(list_venues(code))
        except InsufficientCatalog:
            continue
        ready.append(code)
    return ready


# ---------------------------------------------------------------------------
# SPEC-40: Interest-scored deterministic range builder
# ---------------------------------------------------------------------------


def _interest_score(venue: dict, interest_ids: Sequence[str]) -> float:
    """Score a venue against requested interests.

    Each matching category or vibe tag adds 1.0.  Zero interests means
    balanced catalog order (score 0 for everyone).
    """
    if not interest_ids:
        return 0.0
    from config.interests import get_interest

    category = (venue.get("category") or "experience").lower()
    tags = frozenset(t.lower() for t in (venue.get("vibe_tags") or []))
    score = 0.0
    for iid in interest_ids:
        interest = get_interest(iid)
        if category in interest.category_matches:
            score += 1.0
        score += len(tags & interest.vibe_tag_matches)
    return score


def _bucket_index(venue: dict) -> int:
    """Return the CATEGORY_BUCKETS index for diversity tracking.

    Returns len(CATEGORY_BUCKETS) for venues that match no bucket.
    """
    category = (venue.get("category") or "experience").lower()
    for idx, bucket in enumerate(CATEGORY_BUCKETS):
        if category in bucket:
            return idx
    return len(CATEGORY_BUCKETS)


def select_day_venues_scored(
    pool: List[dict],
    interest_ids: Sequence[str],
    used_venue_ids: set,
) -> List[dict]:
    """Pick exactly VENUES_PER_DAY unique venues for one day.

    1. Exclude already-used venues (cross-day uniqueness).
    2. Score by interest matches.
    3. Preserve category-bucket diversity (pick from distinct buckets first).
    4. Break ties by normalized venue name then stable venue ID.

    Raises InsufficientCatalog if not enough remain.
    """
    available = [v for v in pool if _venue_key(v) not in used_venue_ids]
    if len(available) < VENUES_PER_DAY:
        raise InsufficientCatalog(f"need {VENUES_PER_DAY} unused venues, have {len(available)}")

    # Sort: highest interest score first, then name, then venue_id for determinism
    scored = sorted(
        available,
        key=lambda v: (
            -_interest_score(v, interest_ids),
            (v.get("name") or "").lower(),
            str(v.get("venue_id") or ""),
        ),
    )

    chosen: List[dict] = []
    used_buckets: set[int] = set()

    # Pass 1: one per bucket for diversity
    for venue in scored:
        if len(chosen) >= VENUES_PER_DAY:
            break
        bidx = _bucket_index(venue)
        if bidx not in used_buckets:
            used_buckets.add(bidx)
            chosen.append(venue)

    # Pass 2: fill remaining from scored order
    chosen_keys = {_venue_key(v) for v in chosen}
    for venue in scored:
        if len(chosen) >= VENUES_PER_DAY:
            break
        if _venue_key(venue) not in chosen_keys:
            chosen.append(venue)
            chosen_keys.add(_venue_key(venue))

    # Final sort for deterministic schedule order: by name then id
    chosen.sort(key=lambda v: ((v.get("name") or "").lower(), str(v.get("venue_id") or "")))
    result = chosen[:VENUES_PER_DAY]
    # Assert exactly VENUES_PER_DAY unique venue_ids selected
    result_ids = {str(v["venue_id"]) for v in result}
    if len(result_ids) != VENUES_PER_DAY:
        raise InsufficientCatalog(
            f"expected {VENUES_PER_DAY} unique venue IDs, got {len(result_ids)}"
        )
    return result


def _dedup_by_venue_id(pool: List[dict]) -> List[dict]:
    """Deduplicate eligible corridor venues by venue_id.

    Keeps the first occurrence of each venue_id.  Every entry in *pool*
    is guaranteed to have a non-None venue_id (ensured by
    eligible_corridor_venues).
    """
    seen: set[str] = set()
    result: list[dict] = []
    for v in pool:
        vid = str(v["venue_id"])
        if vid not in seen:
            seen.add(vid)
            result.append(v)
    return result


def _venue_key(venue: dict) -> str:
    """Stable dedup key: venue_id if present, else name."""
    return str(venue.get("venue_id") or venue["name"])


def _valid_interest_profiles() -> list[tuple[str, ...]]:
    """Return all valid interest profiles of size 0..MAX_INTERESTS.

    Used by truthful advertised-capacity calculation so the published
    max_days value succeeds regardless of which valid interests a user picks.
    """
    from itertools import combinations

    from config.interests import INTEREST_IDS, MAX_INTERESTS

    ids = sorted(INTEREST_IDS)
    profiles: list[tuple[str, ...]] = [()]
    for size in range(1, MAX_INTERESTS + 1):
        profiles.extend(combinations(ids, size))
    return profiles


def range_nodes_from_catalog(
    *,
    geo_region: str,
    start_date_local: str,
    end_date_local: str,
    rows: Sequence[dict],
    interest_ids: Sequence[str] = (),
) -> List[TripNode]:
    """Build a deterministic multi-day itinerary for a date range.

    Exactly VENUES_PER_DAY venues per day, no repeats across the
    entire trip.  Schedule from 09:00 in the region IANA timezone, stored
    as UTC.  Uses the shared A3a window-packing planner.
    """
    from datetime import date as date_type
    from zoneinfo import ZoneInfo

    region = require_region(geo_region)
    region_tz = ZoneInfo(region.timezone)

    sd = date_type.fromisoformat(start_date_local)
    ed = date_type.fromisoformat(end_date_local)
    num_days = (ed - sd).days + 1  # inclusive

    pool = _dedup_by_venue_id(eligible_corridor_venues(rows))
    used_ids: set[str] = set()
    all_nodes: List[TripNode] = []

    for day_offset in range(num_days):
        current_date = sd + timedelta(days=day_offset)
        day_start = datetime(
            current_date.year,
            current_date.month,
            current_date.day,
            9,
            0,
            0,
            tzinfo=region_tz,
        ).astimezone(timezone.utc)

        day_nodes, used_ids = pack_day(
            candidates=pool,
            target_count=VENUES_PER_DAY,
            day_start_utc=day_start,
            geo_region=geo_region,
            used_ids=used_ids,
            interest_ids=interest_ids,
        )
        if len(day_nodes) < VENUES_PER_DAY:
            raise InsufficientCatalog(
                f"need {VENUES_PER_DAY} hours-eligible venues on {current_date}, "
                f"have {len(day_nodes)}"
            )
        all_nodes.extend(day_nodes)

    return all_nodes


# ---------------------------------------------------------------------------
# Bounded catalog-fingerprint cache for compute_max_days_for_region
# ---------------------------------------------------------------------------

_CAPACITY_CACHE_MAX_SIZE = 32
_capacity_cache: dict[tuple[str, str], Optional[int]] = {}
_capacity_cache_order: list[tuple[str, str]] = []  # insertion order for eviction


def _catalog_fingerprint(rows: Sequence[dict]) -> str:
    """Deterministic fingerprint of planner-relevant catalog fields.

    Covers every field that influences venue selection, scoring, scheduling,
    or day-packing: identity (venue_id, name), coordinates (lat, lng),
    ranking (category, vibe_tags), hours (opening_hours_structured), and
    dwell (typical_dwell_minutes).  Changing any of these invalidates.

    No network, clock, or process-random inputs.
    """
    import hashlib
    import json

    parts: list[str] = []
    for row in sorted(rows, key=lambda r: str(r.get("venue_id") or r.get("name") or "")):
        record = (
            str(row.get("venue_id") or ""),
            str(row.get("name") or ""),
            str(row.get("lat") or ""),
            str(row.get("lng") or ""),
            str(row.get("category") or ""),
            json.dumps(sorted(row.get("vibe_tags") or []), sort_keys=True),
            json.dumps(row.get("opening_hours_structured"), sort_keys=True),
            str(row.get("typical_dwell_minutes") or ""),
        )
        parts.append("|".join(record))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def invalidate_capacity_cache() -> None:
    """Clear the capacity cache.  Useful in tests."""
    _capacity_cache.clear()
    _capacity_cache_order.clear()


def compute_max_days_for_region(list_venues_fn, geo_region: str) -> Optional[int]:
    """Advertised max_days for a region, or None if insufficient catalog.

    SPEC-41 A3a: evaluate all seven possible start weekdays and all valid
    interest profiles using incremental day-by-day simulation with the same
    pack_day planner as range create.  Advertise only the largest span that
    succeeds for every weekday and every valid set of interests.  Clamped to
    the product ceiling.

    Results are cached by (geo_region, catalog fingerprint).  Changed hours,
    dwell, identity or ranking fields invalidate the cache.
    """
    from config.interests import MAX_DAYS_CEILING
    from datetime import date as date_type
    from zoneinfo import ZoneInfo

    try:
        rows = list_venues_fn(geo_region)
        pool = _dedup_by_venue_id(eligible_corridor_venues(rows))
    except Exception:
        return None

    if len(pool) < VENUES_PER_DAY:
        return None

    fp = _catalog_fingerprint(rows)
    cache_key = (geo_region, fp)
    if cache_key in _capacity_cache:
        return _capacity_cache[cache_key]

    region = require_region(geo_region)
    region_tz = ZoneInfo(region.timezone)
    interest_profiles = _valid_interest_profiles()

    # Use a fixed anchor week: 2026-09-14 (Monday) through 2026-09-20 (Sunday)
    anchor_monday = date_type(2026, 9, 14)

    weekday_maxes: list[int] = []
    for wd in range(7):  # Mon=0 .. Sun=6
        anchor_date = anchor_monday + timedelta(days=wd)
        # For each profile, simulate incrementally: carry used_ids day-by-day
        # until failure or MAX_DAYS_CEILING.  The minimum across all profiles
        # is the guaranteed span for this weekday.
        profile_spans: list[int] = []
        for interest_ids in interest_profiles:
            span = 0
            used_ids: set[str] = set()
            for day_offset in range(MAX_DAYS_CEILING):
                current_date = anchor_date + timedelta(days=day_offset)
                day_start = datetime(
                    current_date.year,
                    current_date.month,
                    current_date.day,
                    9,
                    0,
                    0,
                    tzinfo=region_tz,
                ).astimezone(timezone.utc)
                day_nodes, used_ids = pack_day(
                    candidates=pool,
                    target_count=VENUES_PER_DAY,
                    day_start_utc=day_start,
                    geo_region=geo_region,
                    used_ids=used_ids,
                    interest_ids=interest_ids,
                )
                if len(day_nodes) < VENUES_PER_DAY:
                    break
                span += 1
            profile_spans.append(span)
        weekday_maxes.append(min(profile_spans))

    guaranteed = min(weekday_maxes)
    result = guaranteed if guaranteed >= 1 else None

    # Store in bounded cache
    if cache_key not in _capacity_cache:
        if len(_capacity_cache) >= _CAPACITY_CACHE_MAX_SIZE:
            oldest = _capacity_cache_order.pop(0)
            _capacity_cache.pop(oldest, None)
        _capacity_cache_order.append(cache_key)
    _capacity_cache[cache_key] = result
    return result
