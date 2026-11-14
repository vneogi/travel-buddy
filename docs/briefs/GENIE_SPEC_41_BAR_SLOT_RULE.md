# Genie brief: SPEC-41 follow-up -- bars never fill the morning slot

Read this whole file before touching anything. It is the complete job.
If something here conflicts with your memory of an earlier brief, this
file wins. If something here is unclear, stop and ask; do not guess and
do not widen scope.

## 0. Context in one paragraph

The owner field-tested the Nungwi pack on a phone on 2026-11-14. Day 1
of a generated Nungwi trip put "Cholo's Beach by Bento" (catalog
category `bar`) in the Morning slot. Root cause, verified on main:
`services/day_slots.py` treats every category outside
`{cafe, restaurant, street_food}` as an activity, and activity venues
may fill either `morning_tour` or `afternoon_evening_tour`. So a `bar`
is eligible for the 08:00 to 11:00 morning band. Nothing in the planner
or in the swap predicate stops it. This is region-agnostic: any region
with a `bar` and no structured hours can produce a bar-first day. This
slice makes `bar` an afternoon/evening-only category. It does not change
food slots, hours handling, the catalogs, or the app.

## 1. Goal and the properties that matter

1. A venue with `category == "bar"` can fill `afternoon_evening_tour`
   and no other slot. It never fills `morning_tour`, `lunch`, or
   `dinner`.
2. The rule is enforced in the shared slot helpers, so generation
   (`pack_day`), swap candidates, and swap confirm all follow it
   without separate code paths.
3. Every other category keeps today's behaviour exactly. Food venues
   still go to lunch/dinner, other activities still go to either
   activity slot, whole-day excursions still follow their own rule.
4. If a day's only remaining slot is `morning_tour` (for example a
   hotel-checkout day), a bar is simply not placed there. The planner
   already skips a slot honestly when no candidate fits; do not add a
   fallback that forces a bar in.
5. No catalog edit. `data/nungwi_tanzania.json` and the other catalogs
   stay as they are.

## 2. Preflight (do this first, stop if any check fails)

1. `git fetch origin`. Work from the `origin/main` SHA given in the
   message that sent you this brief. If `origin/main` has moved past
   it, say so and continue from the newer main only if it still
   contains every file in step 2; otherwise stop.
2. Confirm on that main these files exist: this brief,
   `services/day_slots.py`, `services/catalog_itinerary.py`,
   `tests/test_spec41_window_packing.py`,
   `docs/ENGINEERING_RULES.md`.
3. Confirm `tests/test_spec41_bar_slot.py` does NOT exist and
   `origin/feat/spec41-bar-slot-rule` does not exist. If either
   exists, stop and report.
4. Confirm `config.regions.REGIONS` contains `nungwi_tanzania` and
   `zanzibar_tanzania` (the Tanzania packs landed in PR #203 and
   #206). If not, stop and report.
5. Create a fresh branch from that main:
   `feat/spec41-bar-slot-rule`.

Never start work from an older SHA. Check the base before you write a
line.

## 3. Read before editing (read only; these are your patterns)

- `docs/ENGINEERING_RULES.md`: R14 (ASCII), R16 (no hard-coded pytest
  totals in docs; this slice writes no docs), R17 (a guard that cannot
  fail is not a guard).
- `services/day_slots.py` in full: `_FOOD_CATEGORIES`,
  `_ACTIVITY_SLOTS`, `is_food_venue`, `has_matching_slot`,
  `assign_slot`, `venue_fits_slot`. These three functions are the only
  places that decide which slot a venue may take.
- `services/catalog_itinerary.py`: `pack_day` (the slot loop calls
  `_venue_fits_slot`), `is_swap_eligible_venue` (calls `venue_fits_slot`
  when a target slot is named), `_slot_accepts_start`,
  `_slot_floor_utc`. Read only; you should not need to edit this file.
- `tests/test_spec41_window_packing.py`: the helpers `_make_hours`,
  `_make_venue_row`, `_ict_to_utc`, and the existing tests that include
  `category="bar"` (`test_morning_lunch_evening_chronological` and
  `test_category_diversity_remains_observable`). Copy the helpers you
  need into the new test file; do not import across test files.

## 4. Files you may touch

- `services/day_slots.py`
- `tests/test_spec41_bar_slot.py` (new)

Nothing else. In particular do NOT change:

- `services/catalog_itinerary.py`, `routers/**`, `agents/**`
- any `data/*.json` catalog, `scripts/load_venues.py`, `seed_data.py`
- any existing test file (do not edit, delete, or loosen a line)
- `config/**`, `monitoring/**`, `tests/conftest.py`
- `mobile/**`, SQL, requirements, any doc, any brief

Do not write a new brief or any doc. Do not start another slice.

## 5. The change: `services/day_slots.py`

ASCII only. Keep the change small.

### 5.1 Constant

Add next to `_FOOD_CATEGORIES`:

    # Categories that only make sense in the afternoon/evening slot. A bar at
    # 08:00 is a planner defect (owner field test, 2026-11-14).
    _AFTERNOON_ONLY_CATEGORIES: frozenset = frozenset({"bar"})

Do not add other categories. `night_market` already relies on its own
evening opening hours and is out of scope.

### 5.2 Helper

Add a small public helper:

    def is_afternoon_only_venue(venue: dict) -> bool:
        """True if the venue may only fill the afternoon/evening slot."""

It compares `(venue.get("category") or "").lower()` against the
constant.

### 5.3 The three decision points

Update, in this order of precedence (whole-day excursion first, then
the new rule, then food, then generic activity):

- `has_matching_slot`: a bar matches only when
  `"afternoon_evening_tour"` is in `remaining_slots`.
- `assign_slot`: a bar is assigned `afternoon_evening_tour` and that
  slot is removed from the returned list; if that slot is not
  available, raise `ValueError("No afternoon slot available")`. It
  never returns `morning_tour`.
- `venue_fits_slot`: a bar fits only when
  `target_slot == "afternoon_evening_tour"`.

A bar that also carries a whole-day vibe tag keeps the whole-day rule
(do not change the whole-day branch); the new rule applies to bars that
are not whole-day excursions. Write the new branch after the whole-day
branch so existing whole-day behaviour is byte-identical.

Update the module docstring with one sentence naming the new rule.

## 6. Tests: `tests/test_spec41_bar_slot.py`

No network, no database. Copy `_make_hours`, `_make_venue_row`,
`_ict_to_utc` (and any tiny constant such as `_ALL_DAYS`) from
`tests/test_spec41_window_packing.py` into this file.

Exact test names (each must exist; add more only if they add proof):

1. `test_bar_does_not_fit_morning_tour`
   `venue_fits_slot({"category": "bar"}, "morning_tour", list(SLOT_ORDER))`
   is False.

2. `test_bar_fits_afternoon_evening_tour_only`
   Same call is True for `afternoon_evening_tour`, and False for
   `lunch` and `dinner`.

3. `test_other_categories_keep_their_slots`
   A table check: `temple`, `museum`, `market`, `viewpoint` fit both
   activity slots and not lunch/dinner; `restaurant`, `cafe`,
   `street_food` fit lunch/dinner only; `night_market` fits both
   activity slots (unchanged). Use `SLOT_ORDER` as remaining slots.

4. `test_has_matching_slot_for_bar_needs_the_afternoon_slot`
   `has_matching_slot(bar, ["morning_tour"])` is False.
   `has_matching_slot(bar, ["morning_tour", "afternoon_evening_tour"])`
   is True. `has_matching_slot(bar, ["lunch", "dinner"])` is False.

5. `test_assign_slot_gives_a_bar_the_afternoon_slot`
   With the full slot list the bar gets `afternoon_evening_tour` and
   the returned list is `["morning_tour", "lunch", "dinner"]`. With
   `["morning_tour"]` only, `assign_slot` raises `ValueError`.

6. `test_whole_day_bar_keeps_the_whole_day_rule`
   A `bar` with a whole-day vibe tag (for example `"whole_day"`) still
   fits `morning_tour` when morning, lunch and afternoon are all
   remaining. This proves the whole-day branch was not changed.

7. `test_pack_day_never_places_a_bar_in_the_morning`
   Region `nungwi_tanzania`, day start 08:00 destination-local (use
   `ZoneInfo("Africa/Dar_es_Salaam")` to build the UTC instant; do not
   use the Lao timezone). Pool: one `bar` with empty hours
   (`_make_hours({})`), two `viewpoint` rows, two `restaurant` rows,
   each with coordinates the packer accepts (copy the coordinate
   fields `_make_venue_row` sets; if it does not set lat/lng, add
   them). Call `pack_day(rows, 4, start, "nungwi_tanzania", set())`.
   Assert: the bar is not the first node; no node whose venue is the
   bar has `slot_name == "morning_tour"`; and, if the bar is placed,
   its `slot_name == "afternoon_evening_tour"`. Also assert the first
   node is one of the viewpoints. Derive nothing from hard-coded
   totals beyond the pool you built.

8. `test_pack_day_bar_only_pool_leaves_the_morning_empty`
   Pool of one `bar` plus two restaurants, no activity venues. The
   result must contain no node with `slot_name == "morning_tour"`
   (the planner skips the slot honestly), and the bar, if placed, is
   `afternoon_evening_tour`.

9. `test_swap_eligibility_rejects_a_bar_for_a_morning_target`
   `is_swap_eligible_venue(bar_row, "morning_tour")` is False and
   `is_swap_eligible_venue(bar_row, "afternoon_evening_tour")` is
   True. Build `bar_row` the same way existing swap-eligibility rows
   are built (read `is_swap_eligible_venue` first for the keys it
   needs: coordinates, category, and so on). If it needs a field you
   cannot satisfy without editing production code, stop and report.

10. `test_day_slots_module_is_ascii`
    Read `services/day_slots.py` and assert `.isascii()`.

Existing tests (including both bar tests in
`test_spec41_window_packing.py`) stay green and unedited. If one of
them fails because of this change, stop and report it; do not edit it.

## 7. R17 sabotage (required, and must be reported)

Two sabotage runs, each restored before the next. No repo file may
keep the sabotage.

A. Remove the bar branch from `venue_fits_slot` only (so a bar fits
   `morning_tour` again). Under that sabotage these must fail:
   `test_bar_does_not_fit_morning_tour`,
   `test_pack_day_never_places_a_bar_in_the_morning`,
   `test_swap_eligibility_rejects_a_bar_for_a_morning_target`.

B. Make `has_matching_slot` ignore the bar rule. Under that sabotage
   `test_has_matching_slot_for_bar_needs_the_afternoon_slot` must fail.

Report which other named tests failed under each run. If in-place
editing is blocked, an in-memory pytest plugin that patches the
function is the accepted substitute; drop every plugin before the PR.
Confirm the hash of `services/day_slots.py` is identical before A and
after the last restore.

## 8. Stop rules

Stop and report instead of improvising if:

- any preflight check in section 2 fails;
- an existing test fails for a reason related to this change;
- an existing test fails for any other reason not named in section 9;
- you feel you need to edit a file outside section 4;
- you are about to add another category to the rule, edit a catalog,
  change `pack_day`, add a time floor for bars, or write a fallback
  that forces a bar into a slot;
- you are about to write a brief, a doc, or a second slice.

Never "fix" an unrelated failure, never skip or xfail a test, never
loosen an assertion, never force-push over another branch.

## 9. Gates

Run from the repo root, with `backend/.venv` if it exists. Use
`ruff==0.16.3` (CI pin). A newer ruff is not the gate.

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

Known pre-existing failures. These are not yours; do not touch them:

- `test_sparse_create_with_limited_hours_succeeds` (hard-coded date)
- `test_today_tonight_includes_venue_name` (fails near ICT midnight)

Anything else failing is yours until proven otherwise. Confirm touched
files are ASCII only. If `ruff format --check .` fails on a file you
are not allowed to edit, stop and report; do not reformat it.

Dart / Flutter checks are not part of this slice. Do not run them.

## 10. Out of scope (record as remainders, do not build)

- A local-time floor for bars (for example not before 16:00); this
  slice only keeps bars out of the morning
- Other evening-leaning categories or `night_market` handling
- Editing catalog categories or hours (owner field verification)
- Generic `leisurely` vibe tags in the Tanzania catalogs
- Any SPEC-41 text amendment (the planner records it after merge)
- Frontend findings F1-F4 in `UX_BACKLOG.md`
- Gap 4 remainders, deploy, APK

## 11. Delivery

1. Commit on `feat/spec41-bar-slot-rule` with the message:
   `SPEC-41: bars fill only the afternoon/evening slot`.
2. Push that branch. Verify the pushed SHA from the remote
   (`git ls-remote origin feat/spec41-bar-slot-rule`), not from your
   local clone.
3. Do not merge, do not deploy, do not open or edit any other branch.
   This compute has no `gh`; the reviewer opens the PR from your
   branch. Do not try to work around that.

## 12. Report (exactly these fields, in this order)

1. Base `origin/main` SHA you started from.
2. Branch name and pushed SHA (verified from the remote).
3. `pytest` last line, and the name of every failing test.
4. `ruff check`, `ruff format --check`, `git diff --check` results
   (name the ruff version).
5. Files touched (must be only those in section 4).
6. Test 7 and 8 detail: the node names and `slot_name` values in
   order for each result.
7. Confirmation the two existing bar tests in
   `test_spec41_window_packing.py` stayed green and unedited.
8. Confirmation `services/catalog_itinerary.py` and every catalog file
   have an empty diff.
9. The R17 tests that failed under sabotage A and B, by name, and
   confirmation the sabotage was removed and the `day_slots.py` hash
   matches the pre-sabotage hash.
10. Anything you were unsure about, or anything you chose not to do.

Do not edit this brief, `PROJECT_STATUS`, or `HANDOFF`.
