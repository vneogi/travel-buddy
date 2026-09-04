"""Deterministic one-day itinerary seed from a city venue catalog (SPEC-32).

Create-trip reads venues by geo_region. It does not call hybrid search, the
LLM, or the reroute quota path.
"""

from datetime import datetime, timedelta
from typing import Iterable, List, Sequence

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


def select_day_venues(rows: Sequence[dict]) -> List[dict]:
    pool = eligible_venues(rows)
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
