#!/usr/bin/env python3
"""Multi-region venue loader with vocabulary validation.

Usage:
    python scripts/load_venues.py data/venues_luang_prabang.json [data/venues_*.json] [--dry-run]

Behaviour:
- Validates EVERYTHING before touching the DB. Exit non-zero on any error.
- Rejects the whole file on validation failure (never skip rows silently).
- --dry-run validates and reports without writing.
- Upserts on (name, geo_region) so re-running is idempotent.
- Dishes inserted after venues (FK dependency).
- Prints counts by region and category.
"""

import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

# Allow running from project root or scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.regions import get_all_region_codes
from config.dietary import (
    VALID_ALLERGENS,
    VALID_DIETARY_LABELS,
    check_allergen_conflicts,
)

# ===========================================================================
# Vocabulary (SINGLE SOURCE OF TRUTH for validation)
# ===========================================================================

VALID_CATEGORIES = frozenset(
    {
        "restaurant",
        "cafe",
        "temple",
        "market",
        "nature",
        "activity",
        "museum",
        "bar",
        "hotel_lobby",
        "hospital",
        "pharmacy",
        "transport_hub",
        "embassy",
        "essential_service",
        "massage_spa",
        "night_market",
        "waterfall",
        "viewpoint",
        "cooking_class",
        "street_food",
        "walking_area",
        "river_activity",
        "craft_workshop",
    }
)

VALID_VIBE_TAGS = frozenset(
    {
        "cultural",
        "authentic",
        "energetic",
        "leisurely",
        "adventurous",
        "premium_interiors",
        "artistic",
        "independent",
        "familiar",
        "air_conditioned",
        "outdoor",
        "romantic",
        "spiritual",
        "scenic",
        "lively",
        "quiet",
        "historic",
        "modern",
        "cozy",
        "luxurious",
        "family_friendly",
        "instagram_worthy",
        "hidden_gem",
        "photogenic",
        "local_favourite",
        "touristy",
        "budget",
        "riverside",
        "hidden",
        "upscale",
        "historical",
    }
)

VALID_AUDIENCES = frozenset(
    {
        "solo_traveler",
        "couple",
        "family_with_kids",
        "family_with_teens",
        "executive",
        "backpacker",
        "digital_nomad",
        "group",
        "solo",
        "friends_group",
        "seniors",
        "family_young_kids",
        "family_teens",
        "mobility_limited",
    }
)

VALID_INDOOR_OUTDOOR = frozenset({"indoor", "outdoor", "both", "mixed"})

VALID_PRICE_BANDS = frozenset({"budget", "moderate", "mid", "premium", "luxury", "splurge", "free"})

VALID_CUISINES = frozenset(
    {
        "lao",
        "thai",
        "french",
        "fusion",
        "international",
        "vietnamese",
        "emirati",
        "indian",
        "chinese",
        "japanese",
        "korean",
        "italian",
        "american",
        "middle_eastern",
        "african",
        "bakery",
        "dessert",
        "coffee",
        "smoothie",
        "street_food",
        "french_colonial",
        "drink",
    }
)

# Food categories that may have dishes
FOOD_CATEGORIES = frozenset(
    {
        "restaurant",
        "cafe",
        "bar",
        "night_market",
        "street_food",
        "market",
        "craft_workshop",
    }
)

# Column names the loader writes to venues_rag.  Exposed as a constant so
# tests/test_venue_schema.py can import it rather than maintaining a mirror.
VENUES_RAG_WRITE_COLUMNS = frozenset(
    {
        "audience",
        "bid_weight",
        "category",
        "description",
        "embedding",
        "embedding_model",
        "geo_region",
        "has_aircon",
        "indoor_outdoor",
        "is_sponsored",
        "landmarks_local",
        "lat",
        "lng",
        "micro_location",
        "name",
        "names_local",
        "nearest_landmark",
        "opening_hours_structured",
        "price_band",
        "typical_dwell_minutes",
        "venue_id",
        "vibe_tags",
        "wheelchair_notes",
    }
)

# Venue JSON keys intentionally NOT written to venues_rag.
# A key that appears in data/*.json but is in neither this set nor
# VENUES_RAG_WRITE_COLUMNS will fail test_no_silent_key_drop.
EMBEDDING_MODEL = "text-embedding-3-small"

INTENTIONALLY_NOT_PERSISTED = frozenset(
    {
        # Handled by the venue_dish table (separate upsert below)
        "dishes",
        # Mapped to opening_hours_structured via fallback in the insert dict
        "opening_hours",
        # Provenance metadata consumed by _build_localized_jsonb, not stored directly
        "name_local_source",
        "name_local_ref",
        "nearest_landmark_local_source",
        "nearest_landmark_local_ref",
    }
)

# JSON keys in venue data that map to differently-named DB columns.
# test_no_silent_key_drop uses this to avoid false-drop reports.
JSON_KEY_TO_COLUMN = {
    "name_local": "names_local",
    "nearest_landmark_local": "landmarks_local",
}

# Interim region-to-language mapping.  Superseded by SPEC-13
# (region-locale-registry); delete this constant when SPEC-13 lands.
REGION_CURRENCIES = {
    "luang_prabang_laos": "LAK",
    "vang_vieng_laos": "LAK",
    "vientiane_laos": "LAK",
    "dubai_uae": "AED",
}

REGION_LANGUAGES = {
    "luang_prabang_laos": "lo",
    "vang_vieng_laos": "lo",
    "vientiane_laos": "lo",
    "dubai_uae": "ar",
}

# Valid provenance values for names_local / landmarks_local entries.
VALID_LOCALIZED_SOURCES = frozenset(
    {
        "wikidata",
        "osm",
        "official",
        "manual",
        "generated",
        "field_verified",
    }
)

# Closed vocabulary for venue_external_id.source (concern 2 in DATA_LAYER_ROADMAP).
# Intentionally SEPARATE from VALID_LOCALIZED_SOURCES above -- they overlap
# (both include wikidata, osm) but mean different things.
EXTERNAL_ID_SOURCES = frozenset({"wikidata", "osm", "google", "foursquare"})

# Column names the loader writes to venue_external_id. Same guard pattern as
# VENUES_RAG_WRITE_COLUMNS: a test asserts the payload keys equal this set.
VENUE_DISH_WRITE_COLUMNS = frozenset(
    {
        "dish_id",
        "venue_id",
        "name_en",
        "name_local",
        "names_local",
        "is_signature",
        "cuisine",
        "price_local",
        "price_band",
        "currency_code",
    }
)

VENUE_EXTERNAL_ID_WRITE_COLUMNS = frozenset(
    {
        "venue_id",
        "source",
        "external_id",
        "confidence",
        "verified_at",
    }
)

# Taxonomy vocabularies (concern 6 in DATA_LAYER_ROADMAP).
# The loader validates venue data against these at runtime.
# A test asserts these match the taxonomy_term table exactly.
TAXONOMY_TERMS = {
    "category": frozenset(
        {
            "bar",
            "cafe",
            "craft_workshop",
            "hospital",
            "market",
            "massage_spa",
            "museum",
            "nature",
            "pharmacy",
            "restaurant",
            "river_activity",
            "street_food",
            "temple",
            "transport_hub",
            "viewpoint",
            "walking_area",
        }
    ),
    "vibe_tag": frozenset(
        {
            "adventurous",
            "authentic",
            "budget",
            "hidden",
            "historical",
            "lively",
            "local_favourite",
            "photogenic",
            "quiet",
            "riverside",
            "romantic",
            "scenic",
            "spiritual",
            "touristy",
            "upscale",
        }
    ),
    "audience": frozenset(
        {
            "couple",
            "family_teens",
            "family_young_kids",
            "friends_group",
            "mobility_limited",
            "seniors",
            "solo",
        }
    ),
    "price_band": frozenset({"budget", "free", "mid", "splurge"}),
    "indoor_outdoor": frozenset({"indoor", "mixed", "outdoor"}),
    # Dish vocabularies (seeded from laos_dish_glossary.json)
    "cuisine": frozenset(
        {
            "drink",
            "french_colonial",
            "lao",
            "vietnamese",
        }
    ),
    "dish_type": frozenset(
        {
            "alcoholic_drink",
            "bread_pastry",
            "coffee_tea",
            "dessert",
            "grill",
            "noodle_soup",
            "rice_dish",
            "salad",
            "snack",
            "soft_drink",
            "stew",
            "street_snack",
        }
    ),
    "spice_level": frozenset({"hot", "medium", "mild", "none"}),
    "suitable_for": frozenset({"gluten_free", "halal", "vegan", "vegetarian"}),
    "adventurousness": frozenset({"1", "2", "3", "4", "5"}),
}

# Laos bounding box (generous)
LAOS_LAT_MIN, LAOS_LAT_MAX = 13.9, 22.6
LAOS_LNG_MIN, LAOS_LNG_MAX = 100.0, 107.8

# Dubai bounding box
DUBAI_LAT_MIN, DUBAI_LAT_MAX = 24.7, 25.6
DUBAI_LNG_MIN, DUBAI_LNG_MAX = 54.8, 55.8

DAY_KEYS = frozenset({"mon", "tue", "wed", "thu", "fri", "sat", "sun"})
TIME_RE = re.compile(r"^\d{2}:\d{2}$")


# ===========================================================================
# Validation
# ===========================================================================


def get_bounding_box(geo_region: str):
    """Return (lat_min, lat_max, lng_min, lng_max) for a region."""
    if "dubai" in geo_region:
        return DUBAI_LAT_MIN, DUBAI_LAT_MAX, DUBAI_LNG_MIN, DUBAI_LNG_MAX
    # All Laos regions share the Laos bounding box
    return LAOS_LAT_MIN, LAOS_LAT_MAX, LAOS_LNG_MIN, LAOS_LNG_MAX


def validate_time(t: str) -> bool:
    """Check HH:MM format and valid hour/minute."""
    if not TIME_RE.match(t):
        return False
    h, m = int(t[:2]), int(t[3:])
    return 0 <= h <= 23 and 0 <= m <= 59


def validate_venue(
    venue: dict, idx: int, geo_region: str, registered_regions: frozenset, seen_names: set
) -> list[str]:
    """Validate a single venue dict. Returns list of error strings (empty = valid)."""
    errors = []
    name = venue.get("name", f"<unnamed venue #{idx}>")
    prefix = f"Venue '{name}' (#{idx})"

    # Required fields
    for field in ["name", "description", "lat", "lng", "category"]:
        if field not in venue or venue[field] is None:
            errors.append(f"{prefix}: missing required field '{field}'")

    if not venue.get("micro_location"):
        errors.append(f"{prefix}: missing required field 'micro_location'")

    if "typical_dwell_minutes" not in venue:
        errors.append(f"{prefix}: missing required field 'typical_dwell_minutes'")

    if "indoor_outdoor" not in venue:
        errors.append(f"{prefix}: missing required field 'indoor_outdoor'")

    if "price_band" not in venue:
        errors.append(f"{prefix}: missing required field 'price_band'")

    # geo_region validation
    v_region = venue.get("geo_region", geo_region)
    if v_region not in registered_regions:
        errors.append(
            f"{prefix}: geo_region '{v_region}' not in registered regions {sorted(registered_regions)}"
        )

    # Duplicate name within region
    name_key = (venue.get("name", "").lower().strip(), v_region)
    if name_key in seen_names:
        errors.append(f"{prefix}: duplicate name within region '{v_region}'")
    seen_names.add(name_key)

    # Category
    cat = venue.get("category")
    if cat and cat not in VALID_CATEGORIES:
        errors.append(f"{prefix}: category '{cat}' not in valid set")

    # Vibe tags
    for tag in venue.get("vibe_tags", []):
        if tag not in VALID_VIBE_TAGS:
            errors.append(f"{prefix}: vibe_tag '{tag}' not in valid set")

    # Audience
    for aud in venue.get("audience", []):
        if aud not in VALID_AUDIENCES:
            errors.append(f"{prefix}: audience '{aud}' not in valid set")

    # Indoor/outdoor
    io = venue.get("indoor_outdoor")
    if io and io not in VALID_INDOOR_OUTDOOR:
        errors.append(f"{prefix}: indoor_outdoor '{io}' not in valid set")

    # Price band
    pb = venue.get("price_band")
    if pb and pb not in VALID_PRICE_BANDS:
        errors.append(f"{prefix}: price_band '{pb}' not in valid set")

    # Coordinate type check (reject arrays like [lat, lng])
    lat_raw = venue.get("lat")
    lng_raw = venue.get("lng")
    if isinstance(lat_raw, (list, tuple)):
        errors.append(f"{prefix}: 'lat' is an array {lat_raw} -- expected a float (e.g. 19.8856)")
    if isinstance(lng_raw, (list, tuple)):
        errors.append(f"{prefix}: 'lng' is an array {lng_raw} -- expected a float (e.g. 102.1350)")

    # Lat/lng bounds
    lat = lat_raw if isinstance(lat_raw, (int, float)) else None
    lng = lng_raw if isinstance(lng_raw, (int, float)) else None
    if lat is not None and lng is not None:
        lat_min, lat_max, lng_min, lng_max = get_bounding_box(v_region)
        if not (lat_min <= lat <= lat_max):
            errors.append(f"{prefix}: lat {lat} outside bounds [{lat_min}, {lat_max}]")
        if not (lng_min <= lng <= lng_max):
            errors.append(f"{prefix}: lng {lng} outside bounds [{lng_min}, {lng_max}]")

    # Opening hours validation
    hours = venue.get("opening_hours_structured")
    if hours is not None:
        if not isinstance(hours, dict):
            errors.append(f"{prefix}: opening_hours_structured must be a dict")
        else:
            missing_days = DAY_KEYS - set(hours.keys())
            if missing_days:
                errors.append(
                    f"{prefix}: opening_hours_structured missing days: {sorted(missing_days)}"
                )
            for day, slots in hours.items():
                if day not in DAY_KEYS:
                    errors.append(f"{prefix}: opening_hours_structured invalid day key '{day}'")
                    continue
                if not isinstance(slots, list):
                    errors.append(f"{prefix}: opening_hours_structured['{day}'] must be a list")
                    continue
                for slot in slots:
                    if not isinstance(slot, list) or len(slot) != 2:
                        errors.append(
                            f"{prefix}: opening_hours_structured['{day}'] slot must be [start, end]"
                        )
                        continue
                    start, end = slot
                    if not validate_time(start):
                        errors.append(f"{prefix}: invalid time '{start}' in {day}")
                    if not validate_time(end):
                        errors.append(f"{prefix}: invalid time '{end}' in {day}")
                    if validate_time(start) and validate_time(end) and end <= start:
                        errors.append(
                            f"{prefix}: time range end '{end}' <= start '{start}' in {day}"
                        )

    # Dishes on non-food category
    dishes = venue.get("dishes", [])
    if dishes and cat not in FOOD_CATEGORIES:
        errors.append(f"{prefix}: has dishes but category '{cat}' is not a food category")

    # Validate each dish
    for d_idx, dish in enumerate(dishes):
        d_name = dish.get("dish_name") or dish.get("name_en") or f"<dish #{d_idx}>"
        if not dish.get("dish_name") and not dish.get("name_en"):
            errors.append(f"{prefix} > dish #{d_idx}: missing 'dish_name'")
        cuisine = dish.get("cuisine")
        if cuisine and cuisine not in VALID_CUISINES:
            errors.append(f"{prefix} > dish '{d_name}': cuisine '{cuisine}' not in valid set")

        # Allergen vocabulary check
        for allergen in dish.get("contains", []):
            if allergen not in VALID_ALLERGENS:
                errors.append(
                    f"{prefix} > dish '{d_name}': contains allergen '{allergen}' not in valid set"
                )
        for allergen in dish.get("may_contain", []):
            if allergen not in VALID_ALLERGENS:
                errors.append(
                    f"{prefix} > dish '{d_name}': may_contain allergen '{allergen}' not in valid set"
                )

        # Dietary label vocabulary check
        for label in dish.get("suitable_for", []):
            if label not in VALID_DIETARY_LABELS:
                errors.append(
                    f"{prefix} > dish '{d_name}': suitable_for '{label}' not in valid set"
                )

        # SAFETY INVARIANT: cross-field allergen assertion
        suitable = dish.get("suitable_for", [])
        contains_list = dish.get("contains", [])
        may_contain_list = dish.get("may_contain", [])
        if suitable:
            conflicts = check_allergen_conflicts(suitable, contains_list, may_contain_list)
            for conflict in conflicts:
                errors.append(
                    f"{prefix} > dish '{d_name}': ALLERGEN SAFETY VIOLATION -- {conflict}"
                )

    return errors


def collect_warnings(venues: list[dict], geo_region: str) -> list[str]:
    """Collect non-fatal warnings. These are printed but don't block loading."""
    warnings = []

    # Count by micro_location
    micro_counts: dict[str, int] = {}
    for v in venues:
        ml = v.get("micro_location", "unknown")
        micro_counts[ml] = micro_counts.get(ml, 0) + 1

    for ml, count in micro_counts.items():
        if count < 3:
            warnings.append(f"micro_location '{ml}' has only {count} venue(s) (< 3)")

    # Region-level warnings
    if len(venues) < 15:
        warnings.append(f"Region '{geo_region}' has only {len(venues)} venues (< 15)")

    cats = {v.get("category") for v in venues}
    if "massage_spa" not in cats:
        warnings.append(f"Region '{geo_region}' has zero massage_spa venues")

    for v in venues:
        name = v.get("name", "?")
        if v.get("opening_hours_structured") is None and v.get("opening_hours") is None:
            warnings.append(f"'{name}': no opening hours data (neither structured nor plain)")
        if v.get("has_aircon") is None:
            warnings.append(f"'{name}': has_aircon is null")
        cat = v.get("category", "")
        if cat in FOOD_CATEGORIES and not v.get("dishes"):
            warnings.append(f"'{name}': food venue with no dishes")
        dwell = v.get("typical_dwell_minutes")
        if dwell is not None and (dwell < 10 or dwell > 300):
            warnings.append(f"'{name}': typical_dwell_minutes={dwell} outside 10-300")

    return warnings


# ===========================================================================
# Embedding
# ===========================================================================


def generate_embedding_text(venue: dict) -> str:
    """Build the text to embed. Same composition as query-time for consistency."""
    parts = [
        venue.get("name", ""),
        venue.get("description", ""),
        " ".join(venue.get("vibe_tags", [])),
    ]
    return " ".join(p for p in parts if p)


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings using text-embedding-3-small via LiteLLM."""
    import litellm

    response = litellm.embedding(
        model="text-embedding-3-small",
        input=texts,
    )
    return [item["embedding"] for item in response.data]


def estimate_embedding_cost(texts: list[str]) -> float:
    """Estimate cost for text-embedding-3-small ($0.02 per 1M tokens)."""
    # Rough estimate: ~1 token per 4 chars
    total_chars = sum(len(t) for t in texts)
    est_tokens = total_chars / 4
    cost = (est_tokens / 1_000_000) * 0.02
    return cost


# ===========================================================================
# Database operations
# ===========================================================================


def _build_localized_jsonb(raw_value, geo_region: str, source: str = "generated", ref: str = None):
    """Wrap a raw localized string into the SPEC-12 keyed JSONB shape.

    Returns None if raw_value is falsy, otherwise:
        {"<lang>": {"value": "<text>", "source": "<provenance>"}}
    If ref is provided, it is included as a sibling key.

    The language tag comes from REGION_LANGUAGES (interim until SPEC-13).
    """
    if not raw_value:
        return None
    lang = REGION_LANGUAGES.get(geo_region)
    if not lang:
        return None
    entry = {"value": raw_value, "source": source}
    if ref:
        entry["ref"] = ref
    return {lang: entry}


def build_venue_record(venue: dict, venue_id: str, embedding: list[float], geo_region: str) -> dict:
    """Build the venues_rag row dict from a venue JSON object.

    Returns a dict whose keys exactly match VENUES_RAG_WRITE_COLUMNS.
    Used by upsert_venues for both insert and update, and importable by
    tests to assert payload-vs-declaration consistency.
    """
    return {
        "venue_id": venue_id,
        "name": venue["name"],
        "description": venue.get("description"),
        "micro_location": venue.get("micro_location"),
        "lat": venue.get("lat"),
        "lng": venue.get("lng"),
        "vibe_tags": venue.get("vibe_tags", []),
        "audience": venue.get("audience", []),
        "category": venue.get("category"),
        "is_sponsored": venue.get("is_sponsored", False),
        "bid_weight": venue.get("bid_weight", 0.0),
        "opening_hours_structured": venue.get("opening_hours_structured")
        or venue.get("opening_hours"),
        "geo_region": geo_region,
        "embedding": embedding,
        "embedding_model": EMBEDDING_MODEL,
        "typical_dwell_minutes": venue.get("typical_dwell_minutes"),
        "indoor_outdoor": venue.get("indoor_outdoor"),
        "price_band": venue.get("price_band"),
        "has_aircon": venue.get("has_aircon"),
        "names_local": _build_localized_jsonb(
            venue.get("name_local"),
            geo_region,
            source=venue.get("name_local_source", "generated"),
            ref=venue.get("name_local_ref"),
        ),
        "nearest_landmark": venue.get("nearest_landmark"),
        "landmarks_local": _build_localized_jsonb(
            venue.get("nearest_landmark_local"),
            geo_region,
            source=venue.get("nearest_landmark_local_source", "generated"),
            ref=venue.get("nearest_landmark_local_ref"),
        ),
        "wheelchair_notes": venue.get("wheelchair_notes"),
    }


def build_dish_record(
    dish: dict,
    venue_id: str,
    geo_region: str,
) -> dict:
    """Build a venue_dish row dict from a dish entry in the venue JSON.

    Applies the same payload guard as build_venue_record: the returned key set
    must equal VENUE_DISH_WRITE_COLUMNS exactly.
    """
    dish_names_local = None
    raw_name_local = dish.get("name_local")
    if raw_name_local:
        lang = REGION_LANGUAGES.get(geo_region, "und")
        dish_names_local = {lang: {"value": raw_name_local, "source": "generated", "ref": None}}
    dish_currency = REGION_CURRENCIES.get(geo_region) if dish.get("price_local") else None

    record = {
        "dish_id": str(uuid.uuid4()),
        "venue_id": venue_id,
        "name_en": dish.get("dish_name"),
        "name_local": dish.get("name_local"),
        "names_local": dish_names_local,
        "is_signature": dish.get("is_signature", False),
        "cuisine": dish.get("cuisine"),
        "price_local": dish.get("price_local"),
        "price_band": dish.get("price_band"),
        "currency_code": dish_currency,
    }

    # Payload guard: key set must match declared write columns exactly
    if set(record.keys()) != VENUE_DISH_WRITE_COLUMNS:
        extra = set(record.keys()) - VENUE_DISH_WRITE_COLUMNS
        missing = VENUE_DISH_WRITE_COLUMNS - set(record.keys())
        raise ValueError(
            f"build_dish_record payload mismatch: extra={sorted(extra)}, missing={sorted(missing)}"
        )
    return record


def build_external_id_record(venue: dict, venue_id: str) -> dict | None:
    """Build a venue_external_id row if the venue carries a name_local_ref.

    Returns a dict whose keys exactly match VENUE_EXTERNAL_ID_WRITE_COLUMNS,
    or None if no external reference is present.
    """
    source = venue.get("name_local_source")
    ref = venue.get("name_local_ref")
    if not source or not ref or source not in EXTERNAL_ID_SOURCES:
        return None
    return {
        "venue_id": venue_id,
        "source": source,
        "external_id": ref,
        "confidence": 1.0,
        "verified_at": None,
    }


def upsert_venues(venues: list[dict], geo_region: str, embeddings: list[list[float]]):
    """Upsert venues + dishes to Supabase. Idempotent on (name, geo_region)."""
    from supabase import create_client

    url = os.environ.get("TB_SUPABASE_URL", "")
    key = os.environ.get("TB_SUPABASE_KEY", "")
    if not url or not key:
        print("ERROR: TB_SUPABASE_URL and TB_SUPABASE_KEY must be set", file=sys.stderr)
        sys.exit(1)

    client = create_client(url, key)

    for i, venue in enumerate(venues):
        venue_id = str(uuid.uuid4())
        venue_name = venue["name"]

        # Check if venue already exists (upsert)
        existing = (
            client.table("venues_rag")
            .select("venue_id")
            .eq("name", venue_name)
            .eq("geo_region", geo_region)
            .execute()
        )

        if existing.data:
            venue_id = existing.data[0]["venue_id"]

        record = build_venue_record(venue, venue_id, embeddings[i], geo_region)

        if existing.data:
            # Update: strip identity columns used in the WHERE clause
            update_payload = {k: v for k, v in record.items() if k not in ("venue_id", "name")}
            client.table("venues_rag").update(update_payload).eq("venue_id", venue_id).execute()
        else:
            # Insert
            client.table("venues_rag").insert(record).execute()

        # Dishes (delete + re-insert for idempotency)
        dishes = venue.get("dishes", [])
        if dishes:
            client.table("venue_dish").delete().eq("venue_id", venue_id).execute()
            for dish in dishes:
                record = build_dish_record(dish, venue_id, geo_region)
                client.table("venue_dish").insert(record).execute()

        # External IDs (idempotent: ON CONFLICT DO NOTHING)
        ext_record = build_external_id_record(venue, venue_id)
        if ext_record is not None:
            client.table("venue_external_id").upsert(
                ext_record,
                on_conflict="source,external_id",
            ).execute()

    return len(venues)


# ===========================================================================
# Main
# ===========================================================================


def main():
    parser = argparse.ArgumentParser(description="Load venue data with validation")
    parser.add_argument("files", nargs="+", help="JSON venue data files")
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate and report without writing to DB"
    )
    parser.add_argument(
        "--geo-region", default=None, help="Override geo_region for all venues in the file"
    )
    args = parser.parse_args()

    registered_regions = get_all_region_codes()
    all_errors: list[str] = []
    all_warnings: list[str] = []
    file_data: list[tuple[str, list[dict], str]] = []  # (filepath, venues, region)

    for filepath in args.files:
        if not os.path.exists(filepath):
            all_errors.append(f"File not found: {filepath}")
            continue

        with open(filepath, encoding="utf-8") as f:
            raw_text = f.read()

        # Reject // comments (JSON doesn't support them)
        for line_num, line in enumerate(raw_text.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("//"):
                all_errors.append(
                    f"{filepath}:{line_num}: JSON does not support // comments. "
                    f"Remove: {stripped[:60]}"
                )
                break

        if any(filepath in e for e in all_errors):
            continue

        try:
            venues = json.loads(raw_text)
        except json.JSONDecodeError as e:
            all_errors.append(f"{filepath}: Invalid JSON - {e}")
            continue

        file_geo_region = None  # geo_region from dict wrapper (if present)
        if isinstance(venues, dict):
            # Unwrap dict format: {"geo_region": ..., "venues": [...]}
            file_geo_region = venues.get("geo_region") or venues.get("region")
            array_key = next(
                (k for k in ("venues", "data", "items") if isinstance(venues.get(k), list)),
                None,
            )
            if array_key:
                venues = venues[array_key]
            else:
                all_errors.append(
                    f"{filepath}: JSON is a dict but has no 'venues'/'data'/'items' array key. "
                    f"Top-level keys: {sorted(venues.keys())}"
                )
                continue
        elif not isinstance(venues, list):
            all_errors.append(
                f"{filepath}: Expected JSON array or dict with venues key, got {type(venues).__name__}"
            )
            continue

        # Determine geo_region: CLI override > file-level field > infer from filename
        geo_region = args.geo_region
        if not geo_region:
            if file_geo_region and file_geo_region in registered_regions:
                geo_region = file_geo_region
            else:
                # Try to infer from filename (e.g. venues_luang_prabang_laos.json)
                stem = Path(filepath).stem.replace("venues_", "")
                if stem in registered_regions:
                    geo_region = stem
                elif venues and venues[0].get("geo_region"):
                    geo_region = venues[0]["geo_region"]
                else:
                    all_errors.append(
                        f"{filepath}: Cannot determine geo_region. "
                        f"Use --geo-region or name file as venues_<region>.json"
                    )
                    continue

        if geo_region not in registered_regions:
            all_errors.append(
                f"{filepath}: geo_region '{geo_region}' not registered. "
                f"Valid: {sorted(registered_regions)}"
            )
            continue

        # Validate every venue
        seen_names: set = set()
        file_errors: list[str] = []
        for idx, venue in enumerate(venues):
            errs = validate_venue(venue, idx, geo_region, registered_regions, seen_names)
            file_errors.extend(errs)

        if file_errors:
            all_errors.append(f"\n--- {filepath} ({len(file_errors)} error(s)) ---")
            all_errors.extend(file_errors)
        else:
            file_data.append((filepath, venues, geo_region))
            all_warnings.extend(collect_warnings(venues, geo_region))

    # Report
    if all_warnings:
        print(f"\n{'=' * 60}")
        print(f"WARNINGS ({len(all_warnings)}):")
        print(f"{'=' * 60}")
        for w in all_warnings:
            print(f"  [!]  {w}")

    if all_errors:
        print(f"\n{'=' * 60}", file=sys.stderr)
        print(f"ERRORS ({len(all_errors)}) -- NO DATA LOADED:", file=sys.stderr)
        print(f"{'=' * 60}", file=sys.stderr)
        for e in all_errors:
            print(f"  [X] {e}", file=sys.stderr)
        sys.exit(1)

    if not file_data:
        print("No valid files to process.", file=sys.stderr)
        sys.exit(1)

    # Summary
    print(f"\n{'=' * 60}")
    print("VALIDATION PASSED")
    print(f"{'=' * 60}")
    total_venues = 0
    total_dishes = 0
    for filepath, venues, geo_region in file_data:
        n_dishes = sum(len(v.get("dishes", [])) for v in venues)
        total_venues += len(venues)
        total_dishes += n_dishes
        print(f"\n  {filepath}:")
        print(f"    Region: {geo_region}")
        print(f"    Venues: {len(venues)}")
        print(f"    Dishes: {n_dishes}")
        # Category breakdown
        cats: dict[str, int] = {}
        for v in venues:
            c = v.get("category", "unknown")
            cats[c] = cats.get(c, 0) + 1
        for c in sorted(cats):
            print(f"      {c}: {cats[c]}")

    # Embedding cost estimate
    all_texts = []
    for _, venues, _ in file_data:
        for v in venues:
            all_texts.append(generate_embedding_text(v))
    est_cost = estimate_embedding_cost(all_texts)
    print(f"\n  Total venues: {total_venues}")
    print(f"  Total dishes: {total_dishes}")
    print(f"  Estimated embedding cost: ${est_cost:.4f}")

    if args.dry_run:
        print("\n  --dry-run: No data written.")
        sys.exit(0)

    # Generate embeddings and upsert
    print("\n  Generating embeddings...")
    BATCH_SIZE = 50
    all_embeddings: list[list[float]] = []
    for i in range(0, len(all_texts), BATCH_SIZE):
        batch = all_texts[i : i + BATCH_SIZE]
        embs = embed_batch(batch)
        all_embeddings.extend(embs)
        print(f"    Embedded {min(i + BATCH_SIZE, len(all_texts))}/{len(all_texts)}")

    # Upsert per file
    emb_idx = 0
    for filepath, venues, geo_region in file_data:
        n = len(venues)
        file_embeddings = all_embeddings[emb_idx : emb_idx + n]
        emb_idx += n
        inserted = upsert_venues(venues, geo_region, file_embeddings)
        print(f"  Upserted {inserted} venues for {geo_region}")

    print("\n  DONE.")


if __name__ == "__main__":
    main()
