"""Destination timezone conversions using ZoneInfo.

config.REGIONS is the single source of truth for region -> IANA timezone.
This module resolves a geo_region code to a ZoneInfo and converts UTC
datetimes with proper astimezone (never replace(tzinfo=...)).
"""

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from config.regions import REGIONS


def destination_tz(geo_region: Optional[str]) -> Optional[ZoneInfo]:
    """Return the ZoneInfo for a geo_region, or None if unknown."""
    if geo_region is None:
        return None
    region = REGIONS.get(geo_region)
    if region is None:
        return None
    return ZoneInfo(region.timezone)


def to_destination_local(utc_dt: datetime, geo_region: Optional[str]) -> datetime:
    """Convert a UTC datetime to destination-local.

    Uses astimezone for correct conversion. Falls back to UTC when the
    region is unknown (safe for hour comparison -- matches prior behaviour).
    """
    tz = destination_tz(geo_region)
    if tz is None:
        return utc_dt
    # Ensure the input is tz-aware UTC before converting.
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    return utc_dt.astimezone(tz)
