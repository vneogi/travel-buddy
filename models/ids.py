"""Single source of truth for ID generation formats.

The format of each ID must be accepted by the corresponding column type
in migration 0014 (all TEXT, no UUID).
"""

import uuid


def generate_node_id() -> str:
    """8-char hex string for trip_node.node_id (TEXT column)."""
    return str(uuid.uuid4())[:8]


def generate_edge_id() -> str:
    """Full UUID string for trip_edge.edge_id (TEXT column)."""
    return str(uuid.uuid4())
