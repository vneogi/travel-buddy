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

# ===========================================================================
# Vocabulary (SINGLE SOURCE OF TRUTH for validation)
# ===========================================================================

VALID_CATEGORIES = frozenset({
    "restaurant", "cafe", "temple", "market", "nature", "activity",
    "museum", "bar", "hotel_lobby", "hospital", "pharmacy",
    "transport_hub", "embassy", "essential_service", "massage_spa",
    "night_market", "waterfall", "viewpoint", "cooking_class",
})

VALID_VIBE_TAGS = frozenset({
    "cultural", "authentic", "energetic", "leisurely", "adventurous",
    "premium_interiors", "artistic", "independent", "familiar",
    "air_conditioned", "outdoor", "romantic", "spiritual", "scenic",
    "lively", "quiet", "historic", "modern", "cozy", "luxurious",
    "family_friendly", "instagram_worthy", "hidden_gem",
})

VALID_AUDIENCES = frozenset({
    "solo_traveler", "couple", "family_with_kids", "family_with_teens",
    "executive", "backpacker", "digital_nomad", "group",
})

VALID_INDOOR_OUTDOOR = frozenset({"indoor", "outdoor", "both"})

VALID_PRICE_BANDS = frozenset({"budget", "moderate", "premium", "luxury"})

VALID_CUISINES = frozenset({
    "lao", "thai", "french", "fusion", "international", "vietnamese",
    "emirati", "indian", "chinese", "japanese", "korean", "italian",
    "american", "middle_eastern", "african", "bakery", "dessert",
    "coffee", "smoothie", "street_food",
})

# Food categories that may have dishes
FOOD_CATEGORIES = frozenset({
    "restaurant", "cafe", "bar", "night_market", "street_food",
})

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


def validate_venue(venue: dict, idx: int, geo_region: str,
                   registered_regions: frozenset, seen_names: set) -> list[str]:
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
        errors.append(f"{prefix}: geo_region '{v_region}' not in registered regions {sorted(registered_regions)}")

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

    # Lat/lng bounds
    lat = venue.get("lat")
    lng = venue.get("lng")
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
                errors.append(f"{prefix}: opening_hours_structured missing days: {sorted(missing_days)}")
            for day, slots in hours.items():
                if day not in DAY_KEYS:
                    errors.append(f"{prefix}: opening_hours_structured invalid day key '{day}'")
                    continue
                if not isinstance(slots, list):
                    errors.append(f"{prefix}: opening_hours_structured['{day}'] must be a list")
                    continue
                for slot in slots:
                    if not isinstance(slot, list) or len(slot) != 2:
                        errors.append(f"{prefix}: opening_hours_structured['{day}'] slot must be [start, end]")
                        continue
                    start, end = slot
                    if not validate_time(start):
                        errors.append(f"{prefix}: invalid time '{start}' in {day}")
                    if not validate_time(end):
                        errors.append(f"{prefix}: invalid time '{end}' in {day}")
                    if validate_time(start) and validate_time(end) and end <= start:
                        errors.append(f"{prefix}: time range end '{end}' <= start '{start}' in {day}")

    # Dishes on non-food category
    dishes = venue.get("dishes", [])
    if dishes and cat not in FOOD_CATEGORIES:
        errors.append(f"{prefix}: has dishes but category '{cat}' is not a food category")

    # Validate each dish
    for d_idx, dish in enumerate(dishes):
        d_name = dish.get("dish_name", f"<dish #{d_idx}>")
        if not dish.get("dish_name"):
            errors.append(f"{prefix} > dish #{d_idx}: missing 'dish_name'")
        cuisine = dish.get("cuisine")
        if cuisine and cuisine not in VALID_CUISINES:
            errors.append(f"{prefix} > dish '{d_name}': cuisine '{cuisine}' not in valid set")

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
        if v.get("opening_hours_structured") is None:
            warnings.append(f"'{name}': opening_hours_structured is null")
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
        existing = client.table("venues_rag").select("venue_id").eq(
            "name", venue_name
        ).eq("geo_region", geo_region).execute()

        if existing.data:
            venue_id = existing.data[0]["venue_id"]
            # Update
            client.table("venues_rag").update({
                "description": venue.get("description"),
                "micro_location": venue.get("micro_location"),
                "lat": venue.get("lat"),
                "lng": venue.get("lng"),
                "vibe_tags": venue.get("vibe_tags", []),
                "audience": venue.get("audience", []),
                "category": venue.get("category"),
                "is_sponsored": venue.get("is_sponsored", False),
                "bid_weight": venue.get("bid_weight", 0.0),
                "opening_hours_structured": venue.get("opening_hours_structured"),
                "geo_region": geo_region,
                "embedding": embeddings[i],
                "typical_dwell_minutes": venue.get("typical_dwell_minutes"),
                "indoor_outdoor": venue.get("indoor_outdoor"),
                "price_band": venue.get("price_band"),
            }).eq("venue_id", venue_id).execute()
        else:
            # Insert
            client.table("venues_rag").insert({
                "venue_id": venue_id,
                "name": venue_name,
                "description": venue.get("description"),
                "micro_location": venue.get("micro_location"),
                "lat": venue.get("lat"),
                "lng": venue.get("lng"),
                "vibe_tags": venue.get("vibe_tags", []),
                "audience": venue.get("audience", []),
                "category": venue.get("category"),
                "is_sponsored": venue.get("is_sponsored", False),
                "bid_weight": venue.get("bid_weight", 0.0),
                "opening_hours_structured": venue.get("opening_hours_structured"),
                "geo_region": geo_region,
                "embedding": embeddings[i],
                "typical_dwell_minutes": venue.get("typical_dwell_minutes"),
                "indoor_outdoor": venue.get("indoor_outdoor"),
                "price_band": venue.get("price_band"),
            }).execute()

        # Dishes (delete + re-insert for idempotency)
        dishes = venue.get("dishes", [])
        if dishes:
            client.table("venue_dish").delete().eq("venue_id", venue_id).execute()
            for dish in dishes:
                client.table("venue_dish").insert({
                    "dish_id": str(uuid.uuid4()),
                    "venue_id": venue_id,
                    "name_en": dish.get("dish_name"),
                    "is_signature": dish.get("is_signature", False),
                    "cuisine": dish.get("cuisine"),
                    "price_local": dish.get("price_local"),
                }).execute()

    return len(venues)


# ===========================================================================
# Main
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Load venue data with validation")
    parser.add_argument("files", nargs="+", help="JSON venue data files")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate and report without writing to DB")
    parser.add_argument("--geo-region", default=None,
                        help="Override geo_region for all venues in the file")
    args = parser.parse_args()

    registered_regions = get_all_region_codes()
    all_errors: list[str] = []
    all_warnings: list[str] = []
    file_data: list[tuple[str, list[dict], str]] = []  # (filepath, venues, region)

    for filepath in args.files:
        if not os.path.exists(filepath):
            all_errors.append(f"File not found: {filepath}")
            continue

        with open(filepath) as f:
            try:
                venues = json.load(f)
            except json.JSONDecodeError as e:
                all_errors.append(f"{filepath}: Invalid JSON - {e}")
                continue

        if not isinstance(venues, list):
            all_errors.append(f"{filepath}: Expected JSON array, got {type(venues).__name__}")
            continue

        # Determine geo_region: CLI override > file-level field > infer from filename
        geo_region = args.geo_region
        if not geo_region:
            # Try to infer from filename (e.g. venues_luang_prabang_laos.json)
            stem = Path(filepath).stem.replace("venues_", "")
            if stem in registered_regions:
                geo_region = stem
            elif venues and venues[0].get("geo_region"):
                geo_region = venues[0]["geo_region"]
            else:
                all_errors.append(f"{filepath}: Cannot determine geo_region. "
                                  f"Use --geo-region or name file as venues_<region>.json")
                continue

        if geo_region not in registered_regions:
            all_errors.append(f"{filepath}: geo_region '{geo_region}' not registered. "
                              f"Valid: {sorted(registered_regions)}")
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
        print(f"\n{'='*60}")
        print(f"WARNINGS ({len(all_warnings)}):")
        print(f"{'='*60}")
        for w in all_warnings:
            print(f"  ⚠️  {w}")

    if all_errors:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"ERRORS ({len(all_errors)}) — NO DATA LOADED:", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        for e in all_errors:
            print(f"  ❌ {e}", file=sys.stderr)
        sys.exit(1)

    if not file_data:
        print("No valid files to process.", file=sys.stderr)
        sys.exit(1)

    # Summary
    print(f"\n{'='*60}")
    print("VALIDATION PASSED")
    print(f"{'='*60}")
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
        batch = all_texts[i:i + BATCH_SIZE]
        embs = embed_batch(batch)
        all_embeddings.extend(embs)
        print(f"    Embedded {min(i + BATCH_SIZE, len(all_texts))}/{len(all_texts)}")

    # Upsert per file
    emb_idx = 0
    for filepath, venues, geo_region in file_data:
        n = len(venues)
        file_embeddings = all_embeddings[emb_idx:emb_idx + n]
        emb_idx += n
        inserted = upsert_venues(venues, geo_region, file_embeddings)
        print(f"  Upserted {inserted} venues for {geo_region}")

    print("\n  DONE.")


if __name__ == "__main__":
    main()
