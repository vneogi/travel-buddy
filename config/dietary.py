"""Canonical dietary and allergen vocabulary (R5: single source of truth).

Used by:
- scripts/load_venues.py (dish validation, cross-field allergen assertions)
- party_member.dietary_constraints (trip party model)
- Future: recommendation filtering, menu display

Adding a new allergen or dietary label? Add it HERE ONLY.
"""

from __future__ import annotations

# ===========================================================================
# Allergens -- what a dish CONTAINS or MAY_CONTAIN
# ===========================================================================
# Based on EU-14 major allergens + common extensions for SEA cuisine

VALID_ALLERGENS: frozenset[str] = frozenset(
    {
        # EU-14
        "gluten",
        "crustaceans",
        "eggs",
        "fish",
        "peanuts",
        "soybeans",
        "dairy",  # aka milk/lactose
        "tree_nuts",
        "celery",
        "mustard",
        "sesame",
        "sulphites",
        "lupin",
        "molluscs",
        # SEA extensions
        "shellfish",  # broader than crustaceans
        "msg",
        "shrimp_paste",
        "fermented_fish",
    }
)


# ===========================================================================
# Dietary labels -- what a dish is SUITABLE_FOR
# ===========================================================================

VALID_DIETARY_LABELS: frozenset[str] = frozenset(
    {
        "vegan",
        "vegetarian",
        "pescatarian",
        "halal",
        "kosher",
        "gluten_free",
        "dairy_free",
        "nut_free",
        "egg_free",
        "low_fodmap",
        "keto",
        "raw",
    }
)


# ===========================================================================
# Dietary constraints -- what a PERSON avoids (party_member.dietary_constraints)
# ===========================================================================
# Superset: includes both "I am X" (vegan) and "I avoid Y" (peanuts)

VALID_DIETARY_CONSTRAINTS: frozenset[str] = (
    VALID_DIETARY_LABELS
    | VALID_ALLERGENS
    | frozenset(
        {
            # Person-level constraints that aren't dish-level labels
            "no_alcohol",
            "no_pork",
            "no_beef",
            "no_raw_food",
            "no_spicy",
        }
    )
)


# ===========================================================================
# Cross-field exclusion rules (SAFETY INVARIANT)
# ===========================================================================
# If a dish claims suitable_for=X, it MUST NOT contain any allergen in the
# exclusion set. Violation = hard failure in the loader (not a warning).
#
# Logic: "suitable_for vegan" means NO animal products whatsoever.
# A dish cannot be vegan AND contain dairy -- that's a data error that
# could cause an allergic reaction.

LABEL_EXCLUDES_ALLERGENS: dict[str, frozenset[str]] = {
    "vegan": frozenset(
        {
            "dairy",
            "eggs",
            "fish",
            "crustaceans",
            "shellfish",
            "molluscs",
            "shrimp_paste",
            "fermented_fish",
        }
    ),
    "vegetarian": frozenset(
        {
            "fish",
            "crustaceans",
            "shellfish",
            "molluscs",
            "shrimp_paste",
            "fermented_fish",
        }
    ),
    "pescatarian": frozenset(
        {
            # Pescatarian excludes land-animal meat but not fish/shellfish.
            # No allergen-level exclusions needed here since allergens
            # don't encode "meat" -- handled by category instead.
        }
    ),
    "gluten_free": frozenset({"gluten"}),
    "dairy_free": frozenset({"dairy"}),
    "nut_free": frozenset({"peanuts", "tree_nuts"}),
    "egg_free": frozenset({"eggs"}),
}


def check_allergen_conflicts(
    suitable_for: list[str],
    contains: list[str],
    may_contain: list[str],
) -> list[str]:
    """Return list of conflict descriptions. Empty = safe.

    A conflict means the dish claims suitability for a dietary group
    but also contains (or may contain) an allergen that contradicts it.
    This is a SAFETY invariant -- conflicts are hard failures.
    """
    conflicts: list[str] = []
    all_allergens = set(contains) | set(may_contain)

    for label in suitable_for:
        excluded = LABEL_EXCLUDES_ALLERGENS.get(label)
        if not excluded:
            continue
        violations = all_allergens & excluded
        if violations:
            conflicts.append(
                f"suitable_for='{label}' conflicts with allergens {sorted(violations)}"
            )

    return conflicts
