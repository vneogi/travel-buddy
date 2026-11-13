# Genie brief: Zanzibar owner field-test city pack (thin, exception)

Read this whole file before touching anything. It is the complete job.
If something here conflicts with your memory of an earlier brief, this
file wins. If something here is unclear, stop and ask; do not guess and
do not widen scope.

## 0. Context in one paragraph

The owner will spend four nights on Zanzibar around end of December 2026
with no fixed itinerary, using the app as an owner field test. SPEC-13
and SPEC-20 (the real city-pack factory) are specified and not built.
MARKET_STRATEGY says adding a city is still a code change and Bangkok is
the first factory acceptance city. This brief is an explicit
**owner field-test exception**, not the factory. It registers one city,
`zanzibar_tanzania` (Stone Town defaults), with a curated catalog large
enough to create and swap a multi-day trip. No corridor. No Dar. No
Arusha. No SPEC-13/20 implementation.

Gap 4 export route `GET /api/v1/me/export` is on main (`16945be`,
PR #199). Do not continue Gap 4 in this branch.

## 1. Goal and the one property that matters

After this slice, an authenticated create for `geo_region:
"zanzibar_tanzania"` seeds a day from the Zanzibar catalog only: every
node's coordinates sit inside the Zanzibar bounding box, every venue
name comes from `data/zanzibar_tanzania.json`, and no Dubai fixture name
and no Laos venue appears. `supported_regions` advertises
`zanzibar_tanzania` only when the catalog passes
`select_day_venues`. Flutter shows the city, uses UTC+3, and resolves
Stone Town coordinates without falling back to Dubai.

## 2. Preflight (do this first, stop if any check fails)

1. `git fetch origin`. Work from the `origin/main` SHA given in the
   message that sent you this brief. If `origin/main` has moved past
   it, say so and continue from the newer main only if it still
   contains every file in step 2; otherwise stop.
2. Confirm on that main: this brief, `config/regions.py`,
   `services/catalog_itinerary.py`, `scripts/load_venues.py`,
   `seed_data.py`, `data/laos_luang_prabang.json`,
   `mobile/lib/data/region_defaults.dart`,
   `mobile/lib/core/destination_tz.dart`,
   `tests/test_laos_trip_create.py`,
   `docs/ENGINEERING_RULES.md`,
   `docs/MARKET_STRATEGY.md` (read the "adding a city is still a code
   change" section so you know this brief is the exception it warns
   about).
3. Confirm `data/zanzibar_tanzania.json` does NOT exist, and
   `origin/feat/zanzibar-field-test-pack` does not exist. If either
   exists, stop and report.
4. Create a fresh branch from that main: `feat/zanzibar-field-test-pack`.

Never start from an older SHA.

## 3. Read before editing (read only)

- `docs/ENGINEERING_RULES.md` (R14, R16, R17)
- `docs/specs/SPEC-08-laos-venue-curation.md` (catalog wrapper shape,
  closed vocab mindset, coverage lessons: massage/spa and hours matter)
- `docs/specs/SPEC-32-real-laos-trip-creation.md` (create path)
- `config/regions.py` (registry; the "no other file needs changing"
  comment is false -- this brief lists every mirror)
- `scripts/load_venues.py` (`VALID_CATEGORIES`, `get_bounding_box`,
  `REGION_CURRENCIES`, `REGION_LANGUAGES`, validate + dry-run)
- `services/catalog_itinerary.py` (`advertised_regions`,
  `select_day_venues`, `CATEGORY_BUCKETS`, `MIN_STOPS`,
  `DUBAI_FIXTURE_NAMES`)
- `seed_data.py` (`LAOS_CATALOG_FILES`, `_seed_laos_catalogs`, the
  hardcoded `"lo"` language map)
- `tests/test_laos_trip_create.py` (create assertions and sabotage
  proofs to mirror for Zanzibar)
- Flutter mirrors:
  `mobile/lib/data/region_defaults.dart`,
  `mobile/lib/core/destination_tz.dart`,
  `mobile/lib/features/create_trip/create_trip_screen.dart`,
  `mobile/lib/features/itinerary/date_scope.dart`,
  `mobile/lib/features/booking/add_booking_sheet.dart`,
  `mobile/lib/features/booking/booking_parser.dart`,
  `mobile/test/spec37_destination_tz_test.dart`,
  `mobile/test/spec34_location_test.dart`

## 4. Files you may touch

Allowed (only these):

- `config/regions.py`
- `scripts/load_venues.py` (bbox, currency, language maps; no unrelated
  refactors)
- `services/catalog_itinerary.py` (add `zanzibar_tanzania` to the
  `advertised_regions` preferred list only)
- `seed_data.py` (seed the Zanzibar catalog; stop hardcoding `"lo"` for
  every catalog -- map language by region)
- `data/zanzibar_tanzania.json` (new)
- `tests/test_laos_trip_create.py` (extend / adjust assertions that
  hardcode the old four-region set; do not weaken Laos proofs)
- `tests/test_zanzibar_trip_create.py` (new; Zanzibar create + bbox +
  advertisement proofs)
- `mobile/lib/data/region_defaults.dart`
- `mobile/lib/core/destination_tz.dart`
- `mobile/lib/features/create_trip/create_trip_screen.dart`
- `mobile/lib/features/itinerary/date_scope.dart`
- `mobile/lib/features/booking/add_booking_sheet.dart`
- `mobile/lib/features/booking/booking_parser.dart`
- `mobile/test/spec37_destination_tz_test.dart`
- `mobile/test/spec34_location_test.dart`

Do NOT change:

- `config/corridors.py` (no Tanzania corridor)
- any `services/data_rights_*`, `routers/me_router.py`, Gap 4 tests
- SPEC-13 / SPEC-20 / any `packs/` factory work
- Dubai catalog, Laos JSON catalogs (except reading them)
- `monitoring/`, deploy configs, docs other than nothing -- do not edit
  docs, briefs, PROJECT_STATUS, or HANDOFF
- Hosted Supabase load is out of band; make dry-run validation pass.
  Do not apply migrations or touch production.

## 5. Region registration

### 5.1 Code `zanzibar_tanzania`

Add to `REGIONS` in `config/regions.py`:

- `code`: `zanzibar_tanzania`
- `display_name`: `Zanzibar`
- `country`: `Tanzania`
- `default_lat` / `default_lng`: Stone Town centre, approximately
  `-6.1659`, `39.1917` (use five decimals; coords must sit inside the
  bbox in section 5.2)
- `currency`: `TZS`
- `language_hint`: short, honest (Swahili and English common in Stone
  Town tourist areas; less English outside)
- `timezone`: `Africa/Dar_es_Salaam` (EAT, UTC+3, no DST)

`require_region("zanzibar_tanzania")` must succeed.
`require_region` for unknown codes must still raise.

### 5.2 Bounding box (critical)

Today `scripts/load_venues.get_bounding_box` returns the Dubai box when
`"dubai"` is in the code, otherwise the **Laos** box. Zanzibar
coordinates would fail validation, or worse, a future African city
would be checked against Laos.

Change `get_bounding_box` so:

1. `dubai` -> existing Dubai box (unchanged).
2. any `*_laos` code, or the legacy non-dubai path for Laos only ->
   existing Laos box (unchanged numbers).
3. `zanzibar_tanzania` -> Unguja box, generous but not mainland Dar:

   - lat about `-6.50` .. `-5.70`
   - lng about `39.10` .. `39.60`

4. Any other unknown region -> raise `ValueError` (do not silently
   return Laos). Tests must cover that.

Also add `zanzibar_tanzania` to `REGION_CURRENCIES` (`TZS`) and
`REGION_LANGUAGES` (`sw`).

### 5.3 Advertisement

In `advertised_regions`, append `"zanzibar_tanzania"` to `preferred`
after the Laos cities. It must appear in `supported_regions` only when
`select_day_venues(list_venues("zanzibar_tanzania"))` succeeds.

## 6. Catalog: `data/zanzibar_tanzania.json`

Wrapper shape (same as Laos):

```json
{
  "geo_region": "zanzibar_tanzania",
  "curated_at": "YYYY-MM-DD",
  "curator_notes": "...",
  "venues": [ ... ]
}
```

ASCII-only JSON (escape non-ASCII in `name_local` as `\uXXXX` if you
include Swahili names). Real places only. Do not invent beaches, hotels,
or restaurants. Prefer well-known Stone Town and nearby west/east coast
Unguja venues a four-night walker could actually visit. Where you have
a Wikidata or OSM ref, put it in `name_local_ref` / notes; where hours
are unknown, set `opening_hours` to `null` rather than inventing times.

Closed `micro_location` vocabulary for this file (declare in
`curator_notes` and use only these):

- `stone_town`
- `forodhani_waterfront`
- `nungwi_north`
- `paje_southeast`
- `fengate_jambiani`
- `airport_corridor`

Coverage targets (minimums; more is fine if real):

| Bucket (map to VALID_CATEGORIES) | Min venues |
|---|---|
| Culture / history (`museum`, `gallery`, or heritage `experience` / walking) | 4 |
| Food (`restaurant`, `cafe`, `street_food`, `market`) | 8 |
| Nature / beach / viewpoint (`nature`, `viewpoint`, `walking_area`, `beach` if valid else `nature`) | 6 |
| Rest (`massage_spa` or quiet `cafe`/`experience`) | 3 |
| Total eligible (lat/lng/name, not hospital/pharmacy/transport_hub) | >= 25 |

Use only categories from `VALID_CATEGORIES` in `load_venues.py`. If a
natural label is missing (for example beach), pick the closest valid
category and say so in `curator_notes`. Include `typical_dwell_minutes`,
`indoor_outdoor`, `price_band`, `audience`, `vibe_tags`, `description`.
Food venues should carry two to four dishes when you know them; skip
dishes rather than invent menus.

Gates on the catalog:

```
python3 scripts/load_venues.py data/zanzibar_tanzania.json --dry-run
```

must exit 0 with zero validation errors. Every venue lat/lng must fall
inside the Zanzibar bbox.

## 7. Seed path

Update `seed_data.py` so in-memory seed loads `data/zanzibar_tanzania.json`
the same way Laos catalogs load. Refactor the language argument so Laos
keeps `"lo"` and Zanzibar uses `"sw"` (or whatever
`REGION_LANGUAGES` says). Do not leave a hardcoded `"lo"` for all
catalog files. Preserve structured opening hours when present; keep the
existing flatten fallback behaviour.

## 8. Flutter mirrors

Add `zanzibar_tanzania` everywhere the Laos/Dubai codes are listed for
display or defaults:

- `RegionDefaults` coords = the same Stone Town defaults as the Python
  region
- `destination_tz` offset = `3` (EAT)
- Display-name maps in create trip, date scope, add booking sheet:
  `'zanzibar_tanzania': 'Zanzibar'`
- `booking_parser.dart`: map strings containing `zanzibar` or
  `stone town` to `zanzibar_tanzania` (order heuristics so more
  specific matches win if needed)

Update `mobile/test/spec37_destination_tz_test.dart` and
`mobile/test/spec34_location_test.dart` to cover the new code (offset
+3, coords present, unknown still null). Do not weaken existing cases.

## 9. Named tests (Python)

New file `tests/test_zanzibar_trip_create.py` (plus necessary edits to
`tests/test_laos_trip_create.py` where it asserts the exact old region
set):

1. `test_zanzibar_region_registered_and_require_region`
2. `test_zanzibar_bbox_accepts_stone_town_and_rejects_laos_and_dubai_points`
   (unit-test `get_bounding_box` / validation)
3. `test_get_bounding_box_unknown_region_raises`
4. `test_zanzibar_catalog_dry_run_and_select_day_venues`
5. `test_trips_advertise_zanzibar_when_catalog_seeded`
6. `test_create_zanzibar_uses_catalog_not_dubai_or_laos`
   Create with `geo_region: "zanzibar_tanzania"`. Assert 4..6 nodes,
   every name in the Zanzibar catalog, no `DUBAI_FIXTURE_NAMES`, every
   lat/lng inside the Zanzibar bbox, every `geo_region` on the node is
   `zanzibar_tanzania`.
7. `test_empty_zanzibar_catalog_is_not_advertised`
   (same pattern as the Laos empty-catalog test)

Exact R17 sabotage (section 11) must make test 6 or test 2 fail.

Do not hard-code pytest suite totals (R16).

## 10. R17 sabotage

Exact temporary edit: in `get_bounding_box`, make `zanzibar_tanzania`
fall through to the Laos box (the old default).

Expected: Zanzibar catalog dry-run or create-path bbox assertions fail
(`test_zanzibar_bbox_accepts_stone_town_and_rejects_laos_and_dubai_points`
and/or `test_create_zanzibar_uses_catalog_not_dubai_or_laos`). Restore
before the PR. In-memory pytest plugin wrapping `get_bounding_box` is
an accepted substitute if in-place edit is blocked. No sabotage
artifact in the commit.

## 11. Stop rules

Stop and report if:

- you cannot find enough **real** venues without inventing;
- you feel you must implement SPEC-13/20 or a corridor;
- an existing Laos/Dubai test fails for a reason outside the intentional
  region-set assertion updates;
- `load_venues.py --dry-run` fails and the fix would require editing a
  disallowed file;
- you are about to edit docs or start Gap 4 work.

Never invent opening hours to silence warnings. Never force-push.
Never "fix" unrelated failures (`test_sparse_create_with_limited_hours_succeeds`,
`test_today_tonight_includes_venue_name`).

## 12. Out of scope (remainders)

- SPEC-13 / SPEC-20 factory and `packs/`
- Dar es Salaam, Arusha, safari corridor, multi-city Tanzania
- Hosted `load_venues.py` apply to production Supabase (owner/ops)
- Nesting export document, Flutter leave/wipe, tombstones, GET rate
  limit
- Armor, Play Integrity, store listing, non-owner Test Track
- ODbL bulk OSM ingest (hand curation only for this exception)

## 13. Gates

Use `ruff==0.16.3` for Python. From repo root:

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
python3 scripts/load_venues.py data/zanzibar_tanzania.json --dry-run
git diff --check
```

Flutter (required because mirrors changed):

```
cd mobile && dart analyze lib test
cd mobile && flutter test test/spec37_destination_tz_test.dart test/spec34_location_test.dart
```

If the full Flutter suite is feasible on the compute, run it; if not,
report which subset ran. Do not skip analyze on touched Dart files.
ASCII only on touched text files (JSON may use `\u` escapes).

## 14. Delivery

1. Commit on `feat/zanzibar-field-test-pack` with message:
   `Zanzibar field-test pack: register zanzibar_tanzania catalog and mirrors`.
2. Push and verify the SHA from `git ls-remote`.
3. Do not merge, deploy, or open other branches. No `gh` on this
   compute; the reviewer opens the PR.

## 15. Report (exactly these fields, in this order)

1. Base `origin/main` SHA.
2. Branch and pushed SHA (from the remote).
3. pytest last line + every failing test name.
4. ruff check / format / dry-run / flutter analyze + test results.
5. Files touched (must be a subset of section 4).
6. Venue count by category bucket and total eligible.
7. Create-trip proof: node count, all names subset of catalog, bbox
   check, no Dubai/Laos leakage.
8. `supported_regions` includes `zanzibar_tanzania` when seeded.
9. R17: which tests failed under sabotage; confirmation restore.
10. Anything unsure, invented-vs-sourced judgement calls, or skipped
    Flutter surface.

Do not edit this brief, PROJECT_STATUS, or HANDOFF.
