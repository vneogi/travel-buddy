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


def parse_destination_wall_time(
    raw,
    geo_region: Optional[str],
) -> datetime:
    """Parse a booking wall time as destination-local, return UTC.

    Rules
    -----
    - *raw* is ``str`` or ``datetime``.
    - Naive values (no tzinfo, no ``Z``, no offset) are interpreted as
      destination-local civil time for *geo_region*, then converted to
      UTC with ``astimezone``.
    - Aware values (``Z`` or numeric offset) are converted to UTC with
      ``astimezone`` (never ``replace``).
    - Unknown or missing *geo_region* raises ``ValueError`` so the event
      path can surface the error.  Catalog/packer UTC instants should not
      use this helper.
    """
    tz = destination_tz(geo_region)
    if tz is None:
        raise ValueError(f"Cannot interpret booking wall time: unknown geo_region {geo_region!r}")

    if isinstance(raw, str):
        # Normalise "Z" -> "+00:00" so fromisoformat handles it.
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    elif isinstance(raw, datetime):
        dt = raw
    else:
        raise TypeError(f"Expected str or datetime, got {type(raw).__name__}")

    if dt.tzinfo is None:
        # Naive -> attach destination TZ, then convert to UTC.
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(timezone.utc)
