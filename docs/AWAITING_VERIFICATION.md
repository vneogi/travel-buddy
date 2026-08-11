# Awaiting Verification

No test laptop available until roughly Aug 17 2026. Nothing below can be
verified on device or against real Supabase until then.

pytest is the only real verification available in this window. Anything
touching Dart, PowerShell, or a live database is marked UNVERIFIED.

This file is a dated log. It is expected to go stale, and it is the only
place in the repo where dated observations belong (R16).

## A note on commit numbers

Earlier revisions of this file tracked work as `#84`, `#85`, `#86` and so
on. Those numbers cannot be reconciled against `git log` and had already
drifted, so they are dropped. Commits are identified by SHA only.

## Verified via pytest

### arrival_delta server derivation -- 564fd7d

Derives `arrival_delta` from `visited_confirmed.captured_at` against
`node.scheduled_start`, so one tap yields two data points. Covered by
`services/arrival_delta_service.py` and `tests/test_arrival_delta.py`.
This is DONE. Earlier revisions of PROJECT_STATUS.md listed it as the
next task, contradicting this file.

## Awaiting device verification

| SHA | Date | What | Verify with |
|-----|------|------|-------------|
| 21249f4 | Aug 9 | fix(dart): 4 compile errors plus lint warnings | `flutter analyze && flutter test` |
| 951f0ca | Aug 9 | feat(spec-07): wire typed signal methods to the UI | `flutter analyze && flutter test` |
| c6712bb | Aug 9 | fix(scripts): purge non-ASCII from all .ps1, add UTF-8 BOM | `.\scripts\smoke-test.ps1` |
| f778d8f | Aug 9 | feat(glossary): scripts/load_dish_glossary.py | run against live Supabase, then `--report-fk` |
| 1e0d999 | Aug 9 | fix(scripts): open data files as utf-8 | re-run the loaders on Windows |
| 10d27dd | Aug 9 | fix(venues): dict-wrapped JSON plus Laos vocabulary | see finding 1 below -- partly reverted |

`b47bce6` is documentation only and needs no verification.

## Known open issues

### High -- the venue loader cannot load the Laos data

The vocabulary expansion committed in `10d27dd` was reverted by the merge
`c5f64f3` twenty minutes later. On `main` today the VALID_* sets are back
to their pre-Laos state, so validating the three Laos files fails on
vocabulary for a large share of the 58 venues. Missing values include:

- categories: `street_food`, `walking_area`, `river_activity`, `craft_workshop`
- vibe tags: `photogenic`, `local_favourite`, `touristy`
- audiences: `solo`, `friends_group`, `seniors`, `mobility_limited`
- indoor_outdoor: `mixed`
- price bands: `mid`, `splurge`, `free`
- cuisines: `french_colonial`, `drink`

`FOOD_CATEGORIES` still lists `street_food`, which is no longer in
`VALID_CATEGORIES` -- the two sets disagree.

The data currently in Supabase was loaded before the revert, so the
database is fine and the script is not. Restoring the vocabulary is part
of the loader rewrite.

### High -- load_venues.py raises NameError without --geo-region

`file_geo_region` is read in the geo_region inference chain but is never
assigned. Every invocation that does not pass `--geo-region` explicitly
crashes, including the command printed in PROJECT_STATUS.md.

### High -- 145849d claim 2 did not land

That commit states `collect_warnings` was restored to
`{v.get("category") for v in venues}`. On `main` the line is still:

    cats = {v.get("opening_hours_structured") is None and v.get("opening_hours") is None}

So `"massage_spa" not in cats` is always true and every region is warned
as having zero massage_spa venues. The sibling fix in the same commit
(`startswith(f"{filepath}:")` instead of a substring match) did land.
A partial hunk landing on a non-ASCII file, the same failure mode that
left PROJECT_STATUS.md half-rebuilt. Do not trust that commit message.

### High -- halal plus pork passes the allergen check

There is no `LABEL_EXCLUDES_ALLERGENS` rule for halal, so a dish labelled
halal that contains pork validates cleanly. Safety hole for Muslim
travellers. Needs a rule plus a test.

### High -- venues_rag schema drift

The loader writes `typical_dwell_minutes`, `indoor_outdoor` and
`price_band` to `venues_rag`, and no migration defines those columns.
`name_local` and `nearest_landmark` are also absent, which is what blocks
SPEC-12 driver cards. A database rebuilt from `supabase/migrations/`
today fails on load.

### Medium -- hybrid_venue_search geo_region parameter

`supabase_service` passes a `geo_region` filter to the RPC, and the
function defined in `0001_initial_schema.sql` does not declare that
parameter. Either the live function has drifted from the migration or the
filter is silently ignored. Verify against the live database.

### Medium -- Supabase env var name mismatch

`scripts/load_venues.py` reads `TB_SUPABASE_URL` and `TB_SUPABASE_KEY`.
Parts of the documentation say `TB_SUPABASE_SERVICE_KEY`. Confirm which
name the settings layer expects and make all three agree.

### Medium -- opening_hours null on all 58 Laos venues

The loader field-name fix is committed but the data was never re-loaded,
so the scheduler has no hours to respect for any Laos venue.

### Low -- mobility_limited overcorrected

Flagged on roughly two thirds of venues, which makes it useless as a
filter.

### Low -- VALID_DISH_CONTAINS lives in the wrong file

It sits in `scripts/load_dish_glossary.py` and belongs in
`config/dietary.py` (R5). Previously marked BLOCKED because
`config/dietary.py` contains em-dashes. It is no longer blocked: R14
documents the delete-and-recreate procedure, so `config/dietary.py` gets
rebuilt as pure ASCII with the constant moved in.

## Tooling incidents

### runGit outage, Aug 11 2026

A fresh session found `runGit` failing with `Git folder (Repo) has
invalid type` (`RESOURCE_DOES_NOT_EXIST`), after the previous session
died mid-task. The compute could still create files but could not delete,
move, or commit them, which blocks the entire R14 workaround. Repair is a
re-clone of the Databricks Git folder, not a retry. See R15.

### Half-landed documentation commit, 9fbe2f6

That commit rebuilt `PROJECT_STATUS.md` only partially, because R14
blocked the replacement of the em-dashed original. It left the new
summary prepended to the entire stale document, so the file asserted both
"8 signal types registered" and, further down, "Behavioral signals: NOT
STARTED". It also committed `PROJECT_STATUS.new.md` alongside it. Both
were resolved by rewriting the file through the GitHub API.

## Division of labour

Documentation and whole-file rewrites go through the GitHub API from the
planning side. The Databricks compute is reserved for code plus pytest.
This keeps documentation out of the R14 and R15 failure modes entirely.

## Files known to contain non-ASCII

These cannot be patched with `editAsset` and must be rebuilt (R14):

- `scripts/load_venues.py` (warning glyphs and an em-dash in output strings)
- `config/dietary.py` (em-dashes in comments)
- `config/regions.py` (box-drawing characters)
- `mobile/lib/features/itinerary/itinerary_screen.dart` (em-dash)
- `README.md` and `MASTER_BRD.md` (box-drawing diagrams)
- All Lao venue JSON files (Lao script, expected and correct)
