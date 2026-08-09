#!/usr/bin/env python3
"""Patch load_venues.py for Laos dict-format JSON + expanded vocabulary.

Run from project root after git pull:
    python scripts/patch_venues_loader.py

Then verify:
    python scripts/load_venues.py data/laos_luang_prabang.json data/laos_vang_vieng.json data/laos_vientiane.json --dry-run

Changes applied:
  1. encoding='utf-8' on file open (fixes cp1252 crash on Lao script)
  2. Dict-unwrap: accepts {"venues": [...]} wrapper format
  3. file_geo_region from dict wrapper feeds geo_region inference
  4. Expanded: VALID_VIBE_TAGS, VALID_AUDIENCES, VALID_INDOOR_OUTDOOR,
     VALID_PRICE_BANDS, VALID_CUISINES, VALID_CATEGORIES, FOOD_CATEGORIES
  5. dish_name -> name_en fallback (Laos dishes use name_en)

Idempotent: safe to run multiple times (skips already-applied patches).
"""
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "load_venues.py"


def apply_patch():
    content = TARGET.read_text(encoding="utf-8")
    applied = 0
    skipped = 0

    def replace_once(old, new, label):
        nonlocal content, applied, skipped
        if old in content:
            content = content.replace(old, new, 1)
            applied += 1
            print(f"  [APPLIED] {label}")
        elif new in content:
            skipped += 1
            print(f"  [SKIP]    {label} (already applied)")
        else:
            print(f"  [MISS]    {label} -- MANUAL FIX NEEDED")
            return False
        return True

    print(f"Patching: {TARGET}")
    print()

    # 1. Encoding fix
    replace_once(
        'with open(filepath) as f:',
        "with open(filepath, encoding='utf-8') as f:",
        "encoding='utf-8' on file open",
    )

    # 2. Expand VALID_VIBE_TAGS
    replace_once(
        '    "family_friendly", "instagram_worthy", "hidden_gem",\n})',
        '    "family_friendly", "instagram_worthy", "hidden_gem",\n'
        '    "photogenic", "local_favourite", "touristy", "budget",\n'
        '    "riverside", "hidden", "upscale", "historical",\n})',
        "expand VALID_VIBE_TAGS (+8 terms)",
    )

    # 3. Expand VALID_AUDIENCES
    replace_once(
        '    "executive", "backpacker", "digital_nomad", "group",\n})',
        '    "executive", "backpacker", "digital_nomad", "group",\n'
        '    "solo", "friends_group", "seniors",\n'
        '    "family_young_kids", "family_teens", "mobility_limited",\n})',
        "expand VALID_AUDIENCES (+6 terms)",
    )

    # 4. Expand VALID_INDOOR_OUTDOOR
    replace_once(
        'VALID_INDOOR_OUTDOOR = frozenset({"indoor", "outdoor", "both"})',
        'VALID_INDOOR_OUTDOOR = frozenset({"indoor", "outdoor", "both", "mixed"})',
        "expand VALID_INDOOR_OUTDOOR (+mixed)",
    )

    # 5. Expand VALID_PRICE_BANDS
    replace_once(
        'VALID_PRICE_BANDS = frozenset({"budget", "moderate", "premium", "luxury"})',
        'VALID_PRICE_BANDS = frozenset({"budget", "moderate", "mid", "premium", "luxury", "splurge", "free"})',
        "expand VALID_PRICE_BANDS (+mid, splurge, free)",
    )

    # 6. Expand VALID_CUISINES
    replace_once(
        '    "coffee", "smoothie", "street_food",\n})',
        '    "coffee", "smoothie", "street_food", "french_colonial", "drink",\n})',
        "expand VALID_CUISINES (+french_colonial, drink)",
    )

    # 7. Expand VALID_CATEGORIES
    replace_once(
        '    "night_market", "waterfall", "viewpoint", "cooking_class",\n})',
        '    "night_market", "waterfall", "viewpoint", "cooking_class",\n'
        '    "street_food", "walking_area", "river_activity", "craft_workshop",\n})',
        "expand VALID_CATEGORIES (+4 Laos categories)",
    )

    # 8. Expand FOOD_CATEGORIES
    replace_once(
        '    "restaurant", "cafe", "bar", "night_market", "street_food",\n})',
        '    "restaurant", "cafe", "bar", "night_market", "street_food",\n'
        '    "market", "craft_workshop",\n})',
        "expand FOOD_CATEGORIES (+market, craft_workshop)",
    )

    # 9. Dict unwrap + file_geo_region (the big one)
    old_check = ('        if not isinstance(venues, list):\n'
                 '            all_errors.append(f"{filepath}: Expected JSON array, got {type(venues).__name__}")\n'
                 '            continue')
    new_check = ('        file_geo_region = None  # geo_region from dict wrapper (if present)\n'
                 '        if isinstance(venues, dict):\n'
                 '            # Unwrap dict format: {"geo_region": ..., "venues": [...]}\n'
                 '            file_geo_region = venues.get("geo_region") or venues.get("region")\n'
                 '            array_key = next(\n'
                 '                (k for k in ("venues", "data", "items") if isinstance(venues.get(k), list)),\n'
                 '                None,\n'
                 '            )\n'
                 '            if array_key:\n'
                 '                venues = venues[array_key]\n'
                 '            else:\n'
                 '                all_errors.append(\n'
                 '                    f"{filepath}: JSON is a dict but has no \'venues\'/\'data\'/\'items\' array key. "\n'
                 '                    f"Top-level keys: {sorted(venues.keys())}"\n'
                 '                )\n'
                 '                continue\n'
                 '        elif not isinstance(venues, list):\n'
                 '            all_errors.append(f"{filepath}: Expected JSON array or dict with venues key, got {type(venues).__name__}")\n'
                 '            continue')
    replace_once(old_check, new_check, "dict-unwrap + file_geo_region extraction")

    # 10. geo_region inference: add file_geo_region priority
    old_infer = ('            elif venues and venues[0].get("geo_region"):\n'
                 '                geo_region = venues[0]["geo_region"]')
    new_infer = ('            elif file_geo_region and file_geo_region in registered_regions:\n'
                 '                geo_region = file_geo_region\n'
                 '            elif venues and venues[0].get("geo_region"):\n'
                 '                geo_region = venues[0]["geo_region"]')
    replace_once(old_infer, new_infer, "file_geo_region in inference chain")

    # 11. dish_name -> name_en fallback
    replace_once(
        '        if not dish.get("dish_name"):',
        '        if not dish.get("dish_name") and not dish.get("name_en"):',
        "dish_name OR name_en required check",
    )
    replace_once(
        '        d_name = dish.get("dish_name", f"<dish #{d_idx}>")',
        '        d_name = dish.get("dish_name") or dish.get("name_en") or f"<dish #{d_idx}>"',
        "d_name fallback to name_en",
    )

    # Write back
    TARGET.write_text(content, encoding="utf-8")

    print(f"\nDone: {applied} applied, {skipped} skipped.")
    if applied > 0:
        print("\nVerify with:")
        print("  python scripts/load_venues.py data/laos_luang_prabang.json "
              "data/laos_vang_vieng.json data/laos_vientiane.json --dry-run")
    return 0


if __name__ == "__main__":
    sys.exit(apply_patch())
