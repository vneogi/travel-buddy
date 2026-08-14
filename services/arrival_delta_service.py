"""Server-side derivation of arrival_delta from visited_confirmed signals.

arrival_delta is the difference in MINUTES between when the user confirmed
they arrived (visited_confirmed.captured_at) and when they were scheduled
to arrive (node.scheduled_start). Positive = late, negative = early.

This turns one user tap into two data points:
  1. visited_confirmed (explicit, from client)
  2. arrival_delta (derived, from server)

The derived signal:
  - signal_type: 'arrival_delta'
  - value_numeric: minutes (float, rounded to 1 decimal)
  - place_ref: same as the visited_confirmed signal
  - trip_id: same as the visited_confirmed signal
  - signal_id: deterministic from source signal_id (idempotent re-derivation)
  - captured_at: same as the visited_confirmed signal
  - provenance in value_json: {method: 'server_derived', source_signal_id: ...}

Design:
  - Never fails ingest of the source signal. If derivation fails (trip not
    found, node not found, etc.), we log and move on.
  - Idempotent: re-processing the same visited_confirmed produces the same
    arrival_delta signal_id (hash of source), so duplicate insert is a no-op.
  - Called synchronously after successful ingest of visited_confirmed.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from services.db_provider import db_service

logger = logging.getLogger(__name__)


def derive_arrival_delta(
    source_signal_id: str,
    user_id: str,
    place_ref: str,
    captured_at: datetime,
    trip_id: Optional[str],
) -> Optional[float]:
    """Derive and persist an arrival_delta signal from a visited_confirmed.

    Returns the delta in minutes if successfully derived, None otherwise.
    Never raises -- derivation failure must not break ingest.
    """
    if not trip_id:
        logger.debug(
            "arrival_delta: no trip_id on visited_confirmed %s, skipping", source_signal_id
        )
        return None

    try:
        trip = db_service.get_trip(trip_id)
        if not trip:
            logger.debug(
                "arrival_delta: trip %s not found for signal %s", trip_id, source_signal_id
            )
            return None

        # Find the node matching place_ref (by venue_id or venue_name)
        target_node = _find_node_for_place(trip.nodes, place_ref)
        if not target_node:
            logger.debug(
                "arrival_delta: no node matching place_ref=%s in trip %s",
                place_ref,
                trip_id,
            )
            return None

        # Compute delta in minutes
        delta_minutes = _compute_delta(captured_at, target_node.scheduled_start)

        # Build deterministic signal_id for idempotency
        derived_signal_id = _deterministic_id(source_signal_id)

        # Ensure captured_at is tz-aware
        if captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=timezone.utc)

        # Persist the derived signal
        db_service.record_signal(
            user_id=user_id,
            signal_id=derived_signal_id,
            signal_type="arrival_delta",
            place_ref=place_ref,
            value_text=None,
            value_numeric=delta_minutes,
            value_json={
                "method": "server_derived",
                "source_signal_id": source_signal_id,
                "scheduled_start": target_node.scheduled_start.isoformat(),
            },
            captured_at=captured_at,
            trip_id=trip_id,
        )

        logger.info(
            "arrival_delta derived: %.1f min for place_ref=%s (signal %s)",
            delta_minutes,
            place_ref,
            derived_signal_id,
        )
        return delta_minutes

    except Exception as e:
        # Never break ingest. Log and move on.
        logger.warning(
            "arrival_delta derivation failed for signal %s: %s",
            source_signal_id,
            e,
        )
        return None


def _find_node_for_place(nodes, place_ref: str):
    """Find the trip node matching place_ref (venue_id or venue_name)."""
    for node in nodes:
        if node.venue_id and node.venue_id == place_ref:
            return node
        if node.venue_name and node.venue_name.lower() == place_ref.lower():
            return node
    return None


def _compute_delta(actual: datetime, scheduled: datetime) -> float:
    """Compute arrival delta in minutes. Positive = late, negative = early."""
    if actual.tzinfo is None:
        actual = actual.replace(tzinfo=timezone.utc)
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=timezone.utc)
    delta_seconds = (actual - scheduled).total_seconds()
    return round(delta_seconds / 60.0, 1)


def _deterministic_id(source_signal_id: str) -> str:
    """Generate a deterministic UUID-shaped ID from the source signal.

    Ensures re-processing the same visited_confirmed always produces the
    same arrival_delta signal_id (idempotent on re-derivation).
    """
    h = hashlib.sha256(f"arrival_delta:{source_signal_id}".encode()).hexdigest()
    # Format as UUID-shaped: 8-4-4-4-12
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
