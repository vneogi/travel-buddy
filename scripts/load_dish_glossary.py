#!/usr/bin/env python3
"""Load dish glossary JSON into the dish_glossary Supabase table.

Usage:
    python scripts/load_dish_glossary.py data/laos_dish_glossary.json
    python scripts/load_dish_glossary.py data/laos_dish_glossary.json --dry-run
    python scripts/load_dish_glossary.py data/laos_dish_glossary.json --report-fk

Validation (all HARD FAILURES -- script exits non-zero):
  1. JSON parse errors
  2. Missing required fields (dish_key, name_en, contains, may_contain, suitable_for)
  3. Vocab check: contains/may_contain terms must be in VALID_DISH_CONTAINS
  4. Vocab check: suitable_for terms must be in VALID_DIETARY_LABELS
  5. SAFETY INVARIANT: allergen cross-field conflicts (check_allergen_conflicts)
  6. Duplicate dish_key within the input file

--report-fk: After load, query venue_dish and report which rows have
             dish_key set vs NULL (FK linkage health check).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup -- allow running from repo root or scripts/
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from config.dietary import (  # noqa: E402
    VALID_DIETARY_LABELS,
    VALID_DISH_CONTAINS,
    check_allergen_conflicts,
)


logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s: %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Required fields per dish entry
# ---------------------------------------------------------------------------
REQUIRED_FIELDS = {"dish_key", "name_en", "contains", "may_contain", "suitable_for"}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_glossary(dishes: list[dict]) -> list[str]:
    """Validate all dishes. Returns list of error strings. Empty = valid."""
    errors: list[str] = []
    seen_keys: set[str] = set()

    for i, dish in enumerate(dishes):
        prefix = f"dish[{i}]"
        dk = dish.get("dish_key", f"<missing at index {i}>")

        # Required fields
        missing = REQUIRED_FIELDS - set(dish.keys())
        if missing:
            errors.append(f"{prefix} ({dk}): missing required fields: {sorted(missing)}")
            continue  # can't validate further without these

        prefix = f"dish[{i}] ({dk})"

        # Duplicate key check
        if dk in seen_keys:
            errors.append(f"{prefix}: duplicate dish_key")
        seen_keys.add(dk)

        # Vocab: contains
        for term in dish["contains"]:
            if term not in VALID_DISH_CONTAINS:
                errors.append(f"{prefix}: contains term '{term}' not in VALID_DISH_CONTAINS")

        # Vocab: may_contain
        for term in dish["may_contain"]:
            if term not in VALID_DISH_CONTAINS:
                errors.append(f"{prefix}: may_contain term '{term}' not in VALID_DISH_CONTAINS")

        # Vocab: suitable_for
        for label in dish["suitable_for"]:
            if label not in VALID_DIETARY_LABELS:
                errors.append(f"{prefix}: suitable_for label '{label}' not in VALID_DIETARY_LABELS")

        # SAFETY INVARIANT: cross-field allergen conflicts
        conflicts = check_allergen_conflicts(
            suitable_for=dish["suitable_for"],
            contains=dish["contains"],
            may_contain=dish["may_contain"],
        )
        for conflict in conflicts:
            errors.append(f"{prefix}: SAFETY CONFLICT -- {conflict}")

    return errors


# ---------------------------------------------------------------------------
# Database upsert
# ---------------------------------------------------------------------------


def upsert_dishes(client, dishes: list[dict]) -> dict:
    """Upsert dishes into dish_glossary. Returns {inserted, updated, errors}."""
    rows = []
    for dish in dishes:
        rows.append(
            {
                "dish_key": dish["dish_key"],
                "canonical_name": dish["name_en"],
                "cuisine": dish.get("cuisine"),
                "contains": dish["contains"],
                "may_contain": dish["may_contain"],
                "suitable_for": dish["suitable_for"],
                "description": dish.get("description"),
            }
        )

    result = client.table("dish_glossary").upsert(rows, on_conflict="dish_key").execute()
    return {"upserted": len(result.data), "errors": []}


def report_fk_linkage(client) -> None:
    """Report venue_dish FK linkage health."""
    # Count total venue_dish rows
    total = client.table("venue_dish").select("id", count="exact").execute()
    total_count = total.count or 0

    # Count linked (dish_key IS NOT NULL)
    linked = (
        client.table("venue_dish")
        .select("id", count="exact")
        .not_.is_("dish_key", "null")
        .execute()
    )
    linked_count = linked.count or 0

    # Count unlinked
    unlinked_count = total_count - linked_count

    print("\n--- venue_dish FK linkage report ---")
    print(f"  Total venue_dish rows: {total_count}")
    print(f"  Linked (dish_key set): {linked_count}")
    print(f"  Unlinked (dish_key NULL): {unlinked_count}")
    if total_count > 0:
        pct = (linked_count / total_count) * 100
        print(f"  Coverage: {pct:.1f}%")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Load dish glossary into Supabase.")
    parser.add_argument("filepath", help="Path to dish glossary JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, do not upsert")
    parser.add_argument(
        "--report-fk", action="store_true", help="Report venue_dish FK linkage after load"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    filepath = Path(args.filepath)
    if not filepath.exists():
        print(f"ERROR: File not found: {filepath}", file=sys.stderr)
        return 1

    # --- Parse JSON ---
    try:
        raw_text = filepath.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        print(f"ERROR: Cannot read {filepath}: {e}", file=sys.stderr)
        return 1

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {filepath}: {e}", file=sys.stderr)
        return 1

    # --- Extract dishes array ---
    if isinstance(data, dict) and "dishes" in data:
        dishes = data["dishes"]
        region = data.get("region", "unknown")
    elif isinstance(data, list):
        dishes = data
        region = "unknown"
    else:
        print("ERROR: Expected top-level dict with 'dishes' key or a list", file=sys.stderr)
        return 1

    print(f"Loaded {len(dishes)} dishes from {filepath} (region: {region})")

    # --- Validate ---
    errors = validate_glossary(dishes)
    if errors:
        print(f"\nVALIDATION FAILED ({len(errors)} error(s)):", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    print(f"Validation passed: {len(dishes)} dishes, 0 errors")

    if args.dry_run:
        print("--dry-run: skipping database upsert")
        return 0

    # --- Supabase client ---
    url = os.environ.get("TB_SUPABASE_URL") or os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("TB_SUPABASE_SERVICE_KEY") or os.environ.get(
        "SUPABASE_SERVICE_ROLE_KEY", ""
    )

    if not url or not key:
        print(
            "ERROR: Set TB_SUPABASE_URL and TB_SUPABASE_SERVICE_KEY "
            "(or SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY)",
            file=sys.stderr,
        )
        return 1

    from supabase import create_client

    client = create_client(url, key)

    # --- Upsert ---
    result = upsert_dishes(client, dishes)
    print(f"Upserted {result['upserted']} rows into dish_glossary")

    # --- FK report ---
    if args.report_fk:
        report_fk_linkage(client)

    return 0


if __name__ == "__main__":
    sys.exit(main())
