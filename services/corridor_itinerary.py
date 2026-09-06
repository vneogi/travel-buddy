"""SPEC-36: Deterministic corridor itinerary builder.

Builds a multi-city trip from the corridor registry. Each day gets
exactly four unique catalog venues. The whole build validates before
any persistence call.

Does not call hybrid search, the LLM, or consume reroute quota.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import List, Sequence
from zoneinfo import ZoneInfo

from config.corridors import CORRIDORS, Corridor, require_corridor
from config.regions import REGIONS, require_region
from models.schemas import (
    CurrentContext,
    TripNode,
    TripSegment,
    TripSegmentIn,
)
from services.catalog_itinerary import (
    CATEGORY_BUCKETS,
    eligible_corridor_venues,
    duration_for,
    flatten_opening_hours,
)


CORRIDOR_STOPS_PER_DAY = 4


class InvalidCorridor(ValueError):
    """Request shape, order, or date validation failure."""


class UnsupportedCorridor(ValueError):
    """Catalog does not have enough eligible venues."""


def validate_corridor_segments(
    segments: List[TripSegmentIn],
    corridor: Corridor,
) -> None:
    """Validate segment list against corridor rules.

    Raises InvalidCorridor with a user-safe message on any failure.
    """
    expected = list(corridor.geo_regions)
    provided = [s.geo_region for s in segments]

    if provided != expected:
        raise InvalidCorridor(
            f"Segments must follow corridor order: {expected}. " f"Got: {provided}."
        )

    total_days = 0
    prev_ends_on: date | None = None

    for seg in segments:
        if seg.starts_on > seg.ends_on:
            raise InvalidCorridor(
                f"Segment {seg.geo_region}: start {seg.starts_on} is after " f"end {seg.ends_on}."
            )
        span = (seg.ends_on - seg.starts_on).days + 1
        if span < 1 or span > corridor.max_days_per_segment:
            raise InvalidCorridor(
                f"Segment {seg.geo_region}: {span} days; must be 1 to "
                f"{corridor.max_days_per_segment}."
            )
        if prev_ends_on is not None and seg.starts_on <= prev_ends_on:
            raise InvalidCorridor(
                f"Segment {seg.geo_region} starts on {seg.starts_on} "
                f"which overlaps or precedes the previous segment ending "
                f"{prev_ends_on}."
            )
        total_days += span
        prev_ends_on = seg.ends_on

    if total_days > corridor.max_days:
        raise InvalidCorridor(
            f"Total {total_days} days exceeds corridor maximum of " f"{corridor.max_days}."
        )


def _select_corridor_day(
    pool: List[dict],
    used_ids: set[str],
) -> List[dict]:
    """Select exactly CORRIDOR_STOPS_PER_DAY venues, excluding used_ids."""
    chosen: list[dict] = []
    chosen_ids: set[str] = set()
    chosen_names: set[str] = set()

    def _take(row: dict) -> bool:
        key = str(row.get("venue_id") or row["name"])
        name = row["name"]
        if key in used_ids or key in chosen_ids or name in chosen_names:
            return False
        chosen_ids.add(key)
        chosen_names.add(name)
        chosen.append(row)
        return True

    # Bucket-first for diversity
    for bucket in CATEGORY_BUCKETS:
        if len(chosen) >= CORRIDOR_STOPS_PER_DAY:
            break
        match = next(
            (
                row
                for row in pool
                if (row.get("category") or "experience").lower() in bucket
                and str(row.get("venue_id") or row["name"]) not in used_ids
                and str(row.get("venue_id") or row["name"]) not in chosen_ids
            ),
            None,
        )
        if match is not None:
            _take(match)

    # Fill remaining
    for row in pool:
        if len(chosen) >= CORRIDOR_STOPS_PER_DAY:
            break
        _take(row)

    return chosen


def build_corridor_nodes(
    segments: List[TripSegmentIn],
    list_venues_fn,
    corridor: Corridor,
) -> tuple[List[TripNode], List[TripSegment]]:
    """Build all nodes for a corridor trip.

    Returns (nodes, stored_segments). Raises UnsupportedCorridor if any
    segment lacks enough eligible venues. Never persists partial state.
    """
    all_nodes: list[TripNode] = []
    stored_segments: list[TripSegment] = []

    for seg_in in segments:
        region = require_region(seg_in.geo_region)
        tz = ZoneInfo(region.timezone)
        rows = list_venues_fn(seg_in.geo_region)
        pool = eligible_corridor_venues(rows)

        span = (seg_in.ends_on - seg_in.starts_on).days + 1
        needed = span * CORRIDOR_STOPS_PER_DAY
        if len(pool) < needed:
            raise UnsupportedCorridor(
                f"Region {seg_in.geo_region} has {len(pool)} eligible venues "
                f"but needs {needed} for {span} day(s)."
            )

        used_ids: set[str] = set()
        for day_offset in range(span):
            day_date = seg_in.starts_on + timedelta(days=day_offset)
            start_dt = datetime(
                day_date.year,
                day_date.month,
                day_date.day,
                9,
                0,
                0,
                tzinfo=tz,
            ).astimezone(timezone.utc)

            selected = _select_corridor_day(pool, used_ids)
            if len(selected) < CORRIDOR_STOPS_PER_DAY:
                raise UnsupportedCorridor(
                    f"Region {seg_in.geo_region} day {day_date}: only "
                    f"{len(selected)} unique venues available, need "
                    f"{CORRIDOR_STOPS_PER_DAY}."
                )

            # Mark used
            for row in selected:
                used_ids.add(str(row.get("venue_id") or row["name"]))

            cursor = start_dt
            for row in selected:
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
                        geo_region=seg_in.geo_region,
                        names_local=row.get("names_local"),
                        landmarks_local=row.get("landmarks_local"),
                        nearest_landmark=row.get("nearest_landmark"),
                    )
                )
                cursor = cursor + timedelta(minutes=duration + 30)

        stored_segments.append(
            TripSegment(
                geo_region=seg_in.geo_region,
                starts_on=seg_in.starts_on,
                ends_on=seg_in.ends_on,
            )
        )

    return all_nodes, stored_segments


def advertised_corridors(list_venues_fn) -> list[dict]:
    """Corridors where every city can supply one day of venues."""
    result = []
    for cid, corridor in CORRIDORS.items():
        ok = True
        for region_code in corridor.geo_regions:
            try:
                rows = list_venues_fn(region_code)
                pool = eligible_corridor_venues(rows)
                if len(pool) < CORRIDOR_STOPS_PER_DAY:
                    ok = False
                    break
            except Exception:
                ok = False
                break
        if ok:
            result.append(
                {
                    "corridor_id": corridor.corridor_id,
                    "display_name": corridor.display_name,
                    "geo_regions": list(corridor.geo_regions),
                    "max_days": corridor.max_days,
                    "max_days_per_segment": corridor.max_days_per_segment,
                }
            )
    return result
