# Genie brief: Zanzibar owner field-test city pack (thin, exception)

Read this whole file before touching anything. It is the complete job.
If something here conflicts with your memory of an earlier brief, this
file wins. If something here is unclear, stop and ask; do not guess and
do not widen scope.

**Amendment 2026-11-13:** venue sourcing is done for you. Your only
venue source is `docs/briefs/inputs/zanzibar_candidates.json` (38 real
places, coordinates copied from OpenStreetMap). You need no network
access and must not use any. Dart/Flutter checks are NOT required of you
on this compute (see section 13).

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

Scope note: the day picker has no geographic clustering, so this
catalog deliberately stays within about 10 km of Stone Town (Stone Town,
Forodhani waterfront, two boat-trip islets, and the near west-coast
sites). Nungwi, Paje, Jambiani, Jozani and the other east and north
coast places are NOT in the catalog; mixing them into a day would
produce impossible itineraries. That is a recorded remainder.

## 2. Preflight (do this first, stop if any check fails)

1. `git fetch origin`. Work from the `origin/main` SHA given in the
   message that sent you this brief. If `origin/main` has moved past
   it, say so and continue from the newer main only if it still
   contains every file in step 2; otherwise stop.
2. Confirm on that main: this brief, `config/regions.py`,
   `services/catalog_itinerary.py`, `scripts/load_venues.py`,
   `seed_data.py`, `data/laos_luang_prabang.json`,
   `docs/briefs/inputs/zanzibar_candidates.json` (your only venue
   source; read it fully),
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
- `docs/briefs/inputs/zanzibar_candidates.json` (read only)
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

Build this file ONLY from `docs/briefs/inputs/zanzibar_candidates.json`.

Rules:

- Use all 38 candidate venues. Do not add a venue, do not drop one, and
  do not look anything up. If you believe a place is missing or wrong,
  stop and say so (section 11).
- Copy `lat`/`lng` exactly as given in the candidates file. Never round,
  nudge or "fix" a coordinate.
- Catalog `name` = candidate `name`. Put the candidate `osm_ref` in
  `name_local_ref` with `name_local_source` set to `osm`. If the
  candidate has a `wikidata` id, use that as `name_local_ref` with
  `name_local_source` set to `wikidata` instead. Do not write
  `name_local`; leave it out (no Swahili or Arabic names are verified).
- Catalog `category` = candidate `category_suggestion` (every value is
  already in `VALID_CATEGORIES`).
- Catalog `micro_location` = candidate `micro_location`.
- `opening_hours`: convert ONLY when `opening_hours_osm` is exactly one
  range of the form `Mo-Su HH:MM-HH:MM` or `Mo-Sa HH:MM-HH:MM` (seven
  or six days, same range every day). For every other venue set
  `opening_hours` to `null`. Never invent hours.
- Do NOT write `dishes`, `wheelchair_notes`, prices, or any other fact
  that is not in the candidates file. No dishes at all in this file.
- `description`: one or two plain sentences built only from the
  candidate `note` and name. No invented facts, no adjectives that claim
  quality ("best", "famous") unless the note says so.
- These fields are planner estimates, not verified facts, and must say
  so in `curator_notes`: `typical_dwell_minutes` (culture 45 to 60,
  food 45 to 60, rest 30 to 45, nature 30 to 90, Changuu 180,
  Nakupenda 180, Kidichi Spice Farm 90), `indoor_outdoor`, `has_aircon`
  (set `false` unless the candidate note says otherwise), `price_band`,
  `audience`, `vibe_tags`. Use `has_aircon: false` and conservative
  values; `price_band` `mid` for food unless it is a market or street
  food (`budget`), museums `budget`.
- `is_sponsored` false, `bid_weight` 0.0.

Wrapper shape (same as Laos):

```json
{
  "geo_region": "zanzibar_tanzania",
  "curated_at": "2026-11-13",
  "curator_notes": "...",
  "venues": [ ... ]
}
```

ASCII-only JSON.

`curator_notes` must state: the closed `micro_location` vocabulary
below; that data derives from OpenStreetMap (c) OpenStreetMap
contributors under ODbL 1.0 via an owner-only exception; that opening
hours, dwell, price band, audience and vibe tags are unverified planner
estimates; and that there is no massage/spa venue because none could be
verified (rest is served by quiet cafes).

Closed `micro_location` vocabulary for this file (use only these):

- `stone_town`
- `forodhani_waterfront`
- `west_outskirts`
- `offshore_islets`

Expected coverage (the candidates file has exactly this; it must hold
in your catalog):

| Bucket | Venues |
|---|---|
| culture | 12 |
| food (restaurant, cafe, street_food, market, bar) | 15 |
| rest (quiet cafe) | 4 |
| nature | 7 |
| total | 38 |

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
8. `test_zanzibar_catalog_matches_candidates_file`
   Load both files. Assert the venue name sets are identical (38), each
   venue's `lat`/`lng` equals the candidate's exactly, every venue's
   `category` equals `category_suggestion`, no venue carries `dishes`,
   and every venue whose candidate `opening_hours_osm` is not one of the
   two simple patterns has `opening_hours` equal to `None`.

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

- you feel you need the network, or a venue that is not in
  `zanzibar_candidates.json`, or to change a candidate coordinate;
- a candidate fails `load_venues.py --dry-run` or the bbox (report the
  venue and the error; do not edit the candidate file or its
  coordinates);
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
- ODbL bulk OSM ingest and the SPEC-21 review. This catalog is owner-only
  hand curation derived from OSM; wider use needs that review first
- Nungwi, Kendwa, Matemwe, Paje, Jambiani, Jozani, Mangapwani, Kizimkazi
  and other far-from-Stone-Town venues: needs geographic day clustering
  in the day picker, which does not exist
- Massage/spa venue in Stone Town (none verifiable in OSM)
- Swahili `name_local` values and dishes (not verified)

## 13. Gates

Use `ruff==0.16.3` for Python. From repo root:

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
python3 scripts/load_venues.py data/zanzibar_tanzania.json --dry-run
git diff --check
```

Flutter: this compute has no Dart or Flutter SDK. Do NOT try to install
one and do NOT use the network. Make the Dart edits carefully by
mirroring the exact existing pattern for the Laos codes, and in your
report write `dart analyze: not run (no SDK on compute)` and
`flutter test: not run (no SDK on compute)`. The pull request's CI
`flutter` job and the owner's local Flutter run are the gate before
merge, not you. Do not claim Dart passed.

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
4. ruff check / format / dry-run results. Dart checks: state `not run
   (no SDK on compute)`.
5. Files touched (must be a subset of section 4).
6. Venue count by category bucket and total eligible.
7. Create-trip proof: node count, all names subset of catalog, bbox
   check, no Dubai/Laos leakage.
8. `supported_regions` includes `zanzibar_tanzania` when seeded.
9. R17: which tests failed under sabotage; confirmation restore.
10. Anything unsure, invented-vs-sourced judgement calls, or skipped
    Flutter surface.

Do not edit this brief, PROJECT_STATUS, or HANDOFF.
