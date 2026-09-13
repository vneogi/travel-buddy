"""Lightweight region-to-UTC-offset for opening-hours validation.

The scheduler checks venue opening hours against the scheduled time.
Times are stored in UTC; opening hours are in destination-local time.
This module converts UTC datetimes to destination-local for comparison.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

# Map geo_region identifiers to UTC offset in hours.
# DST is not relevant for current corridors (ICT/GST are fixed).
REGION_OFFSETS: dict[str, int] = {
    "dubai_uae": 4,  # GST  UTC+4
    "vientiane_laos": 7,  # ICT  UTC+7
    "luang_prabang_laos": 7,
    "vang_vieng_laos": 7,
}


def destination_offset(geo_region: Optional[str]) -> Optional[timedelta]:
    """Return the UTC offset for a geo_region, or None if unknown."""
    if geo_region is None:
        return None
    hours = REGION_OFFSETS.get(geo_region)
    if hours is None:
        return None
    return timedelta(hours=hours)


def to_destination_local(utc_dt: datetime, geo_region: Optional[str]) -> datetime:
    """Convert a UTC datetime to destination-local.

    Falls back to UTC if the region is unknown (safe for hour comparison
    because that was the prior behaviour).
    """
    offset = destination_offset(geo_region)
    if offset is None:
        return utc_dt
    tz = timezone(offset)
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz)
