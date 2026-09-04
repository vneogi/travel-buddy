"""Region definitions for multi-city support.

Each geo_region code maps to the metadata needed for venue search,
prompt generation, and coordinate defaults. Add new regions here;
no other file needs changing for basic geographic expansion.
"""

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class Region:
    """Immutable region metadata."""

    code: str
    display_name: str
    country: str
    default_lat: float
    default_lng: float
    currency: str
    language_hint: str  # For LLM system prompt
    timezone: str


# --- Region Registry ----------------------------------------------------------
# Add new regions here. Trip creation sets trip.geo_region = one of these codes.

REGIONS: Dict[str, Region] = {
    "dubai_uae": Region(
        code="dubai_uae",
        display_name="Dubai",
        country="UAE",
        default_lat=25.1972,
        default_lng=55.2744,
        currency="AED",
        language_hint="Arabic/English bilingual; most venues have English-speaking staff",
        timezone="Asia/Dubai",
    ),
    "luang_prabang_laos": Region(
        code="luang_prabang_laos",
        display_name="Luang Prabang",
        country="Laos",
        default_lat=19.8856,
        default_lng=102.1347,
        currency="LAK",
        language_hint="Lao; limited English outside tourist areas; French sometimes understood",
        timezone="Asia/Vientiane",
    ),
    "vang_vieng_laos": Region(
        code="vang_vieng_laos",
        display_name="Vang Vieng",
        country="Laos",
        default_lat=18.9220,
        default_lng=102.4474,
        currency="LAK",
        language_hint="Lao; tourist English common on main strip; limited elsewhere",
        timezone="Asia/Vientiane",
    ),
    "vientiane_laos": Region(
        code="vientiane_laos",
        display_name="Vientiane",
        country="Laos",
        default_lat=17.9757,
        default_lng=102.6331,
        currency="LAK",
        language_hint="Lao; French heritage; more English in expat areas",
        timezone="Asia/Vientiane",
    ),
}

DEFAULT_REGION = "dubai_uae"


def require_region(code: str) -> Region:
    """Look up a region by code. Unknown codes raise KeyError.

    Create-trip must use this, not get_region. get_region falls back to Dubai
    and would stamp a Laos trip onto Dubai venues.
    """
    if code not in REGIONS:
        raise KeyError(code)
    return REGIONS[code]


def get_region(code: str) -> Region:
    """Look up region by code, falling back to Dubai.

    Unsafe as a create allowlist. Prefer require_region when the caller must
    refuse unknown cities.
    """
    return REGIONS.get(code, REGIONS[DEFAULT_REGION])


def get_all_region_codes() -> frozenset:
    """Return all registered region codes (for loader validation)."""
    return frozenset(REGIONS.keys())
