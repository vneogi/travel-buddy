"""SPEC-43 Gap 9: one trip-ownership rule for signal ingest and derived writers.

A caller may attach signals or derived facts to a trip only when that trip
exists and ``trip_states.user_id`` (or the in-memory equivalent) equals the
authenticated user. Ingest and the derive services share this helper so the
rule cannot drift.
"""

from __future__ import annotations

import logging
from typing import Optional

from models.schemas import TripState
from services.db_provider import db_service

logger = logging.getLogger(__name__)

TRIP_OWNERSHIP_REJECT_REASON = "trip_id is unknown or not owned by caller (trip ownership)"


def get_owned_trip(trip_id: Optional[str], user_id: str) -> Optional[TripState]:
    """Return the trip only if it exists and belongs to ``user_id``.

    Returns None for a missing/empty trip_id, an unknown trip, another user's
    trip, or any lookup error (fail closed).
    """
    if not trip_id or not user_id:
        return None
    try:
        trip = db_service.get_trip(trip_id)
    except Exception as exc:  # malformed id, backend error: fail closed
        logger.debug("trip ownership lookup failed for %s: %s", trip_id, exc)
        return None
    if trip is None or str(trip.user_id) != str(user_id):
        return None
    return trip


def is_trip_owned_by(trip_id: Optional[str], user_id: str) -> bool:
    """True when ``trip_id`` exists and is owned by ``user_id``."""
    return get_owned_trip(trip_id, user_id) is not None


def _norm_place(value: object) -> str:
    return str(value).strip().casefold() if value is not None else ""


def trip_has_place(trip: Optional[TripState], place_ref: str) -> bool:
    """SPEC-43 Gap 9: True if *place_ref* names a node on *trip*.

    Matches any node venue_id or venue_name, case-insensitive after strip.
    Uncatalogued nodes still match on venue_name. Missing trip -> False.
    """
    if trip is None:
        return False
    target = _norm_place(place_ref)
    if not target:
        return False
    for node in trip.nodes or []:
        for candidate in (getattr(node, "venue_id", None), getattr(node, "venue_name", None)):
            if candidate is not None and _norm_place(candidate) == target:
                return True
    return False


def is_place_on_trip(trip_id: str, place_ref: str) -> bool:
    """SPEC-43 Gap 9: resolve *trip_id* via get_trip and check membership."""
    try:
        trip = db_service.get_trip(trip_id)
    except Exception:  # noqa: BLE001 -- fail closed
        return False
    return trip_has_place(trip, place_ref)


def trip_place_reject_reason(place_ref: str) -> str:
    return f"place: {place_ref!r} is not a node on this trip"
