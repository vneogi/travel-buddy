"""SPEC-43 Gap 9: GPS plausibility on signal ingest.

GPS is optional. When a client sends lat/lng in value_json they must be a
finite, in-range pair. For trip-linked presence claims (visited_confirmed,
node_skipped) the point must also be near the matched itinerary node.
Coordinates are never logged.
"""

from __future__ import annotations

import math
from typing import Optional

from services.db_provider import db_service
from services.trip_ownership import find_trip_node

MAX_GPS_OFFSET_M = 50000  # 50 km
MAX_ACCURACY_M = 10000

EARTH_RADIUS_M = 6371008.8

# Types that may carry lat/lng/accuracy_m in value_json this slice.
GPS_CAPABLE_SIGNAL_TYPES = frozenset(
    {"visited_confirmed", "node_skipped", "user_loved", "dish_loved", "dish_ordered"}
)
# Presence claims: distance to the matched trip node is checked.
GPS_DISTANCE_CHECKED_TYPES = frozenset({"visited_confirmed", "node_skipped"})

GPS_RANGE_REASON = "gps: lat/lng out of range"
GPS_PAIR_REASON = "gps: lat and lng must be sent together"
GPS_ACCURACY_REASON = "gps: accuracy_m out of range"
GPS_TOO_FAR_REASON = "gps: coordinates too far from trip place"


def _finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in meters."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def gps_range_error(value_json: Optional[dict]) -> Optional[str]:
    """Reject reason for malformed or out-of-range GPS, else None.

    Missing lat and lng together is fine (GPS optional).
    """
    vj = value_json or {}
    has_lat, has_lng = "lat" in vj, "lng" in vj
    if not has_lat and not has_lng:
        if "accuracy_m" in vj:
            return GPS_PAIR_REASON
        return None
    if has_lat != has_lng:
        return GPS_PAIR_REASON
    lat, lng = vj["lat"], vj["lng"]
    if not (_finite_number(lat) and _finite_number(lng)):
        return GPS_RANGE_REASON
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return GPS_RANGE_REASON
    if "accuracy_m" in vj:
        acc = vj["accuracy_m"]
        if not _finite_number(acc) or not (0 < acc <= MAX_ACCURACY_M):
            return GPS_ACCURACY_REASON
    return None


def gps_distance_error(
    signal_type: str, trip_id: Optional[str], place_ref: str, value_json: Optional[dict]
) -> Optional[str]:
    """Reject reason if a presence claim's GPS is far from the matched node."""
    vj = value_json or {}
    if signal_type not in GPS_DISTANCE_CHECKED_TYPES or not trip_id:
        return None
    if "lat" not in vj or "lng" not in vj:
        return None
    lat, lng = vj["lat"], vj["lng"]
    # Range is owned by gps_range_error; distance is only defined for a
    # finite in-range point.
    if not (_finite_number(lat) and _finite_number(lng)):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return None
    try:
        trip = db_service.get_trip(trip_id)
    except Exception:  # noqa: BLE001 -- trip-place already ran; treat as no node
        return None
    node = find_trip_node(trip, place_ref)
    if node is None:
        return None
    node_lat, node_lng = getattr(node, "lat", None), getattr(node, "lng", None)
    if not (_finite_number(node_lat) and _finite_number(node_lng)):
        return None  # node has no coords: range only
    if haversine_m(lat, lng, node_lat, node_lng) > MAX_GPS_OFFSET_M:
        return GPS_TOO_FAR_REASON
    return None


def gps_error(
    signal_type: str, trip_id: Optional[str], place_ref: str, value_json: Optional[dict]
) -> Optional[str]:
    """Range check for GPS-capable types, then distance for presence claims."""
    if signal_type not in GPS_CAPABLE_SIGNAL_TYPES:
        return None
    return gps_range_error(value_json) or gps_distance_error(
        signal_type, trip_id, place_ref, value_json
    )
