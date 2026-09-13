"""Server-owned registry for guided create trip (SPEC-40).

One source of truth for party types, interest options, and the
product ceiling on single-city range days.  Validation, ranking,
and the advertised options response all consume this registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Sequence

# ---------------------------------------------------------------------------
# Product ceiling
# ---------------------------------------------------------------------------

MAX_DAYS_CEILING = 5
"""Hard product limit on single-city range days."""

VENUES_PER_DAY = 4
"""Exact unique catalog venues placed per day in range mode."""


def compute_max_days(eligible_count: int) -> int:
    """Advertised max for a region: min(ceiling, floor(eligible / per_day))."""
    return min(MAX_DAYS_CEILING, eligible_count // VENUES_PER_DAY)


# ---------------------------------------------------------------------------
# Party types (SPEC-03 vocabulary)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PartyType:
    id: str
    label: str


PARTY_TYPES: Sequence[PartyType] = (
    PartyType(id="solo", label="Solo"),
    PartyType(id="couple", label="Couple"),
    PartyType(id="friends", label="Friends"),
    PartyType(id="family_young_kids", label="Family with young kids"),
    PartyType(id="family_teens", label="Family with teens"),
    PartyType(id="multigen", label="Multi-generation"),
)

PARTY_TYPE_IDS: FrozenSet[str] = frozenset(p.id for p in PARTY_TYPES)

# ---------------------------------------------------------------------------
# Interest options
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Interest:
    id: str
    label: str
    category_matches: FrozenSet[str] = field(default_factory=frozenset)
    vibe_tag_matches: FrozenSet[str] = field(default_factory=frozenset)


INTERESTS: Sequence[Interest] = (
    Interest(
        id="history_culture",
        label="History & culture",
        category_matches=frozenset({"temple", "museum", "gallery"}),
        vibe_tag_matches=frozenset({"historical", "spiritual"}),
    ),
    Interest(
        id="food_markets",
        label="Food & markets",
        category_matches=frozenset({"restaurant", "cafe", "street_food", "market"}),
        vibe_tag_matches=frozenset({"authentic", "local_favourite"}),
    ),
    Interest(
        id="nature_scenery",
        label="Nature & scenery",
        category_matches=frozenset({"nature", "viewpoint", "walking_area", "river_activity"}),
        vibe_tag_matches=frozenset({"scenic", "riverside", "photogenic"}),
    ),
    Interest(
        id="adventure_outdoors",
        label="Adventure & outdoors",
        category_matches=frozenset({"river_activity", "nature", "walking_area"}),
        vibe_tag_matches=frozenset({"adventurous", "lively"}),
    ),
    Interest(
        id="arts_crafts",
        label="Arts & crafts",
        category_matches=frozenset({"craft_workshop", "gallery", "museum"}),
        vibe_tag_matches=frozenset({"authentic", "hidden"}),
    ),
    Interest(
        id="wellness_slow",
        label="Wellness & slow travel",
        category_matches=frozenset({"massage_spa", "cafe", "nature"}),
        vibe_tag_matches=frozenset({"quiet", "romantic"}),
    ),
    Interest(
        id="nightlife_social",
        label="Nightlife & social",
        category_matches=frozenset({"bar", "restaurant", "community_space"}),
        vibe_tag_matches=frozenset({"lively", "upscale"}),
    ),
)

INTEREST_IDS: FrozenSet[str] = frozenset(i.id for i in INTERESTS)
_INTEREST_MAP: Dict[str, Interest] = {i.id: i for i in INTERESTS}

MAX_INTERESTS = 3
"""Traveller may choose zero to three interests per trip."""


def get_interest(interest_id: str) -> Interest:
    """Look up an interest by ID; raises KeyError if unknown."""
    return _INTEREST_MAP[interest_id]


def validate_interest_ids(ids: Sequence[str]) -> List[str]:
    """Return validated interest IDs or raise ValueError."""
    if len(ids) > MAX_INTERESTS:
        raise ValueError(f"At most {MAX_INTERESTS} interests allowed, got {len(ids)}")
    bad = [i for i in ids if i not in INTEREST_IDS]
    if bad:
        raise ValueError(f"Unknown interest IDs: {bad}")
    # Deduplicate preserving order
    seen: set[str] = set()
    result: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            result.append(i)
    return result
