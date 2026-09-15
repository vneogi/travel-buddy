"""Deterministic walking-time helper for itinerary feasibility (SPEC-41 A3b).

Single source of truth for intra-day transfer estimates used by:
  - pack_day (create / range / corridor packing)
  - swap search and apply (state machine)
  - reschedule_and_validate (scheduler)

Contract:
  * Haversine great-circle distance.
  * Walking speed 5.0 km/h.
  * Minutes = ceil(distance / speed * 60), floored to MINIMUM_TRANSFER_MINUTES.
  * Same inputs always produce the same integer.
  * No randomness, no server clock, no traffic, no network, no LLM, no Maps API.
  * Missing or non-finite coordinates raise ValueError.
"""

import math
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WALKING_SPEED_KMH: float = 5.0
"""Assumed walking speed in km/h."""

MINIMUM_TRANSFER_MINUTES: int = 5
"""Floor applied to every transfer estimate."""

_EARTH_RADIUS_KM: float = 6371.0


# ---------------------------------------------------------------------------
# Haversine (moved from maps_service to avoid duplicating the formula)
# ---------------------------------------------------------------------------


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in kilometres between two WGS-84 points."""
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS_KM * c


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------


def walking_minutes(
    origin_lat: Optional[float],
    origin_lng: Optional[float],
    dest_lat: Optional[float],
    dest_lng: Optional[float],
) -> int:
    """Deterministic walking transfer time between two points.

    Returns an integer number of minutes (>= MINIMUM_TRANSFER_MINUTES).
    Raises ValueError when any coordinate is None or non-finite.
    """
    for name, val in [
        ("origin_lat", origin_lat),
        ("origin_lng", origin_lng),
        ("dest_lat", dest_lat),
        ("dest_lng", dest_lng),
    ]:
        if val is None or not math.isfinite(val):
            raise ValueError(f"{name} must be a finite number, got {val!r}")

    dist_km = haversine_km(origin_lat, origin_lng, dest_lat, dest_lng)
    raw_minutes = math.ceil(dist_km / WALKING_SPEED_KMH * 60)
    return max(MINIMUM_TRANSFER_MINUTES, raw_minutes)
