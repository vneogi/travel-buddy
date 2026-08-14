# Genie Brief -- Relocate VALID_DISH_CONTAINS (R5)

> Status: DONE. Landed via PR #15, squash merge `d061222` on main.
> Kept as the executed brief; do not re-run.

> Paste this entire file to Genie Code. Land via PR, not direct to main.

## Goal

Move `VALID_DISH_CONTAINS` from `scripts/load_dish_glossary.py` into
`config/dietary.py`, which is already the dietary vocabulary registry.
Close the standing R5 violation. Pure refactor. No schema change. No
migration. Do not touch live data. Do not implement SPEC-14 retirement in
this brief.

## Why

`config/dietary.py` already owns `VALID_ALLERGENS`, `VALID_DIETARY_LABELS`,
`VALID_DIETARY_CONSTRAINTS`, and `LABEL_EXCLUDES_ALLERGENS`. The glossary
loader defines a superset of `VALID_ALLERGENS` locally and comments that the
extension is temporary. Two registries for one vocabulary is exactly R5.

## Current definition (move as-is)

In `scripts/load_dish_glossary.py` today:

```python
VALID_DISH_CONTAINS: frozenset[str] = VALID_ALLERGENS | frozenset(
    {
        "pork",
        "beef",
        "chilli",
        "alcohol",
        "fish_sauce",
        "egg",
        "peanut",
        "soy",
        "tree_nut",
    }
)
```

Place that constant in `config/dietary.py` next to the other vocabularies,
with a short comment that it is the allowed vocabulary for dish
`contains` / `may_contain` arrays (allergens plus meat types, sensitivities,
and singular aliases used by the glossary).

## Code changes

1. Add `VALID_DISH_CONTAINS` to `config/dietary.py`.
2. In `scripts/load_dish_glossary.py`:
   - Import `VALID_DISH_CONTAINS` from `config.dietary`.
   - Delete the local definition and the "temporary co-location" comment
     block above it.
   - Keep behaviour identical.
3. Do not rename terms. Do not "clean up" aliases. Do not change
   `LABEL_EXCLUDES_ALLERGENS` or retire `suitable_for`.

## Tests (R17)

Add a guard that would fail if the constant is redefined in the loader or
quietly diverges:

1. Assert `scripts.load_dish_glossary.VALID_DISH_CONTAINS is
   config.dietary.VALID_DISH_CONTAINS` (same object, not merely equal).
   Import the loader module the way production does.
2. Assert set equality against the explicit expected extension union so a
   future edit that shrinks the set in one place only cannot stay green.
3. Keep existing glossary validation behaviour covered -- a dry-run style
   unit test that rejects an unknown `contains` term still fails.

Sabotage before trusting the guard:

- Put a duplicate local frozenset back in the loader with one term removed
  and confirm test 1 or 2 fails.
- Watch which assertion fails by name.

## Out of scope

- SPEC-14 dietary claim retirement
- Moving `VALID_DISH_CONTAINS` consumers other than the glossary loader
  (there should be none; grep to confirm)
- Data file edits
- Migrations
- Flutter

## Acceptance

- [ ] `VALID_DISH_CONTAINS` defined only in `config/dietary.py`
- [ ] `scripts/load_dish_glossary.py` imports it; no local copy remains
- [ ] `rg -n "VALID_DISH_CONTAINS" ` shows the definition once, plus imports
      and tests
- [ ] New identity/equality guards pass, and sabotage proof was observed
- [ ] `pytest -q -ra` green; report pass and skip counts with reasons (R8)
- [ ] ASCII only in Python comments/docstrings (R14)
- [ ] No SPEC-NN citation of a missing spec
- [ ] PR opened; do not push directly to main for this code change

## PR title suggestion

`refactor: move VALID_DISH_CONTAINS into config.dietary (R5)`
