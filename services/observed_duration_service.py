"""Server-side derivation of observed_duration_minutes from visited_confirmed pairs.

When a node's arrival is confirmed and the PREVIOUS scheduled node's arrival
was also confirmed, the previous node's observed duration = the span between
the two confirmed arrivals.

Design:
  - Never fails ingest of the source signal. If derivation fails (trip not
    found, node not found, pair incomplete), we log and move on.
  - Idempotent: writing the same value is a no-op.
  - Called synchronously after successful ingest of visited_confirmed,
    right after derive_arrival_delta.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from services.db_provider import db_service

logger = logging.getLogger(__name__)


def derive_observed_duration(
    source_signal_id: str,
    user_id: str,
    place_ref: str,
    captured_at: datetime,
    trip_id: Optional[str],
) -> Optional[float]:
    """Derive and persist observed_duration_minutes on the previous node.

    Returns the duration in minutes if successfully derived, None otherwise.
    Never raises -- derivation failure must not break ingest.
    """
    if not trip_id:
        logger.debug(
            "observed_duration: no trip_id on visited_confirmed %s, skipping",
            source_signal_id,
        )
        return None

    try:
        trip = db_service.get_trip(trip_id)
        if not trip:
            logger.debug(
                "observed_duration: trip %s not found for signal %s",
                trip_id,
                source_signal_id,
            )
            return None

        # Find the target node for the current confirmation
        target_node = _find_node_for_place(trip.nodes, place_ref)
        if not target_node:
            logger.debug(
                "observed_duration: no node matching place_ref=%s in trip %s",
                place_ref,
                trip_id,
            )
            return None

        # Find the node scheduled immediately BEFORE the target
        prev_node = _find_previous_node(trip.nodes, target_node)
        if not prev_node:
            logger.debug(
                "observed_duration: no previous node before %s in trip %s",
                place_ref,
                trip_id,
            )
            return None

        # Look up the previous node's visited_confirmed
        prev_place_ref = prev_node.venue_id or prev_node.venue_name
        prev_confirmed = db_service.get_visited_confirmed_for_node(
            trip_id=trip_id, place_ref=prev_place_ref
        )
        if not prev_confirmed:
            logger.debug(
                "observed_duration: previous node %s has no visited_confirmed yet",
                prev_place_ref,
            )
            return None

        # Compute duration = current captured_at - prev confirmed captured_at
        if captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=timezone.utc)

        prev_cap_str = prev_confirmed["captured_at"]
        if isinstance(prev_cap_str, str):
            prev_cap = datetime.fromisoformat(prev_cap_str)
        else:
            prev_cap = prev_cap_str
        if prev_cap.tzinfo is None:
            prev_cap = prev_cap.replace(tzinfo=timezone.utc)

        duration_seconds = (captured_at - prev_cap).total_seconds()
        if duration_seconds <= 0:
            logger.debug(
                "observed_duration: negative or zero span (%.1fs) for %s, skipping",
                duration_seconds,
                source_signal_id,
            )
            return None

        duration_minutes = round(duration_seconds / 60.0, 1)

        # Write on the PREVIOUS node (not the target)
        db_service.update_node_observed_duration(
            trip_id=trip_id,
            node_id=prev_node.node_id,
            duration_minutes=duration_minutes,
        )

        logger.info(
            "observed_duration: %.1f min on node %s (triggered by signal %s)",
            duration_minutes,
            prev_node.node_id,
            source_signal_id,
        )
        return duration_minutes

    except Exception as e:
        # Never break ingest. Log and move on.
        logger.warning(
            "observed_duration derivation failed for signal %s: %s",
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


def _find_previous_node(nodes, target_node):
    """Find the node scheduled immediately before the target in the trip.

    Nodes are ordered by scheduled_start. Returns the node just before
    the target, or None if the target is the first.
    """
    sorted_nodes = sorted(nodes, key=lambda n: n.scheduled_start)
    for i, node in enumerate(sorted_nodes):
        if node.node_id == target_node.node_id:
            return sorted_nodes[i - 1] if i > 0 else None
    return None
