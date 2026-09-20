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

from config.interests import TRIP_SPAN_SANITY_DAYS
from config.corridors import CORRIDORS, Corridor, require_corridor
from config.regions import REGIONS, require_region
from models.schemas import (
    CurrentContext,
    SupportedCorridor,
    TripNode,
    TripSegment,
    TripSegmentIn,
)
from services.catalog_itinerary import (
    CATEGORY_BUCKETS,
    eligible_corridor_venues,
    duration_for,
    flatten_opening_hours,
    pack_day,
)
from services.opening_hours import HoursResult, hours_for_slot


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
        raise InvalidCorridor(f"Segments must follow corridor order: {expected}. Got: {provided}.")

    total_days = 0
    prev_ends_on: date | None = None

    for seg in segments:
        if seg.starts_on > seg.ends_on:
            raise InvalidCorridor(
                f"Segment {seg.geo_region}: start {seg.starts_on} is after end {seg.ends_on}."
            )
        span = (seg.ends_on - seg.starts_on).days + 1
        if span < 1 or span > TRIP_SPAN_SANITY_DAYS:
            raise InvalidCorridor(
                f"Segment {seg.geo_region}: {span} days exceeds "
                f"the {TRIP_SPAN_SANITY_DAYS}-day safety limit."
            )
        if prev_ends_on is not None and seg.starts_on <= prev_ends_on:
            raise InvalidCorridor(
                f"Segment {seg.geo_region} starts on {seg.starts_on} "
                f"which overlaps or precedes the previous segment ending "
                f"{prev_ends_on}."
            )
        total_days += span
        prev_ends_on = seg.ends_on

    if total_days > TRIP_SPAN_SANITY_DAYS:
        raise InvalidCorridor(
            f"Total {total_days} days exceeds the {TRIP_SPAN_SANITY_DAYS}-day safety limit."
        )

    # SPEC-42: inclusive corridor span (first start through last end),
    # which includes inter-segment gaps.
    if segments:
        inclusive_span = (segments[-1].ends_on - segments[0].starts_on).days + 1
        if inclusive_span > TRIP_SPAN_SANITY_DAYS:
            raise InvalidCorridor(
                f"Inclusive corridor span {inclusive_span} days "
                f"(including gaps) exceeds the "
                f"{TRIP_SPAN_SANITY_DAYS}-day safety limit."
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

    Returns (nodes, stored_segments).  SPEC-42: sparse population with
    a global budget of MAX_AUTO_POPULATED_DAYS across all segments.
    Regions with zero packable venues produce no nodes (not an error).
    """
    all_nodes: list[TripNode] = []
    stored_segments: list[TripSegment] = []

    from config.interests import MAX_AUTO_POPULATED_DAYS
    from services.catalog_itinerary import _select_populated_day_indices

    # SPEC-42: global budget of starter days across the whole corridor.
    global_budget = MAX_AUTO_POPULATED_DAYS

    for seg_in in segments:
        region = require_region(seg_in.geo_region)
        tz = ZoneInfo(region.timezone)
        rows = list_venues_fn(seg_in.geo_region)
        pool = eligible_corridor_venues(rows)

        span = (seg_in.ends_on - seg_in.starts_on).days + 1

        if global_budget > 0 and len(pool) >= CORRIDOR_STOPS_PER_DAY:
            # Probe feasible days using actual segment dates
            feasible = 0
            probe_used: set[str] = set()
            for day_i in range(min(global_budget, span)):
                probe_date = seg_in.starts_on + timedelta(days=day_i)
                probe_start = datetime(
                    probe_date.year,
                    probe_date.month,
                    probe_date.day,
                    9,
                    0,
                    0,
                    tzinfo=tz,
                ).astimezone(timezone.utc)
                day_nodes, probe_used = pack_day(
                    candidates=pool,
                    target_count=CORRIDOR_STOPS_PER_DAY,
                    day_start_utc=probe_start,
                    geo_region=seg_in.geo_region,
                    used_ids=probe_used,
                )
                if len(day_nodes) < CORRIDOR_STOPS_PER_DAY:
                    break
                feasible += 1

            day_indices = _select_populated_day_indices(span, min(feasible, global_budget))

            used_ids: set[str] = set()
            for day_offset in day_indices:
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

                day_nodes, used_ids = pack_day(
                    candidates=pool,
                    target_count=CORRIDOR_STOPS_PER_DAY,
                    day_start_utc=start_dt,
                    geo_region=seg_in.geo_region,
                    used_ids=used_ids,
                )

                if len(day_nodes) < CORRIDOR_STOPS_PER_DAY:
                    break
                all_nodes.extend(day_nodes)
                global_budget -= 1

        stored_segments.append(
            TripSegment(
                geo_region=seg_in.geo_region,
                starts_on=seg_in.starts_on,
                ends_on=seg_in.ends_on,
            )
        )

    return all_nodes, stored_segments


def advertised_corridors(list_venues_fn) -> list[dict]:
    """Corridors where every city has at least one eligible venue.

    SPEC-42: catalog capacity no longer hides a corridor.  A corridor is
    advertised when each region has at least one eligible venue, not when
    it can fill every configured date.
    """
    result = []
    for cid, corridor in CORRIDORS.items():
        ok = True
        for region_code in corridor.geo_regions:
            try:
                rows = list_venues_fn(region_code)
                pool = eligible_corridor_venues(rows)
                if not pool:
                    ok = False
                    break
            except Exception:
                ok = False
                break
        if ok:
            result.append(
                SupportedCorridor(
                    corridor_id=corridor.corridor_id,
                    display_name=corridor.display_name,
                    geo_regions=list(corridor.geo_regions),
                    max_days=corridor.max_days,
                    max_days_per_segment=corridor.max_days_per_segment,
                    max_days_per_region=corridor.max_days_per_region,
                ).model_dump()
            )
    return result
