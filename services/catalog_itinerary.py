"""Deterministic one-day itinerary seed from a city venue catalog (SPEC-32).

Create-trip reads venues by geo_region. It does not call hybrid search, the
LLM, or the reroute quota path.
"""

from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Sequence

from config.interests import VENUES_PER_DAY
from config.regions import REGIONS, require_region
from models.schemas import CurrentContext, TripNode

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


def nodes_from_catalog(
    *,
    geo_region: str,
    start: datetime,
    rows: Sequence[dict],
) -> List[TripNode]:
    selected = select_day_venues(rows)
    nodes: List[TripNode] = []
    cursor = start
    for row in selected:
        duration = duration_for(row)
        hours = flatten_opening_hours(row.get("opening_hours"))
        nodes.append(
            TripNode(
                venue_name=row["name"],
                venue_id=str(row["venue_id"]) if row.get("venue_id") else None,
                scheduled_start=cursor,
                duration_minutes=duration,
                micro_location=row.get("micro_location"),
                vibe_tags=list(row.get("vibe_tags") or []),
                lat=float(row["lat"]),
                lng=float(row["lng"]),
                opening_hours=hours,
                geo_region=geo_region,
                names_local=row.get("names_local"),
                landmarks_local=row.get("landmarks_local"),
                nearest_landmark=row.get("nearest_landmark"),
            )
        )
        cursor = cursor + timedelta(minutes=duration + 30)
    return nodes


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
    as UTC.
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

        day_venues = select_day_venues_scored(pool, interest_ids, used_ids)
        cursor = day_start
        for row in day_venues:
            duration = duration_for(row)
            hours = flatten_opening_hours(row.get("opening_hours"))
            all_nodes.append(
                TripNode(
                    venue_name=row["name"],
                    venue_id=str(row["venue_id"]) if row.get("venue_id") else None,
                    scheduled_start=cursor,
                    duration_minutes=duration,
                    micro_location=row.get("micro_location"),
                    vibe_tags=list(row.get("vibe_tags") or []),
                    lat=float(row["lat"]),
                    lng=float(row["lng"]),
                    opening_hours=hours,
                    geo_region=geo_region,
                    names_local=row.get("names_local"),
                    landmarks_local=row.get("landmarks_local"),
                    nearest_landmark=row.get("nearest_landmark"),
                )
            )
            cursor = cursor + timedelta(minutes=duration + 30)
            used_ids.add(_venue_key(row))

    return all_nodes


def compute_max_days_for_region(list_venues_fn, geo_region: str) -> Optional[int]:
    """Advertised max_days for a region, or None if insufficient catalog.

    Uses eligible_corridor_venues (requires stable venue_id) and deduplicates
    by venue_id so duplicate entries do not inflate capacity.
    """
    from config.interests import compute_max_days

    try:
        pool = _dedup_by_venue_id(eligible_corridor_venues(list_venues_fn(geo_region)))
    except Exception:
        return None
    md = compute_max_days(len(pool))
    return md if md >= 1 else None
