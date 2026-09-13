"""SPEC-36: Corridor registry.

The single source of truth for multi-city corridor definitions.
Validation and advertisement must read this registry; router logic
must not hardcode city order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class Corridor:
    """Immutable corridor definition."""

    corridor_id: str
    display_name: str
    geo_regions: tuple[str, ...]
    max_days: int
    max_days_by_region: tuple[tuple[str, int], ...]

    def max_days_for_region(self, geo_region: str) -> int:
        """Return the advertised segment cap for one corridor city."""
        limits = dict(self.max_days_by_region)
        if geo_region not in limits:
            raise KeyError(geo_region)
        return limits[geo_region]

    @property
    def max_days_per_segment(self) -> int:
        """Backward-compatible overall maximum for older clients."""
        return max(limit for _, limit in self.max_days_by_region)

    @property
    def max_days_per_region(self) -> Dict[str, int]:
        """JSON-ready per-city limits for corridor clients."""
        return dict(self.max_days_by_region)


CORRIDORS: Dict[str, Corridor] = {
    "laos_northbound_v1": Corridor(
        corridor_id="laos_northbound_v1",
        display_name="Vientiane to Luang Prabang",
        geo_regions=(
            "vientiane_laos",
            "vang_vieng_laos",
            "luang_prabang_laos",
        ),
        max_days=8,
        max_days_by_region=(
            ("vientiane_laos", 4),
            ("vang_vieng_laos", 3),
            ("luang_prabang_laos", 4),
        ),
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
