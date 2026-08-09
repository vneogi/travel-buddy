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


# ─── Region Registry ──────────────────────────────────────────────────────────
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
}

DEFAULT_REGION = "dubai_uae"


def get_region(code: str) -> Region:
    """Look up region by code, falling back to default."""
    return REGIONS.get(code, REGIONS[DEFAULT_REGION])
