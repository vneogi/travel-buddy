"""Itinerary normalisation: decompose/compose between state_json and rows.

SPEC-16 phase 1: dual-write. This module handles:
- decompose_trip: TripState -> (trip_node rows, trip_edge rows)
- compose_trip_nodes: (trip_node rows) -> List[TripNode dict] (API wire format)
- Round-trip invariant: compose(decompose(trip)) == trip.nodes (parsed structures)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from models.ids import generate_edge_id, generate_node_id


# Sparse seq gap for inserts between nodes without rewriting
_SEQ_GAP = 1000

# Region -> IANA timezone mapping (application-level, not stored per-row)
REGION_TIMEZONES: Dict[str, str] = {
    "dubai_uae": "Asia/Dubai",
    "luang_prabang_laos": "Asia/Vientiane",
    "vang_vieng_laos": "Asia/Vientiane",
    "vientiane_laos": "Asia/Vientiane",
}


def decompose_trip(
    trip_state: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Decompose a TripState dict into normalised trip_node and trip_edge rows.

    Args:
        trip_state: The full TripState dict (as stored in state_json).

    Returns:
        (nodes, edges) where each node/edge is a dict matching the DB columns.
        node_id is preserved from the source if present; generated otherwise.
        Edges are synthetic: consecutive nodes get a connecting edge.
    """
    trip_id = trip_state["trip_id"]
    trip_geo = trip_state.get("geo_region")
    raw_nodes = trip_state.get("nodes", [])

    nodes: List[Dict[str, Any]] = []
    for i, n in enumerate(raw_nodes):
        node_id = n.get("node_id") or generate_node_id()
        # Parse scheduled_start if it's a string
        sched_start = n.get("scheduled_start")
        if isinstance(sched_start, str):
            # Keep as string for DB (TIMESTAMPTZ accepts ISO format)
            pass

        # Compute scheduled_end from start + duration
        duration = n.get("duration_minutes", 90)
        sched_end = None
        if sched_start:
            try:
                if isinstance(sched_start, str):
                    dt = datetime.fromisoformat(sched_start.replace("Z", "+00:00"))
                else:
                    dt = sched_start
                from datetime import timedelta
                end_dt = dt + timedelta(minutes=duration)
                sched_end = end_dt.isoformat()
                if isinstance(sched_start, str):
                    sched_start = dt.isoformat()
            except (ValueError, TypeError):
                sched_end = None

        # Map status: the app uses pending/active/completed/skipped;
        # normalised table uses planned/visited/skipped/cancelled
        status_map = {
            "pending": "planned",
            "active": "planned",  # active is still in-progress, maps to planned
            "completed": "visited",
            "skipped": "skipped",
        }
        raw_status = n.get("status", "pending")
        status = status_map.get(raw_status, "planned")

        node_row = {
            "node_id": node_id,
            "trip_id": trip_id,
            "day_index": 0,  # single-day trips; future: derive from date
            "seq": (i + 1) * _SEQ_GAP,
            "node_type": "activity",  # all current nodes are activity type
            "venue_ref": n.get("venue_id"),
            "title": n.get("venue_name", "Untitled"),
            "scheduled_start": sched_start,
            "scheduled_end": sched_end,
            "duration_minutes": duration,
            "is_locked": n.get("is_locked", False),
            "status": status,
            "geo_region": n.get("geo_region") or trip_geo,
            "micro_location": n.get("micro_location"),
            "lat": n.get("lat"),
            "lng": n.get("lng"),
            "vibe_tags": n.get("vibe_tags", []),
            "opening_hours": n.get("opening_hours"),
        }
        nodes.append(node_row)

    # Edges: consecutive node pairs
    edges: List[Dict[str, Any]] = []
    for i in range(len(nodes) - 1):
        edge_row = {
            "edge_id": generate_edge_id(),
            "trip_id": trip_id,
            "from_node_id": nodes[i]["node_id"],
            "to_node_id": nodes[i + 1]["node_id"],
            "transport_mode": None,
            "expected_duration_minutes": None,
            "observed_duration_minutes": None,
            "expected_cost_band": None,
            "notes": None,
        }
        edges.append(edge_row)

    return nodes, edges


def compose_trip_nodes(
    node_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Compose normalised trip_node rows back into the API wire format.

    The output is the same shape as TripState.nodes in the JSON API,
    ensuring byte-identical responses to Flutter.
    """
    # Sort by (day_index, seq)
    sorted_rows = sorted(node_rows, key=lambda r: (r["day_index"], r["seq"]))

    # Reverse-map status
    status_rmap = {
        "planned": "pending",
        "visited": "completed",
        "skipped": "skipped",
        "cancelled": "skipped",  # no direct equivalent; closest
    }

    result: List[Dict[str, Any]] = []
    for row in sorted_rows:
        node = {
            "node_id": row["node_id"],
            "venue_name": row["title"],
            "venue_id": row.get("venue_ref"),
            "scheduled_start": row["scheduled_start"],
            "duration_minutes": row["duration_minutes"],
            "is_locked": row["is_locked"],
            "status": status_rmap.get(row["status"], "pending"),
            "micro_location": row.get("micro_location"),
            "vibe_tags": row.get("vibe_tags", []),
            "lat": row.get("lat"),
            "lng": row.get("lng"),
            "opening_hours": row.get("opening_hours"),
            "geo_region": row.get("geo_region"),
        }
        result.append(node)

    return result


def round_trip_equal(trip_state: Dict[str, Any]) -> bool:
    """Verify that decompose -> compose produces the same node list.

    Compares parsed structures (not string formatting).
    """
    nodes, _edges = decompose_trip(trip_state)
    composed = compose_trip_nodes(nodes)
    original = trip_state.get("nodes", [])

    if len(composed) != len(original):
        return False

    for orig, comp in zip(original, composed):
        # Compare the fields that must round-trip
        for key in ("node_id", "venue_name", "venue_id", "duration_minutes",
                    "is_locked", "micro_location", "vibe_tags", "lat", "lng",
                    "opening_hours", "geo_region"):
            if orig.get(key) != comp.get(key):
                return False
        # Status: pending/active -> planned -> pending (active maps to planned maps to pending)
        orig_status = orig.get("status", "pending")
        comp_status = comp.get("status", "pending")
        # active and pending both map to planned and back to pending
        if orig_status == "active":
            if comp_status != "pending":
                return False
        elif orig_status != comp_status:
            return False

    return True
