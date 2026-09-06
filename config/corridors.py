"""SPEC-36: Corridor registry.

The single source of truth for multi-city corridor definitions.
Validation and advertisement must read this registry; router logic
must not hardcode city order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class Corridor:
    """Immutable corridor definition."""

    corridor_id: str
    display_name: str
    geo_regions: tuple[str, ...]
    max_days: int
    max_days_per_segment: int


CORRIDORS: Dict[str, Corridor] = {
    "laos_northbound_v1": Corridor(
        corridor_id="laos_northbound_v1",
        display_name="Vientiane to Luang Prabang",
        geo_regions=(
            "vientiane_laos",
            "vang_vieng_laos",
            "luang_prabang_laos",
        ),
        max_days=7,
        max_days_per_segment=3,
    ),
}


def require_corridor(corridor_id: str) -> Corridor:
    """Look up a corridor by ID. Raises KeyError if unknown."""
    if corridor_id not in CORRIDORS:
        raise KeyError(corridor_id)
    return CORRIDORS[corridor_id]


def get_all_corridor_ids() -> frozenset[str]:
    """Return all registered corridor IDs."""
    return frozenset(CORRIDORS.keys())
