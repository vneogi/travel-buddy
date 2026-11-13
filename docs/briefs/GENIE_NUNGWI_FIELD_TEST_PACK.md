# Genie brief: Nungwi owner field-test pack (thin, exception, second Zanzibar region)

Read this whole file before touching anything. It is the complete job.
If something here conflicts with your memory of an earlier brief, this
file wins. If something here is unclear, stop and ask; do not guess and
do not widen scope.

You need no network access and must not use any. All venue data is in
`docs/briefs/inputs/nungwi_candidates.json`. Dart/Flutter checks are NOT
required of you on this compute (see section 13).

## 0. Context in one paragraph

The owner's home base for four nights at end of December 2026 is
**Nungwi**, on the northern tip of Zanzibar (Unguja), about an hour and
a half by road from Stone Town. The Stone Town pack (`zanzibar_tanzania`,
PR #203) is the day-trip catalog. The day picker has no geographic
clustering, so Nungwi venues must NOT be added to the Stone Town catalog;
mixing them would produce impossible days. This brief registers a
second, separate region, `nungwi_tanzania`, with its own catalog built
only from the verified candidates file. Like the Stone Town pack, it is
an explicit **owner field-test exception**, not the SPEC-13/20 factory.
No corridor. No change to the Stone Town catalog.

## 1. Goal and the one property that matters

After this slice, an authenticated create for `geo_region:
"nungwi_tanzania"` seeds a day from the Nungwi catalog only: every node
sits inside the Nungwi bounding box, every venue name comes from
`data/nungwi_tanzania.json`, and no Stone Town (`zanzibar_tanzania`)
venue, Laos venue or Dubai fixture appears. The reverse also holds: a
`zanzibar_tanzania` create contains no Nungwi venue.
`supported_regions` advertises `nungwi_tanzania` only when its catalog
passes `select_day_venues`. Flutter shows the city, uses UTC+3, resolves
Nungwi coordinates, and a booking that mentions Nungwi or Kendwa maps to
`nungwi_tanzania` even when it also says "Zanzibar".

Why the bbox alone is not the proof: the Zanzibar (Unguja) box already
contains Nungwi. Leakage is proven by name sets, not coordinates.

## 2. Preflight (do this first, stop if any check fails)

1. `git fetch origin`. Work from the `origin/main` SHA given in the
   message that sent you this brief. If `origin/main` has moved past it,
   say so and continue from the newer main only if it still contains
   every file in step 2; otherwise stop.
2. Confirm on that main:
   - this brief and `docs/briefs/inputs/nungwi_candidates.json` (your
     only venue source; read it fully, including `rules`);
   - the merged Stone Town pack: `data/zanzibar_tanzania.json`,
     `tests/test_zanzibar_trip_create.py`, `zanzibar_tanzania` in
     `config/regions.py`, the `ValueError` branch in
     `scripts/load_venues.get_bounding_box`, and `CATALOG_FILES` /
     `CATALOG_LANGUAGES` in `seed_data.py`.
     **If any of these is missing, PR #203 has not merged: stop and
     report. Do not rebuild the Stone Town pack.**
   - `services/catalog_itinerary.py`, `docs/ENGINEERING_RULES.md`.
3. Confirm `data/nungwi_tanzania.json` does NOT exist and
   `origin/feat/nungwi-field-test-pack` does not exist. If either exists,
   stop and report.
4. Create a fresh branch from that main: `feat/nungwi-field-test-pack`.

Never start from an older SHA.

## 3. Read before editing (read only)

- `docs/ENGINEERING_RULES.md` (R14, R16, R17)
- `docs/briefs/GENIE_ZANZIBAR_FIELD_TEST_PACK.md` (the pattern you are
  repeating; section 6 rules apply here unless this brief overrides them)
- `tests/test_zanzibar_trip_create.py` (mirror its structure and helpers)
- `config/regions.py`, `scripts/load_venues.py` (`get_bounding_box`,
  `REGION_CURRENCIES`, `REGION_LANGUAGES`, `VALID_CATEGORIES`,
  `INTENTIONALLY_NOT_PERSISTED`), `seed_data.py`,
  `services/catalog_itinerary.py` (`advertised_regions`,
  `CATEGORY_BUCKETS`)
- Flutter: `mobile/lib/data/region_defaults.dart`,
  `mobile/lib/core/destination_tz.dart`,
  `mobile/lib/features/create_trip/create_trip_screen.dart`,
  `mobile/lib/features/itinerary/date_scope.dart`,
  `mobile/lib/features/booking/add_booking_sheet.dart`,
  `mobile/lib/features/booking/booking_parser.dart` (`_inferGeoRegion`),
  `mobile/test/spec37_destination_tz_test.dart`,
  `mobile/test/spec34_location_test.dart`,
  `mobile/test/features/booking/booking_test.dart` (the
  `extractBookingFromText(...).geoRegion` pattern)

## 4. Files you may touch

Allowed (only these):

- `config/regions.py`
- `scripts/load_venues.py` (bbox branch, currency, language maps only)
- `services/catalog_itinerary.py` (append `nungwi_tanzania` to the
  `advertised_regions` preferred list only)
- `seed_data.py` (add the catalog file and its language; nothing else)
- `data/nungwi_tanzania.json` (new)
- `tests/test_nungwi_trip_create.py` (new)
- `tests/test_zanzibar_trip_create.py` (ONLY if an assertion there breaks
  because a second Tanzania region now exists; do not weaken any Stone
  Town proof, and say exactly what you changed and why)
- `mobile/lib/data/region_defaults.dart`
- `mobile/lib/core/destination_tz.dart`
- `mobile/lib/features/create_trip/create_trip_screen.dart`
- `mobile/lib/features/itinerary/date_scope.dart`
- `mobile/lib/features/booking/add_booking_sheet.dart`
- `mobile/lib/features/booking/booking_parser.dart`
- `mobile/test/spec37_destination_tz_test.dart`
- `mobile/test/spec34_location_test.dart`
- `mobile/test/features/booking/booking_test.dart`

Do NOT change:

- `data/zanzibar_tanzania.json`, any Laos or Dubai catalog
- `docs/briefs/inputs/*.json` (read only)
- `config/corridors.py` (no corridor)
- `INTENTIONALLY_NOT_PERSISTED`, `VENUES_RAG_WRITE_COLUMNS`, migrations
- any `services/data_rights_*`, `routers/me_router.py`, Gap 4 tests
- `monitoring/`, deploy configs, SPEC-13/20 / `packs/`
- docs, briefs, PROJECT_STATUS, HANDOFF
- Hosted Supabase: no apply. Dry-run only.

## 5. Region registration

### 5.1 Code `nungwi_tanzania`

Add to `REGIONS` in `config/regions.py`, directly after
`zanzibar_tanzania`, with the same owner-exception comment style:

- `code`: `nungwi_tanzania`
- `display_name`: `Nungwi (Zanzibar)`
- `country`: `Tanzania`
- `default_lat` / `default_lng`: `-5.72720`, `39.29920` (Nungwi village
  centre, OSM node 27251888)
- `currency`: `TZS`
- `language_hint`: `Swahili; English common at beach restaurants and
  hotels, less in the village`
- `timezone`: `Africa/Dar_es_Salaam`

### 5.2 Bounding box

Add an explicit branch in `get_bounding_box`, alongside the Zanzibar one:

- `nungwi_tanzania` -> lat `-5.78` .. `-5.70`, lng `39.27` .. `39.33`
  (Nungwi and Kendwa; excludes Stone Town at about -6.17)

Use named module constants like the Zanzibar box. Do not change the
Dubai, Laos or Zanzibar boxes, and keep the `ValueError` for unknown
regions. Add `nungwi_tanzania` to `REGION_CURRENCIES` (`TZS`) and
`REGION_LANGUAGES` (`sw`).

### 5.3 Advertisement

Append `"nungwi_tanzania"` to `preferred` in `advertised_regions`,
immediately after `"zanzibar_tanzania"`.

### 5.4 Seed

Append `DATA_DIR / "nungwi_tanzania.json"` to `CATALOG_FILES` and
`"nungwi_tanzania": "sw"` to `CATALOG_LANGUAGES`. No other seed change.

## 6. Catalog: `data/nungwi_tanzania.json`

Build this file ONLY from `docs/briefs/inputs/nungwi_candidates.json`.
The section 6 rules of the Zanzibar brief apply (all candidates, exact
coordinates, `name` = candidate `name`, `name_local_ref` = `wikidata`
if present else `osm_ref` with matching `name_local_source`, no
`name_local`, `category` = `category_suggestion`, `micro_location` =
candidate `micro_location`, no dishes, no wheelchair notes, no prices,
`is_sponsored` false, `bid_weight` 0.0, ASCII-only JSON). In addition:

- Use all 34 candidates. Do not add, drop or move a venue.
- `opening_hours`: same rule as before. Convert ONLY a value that is
  exactly one `Mo-Su HH:MM-HH:MM` or `Mo-Sa HH:MM-HH:MM` range. In this
  file that is expected to be exactly three venues (Essence Restaurant,
  RestOtalia Swahili Restaurant, The Rocks Spa). Bare ranges without
  days (Fat Fish, Origin Zanzibar) and anything else -> `null`.
- `description`: one or two plain sentences from the descriptive part of
  the candidate `note` only. Drop curation remarks (OSM ids, duplicate
  nodes, "leave opening_hours null", "field-verify"). No quality claims
  ("best", "famous", "hidden gem") anywhere in the catalog.
- **Do NOT copy `quality_signal` or `cuisine_osm` into the catalog.**
  The loader's `test_no_silent_key_drop` fails on unknown venue keys,
  and persisting them needs a schema change that is out of scope. They
  stay in the candidates file, which remains the source of truth for
  field verification.
- Planner estimates (label them as such in `curator_notes`):
  `typical_dwell_minutes` food 45 to 75, bars 60 to 90, culture 45 to
  60, nature 30 to 60, Zanzibar Reef Walking Tour 90, spas 60 to 90.
  **Keep every dwell at or below 120** so nothing is treated as a
  whole-day excursion. `indoor_outdoor`, `has_aircon` (`false` unless
  the note says otherwise), `price_band` (`budget` for venues whose name
  or note marks them as local food, mgahawa, Mama, Kibanda or "Food for
  Locals"; `mid` for the other food and bars; `budget` for culture and
  nature; `mid` for spas), `audience`, `vibe_tags` (conservative; may
  use `local_favourite` ONLY for the two venues whose note says local
  guides mention them: Mama Sele Local Food and Mabungo Cafe and
  Restaurant).

Wrapper:

```json
{
  "geo_region": "nungwi_tanzania",
  "curated_at": "2026-11-13",
  "curator_notes": "...",
  "venues": [ ... ]
}
```

`curator_notes` must state: owner field-test exception, separate from
the Stone Town catalog because the day picker has no clustering; data
derives from OpenStreetMap, (c) OpenStreetMap contributors, ODbL 1.0,
owner-only, SPEC-21 review required before wider use; the closed
`micro_location` vocabulary below; coordinates copied unchanged; which
fields are planner estimates; that per-venue quality signals are kept in
`docs/briefs/inputs/nungwi_candidates.json`, not in this file.

Closed `micro_location` vocabulary (use only these):

- `nungwi_north_tip`
- `nungwi_village`
- `nungwi_beachfront`
- `kendwa_south`

Expected coverage (must hold in your catalog):

| Bucket | Venues |
|---|---|
| culture | 4 |
| food (restaurant, cafe, bar) | 24 |
| rest (massage_spa) | 2 |
| nature | 4 |
| total | 34 |

Note for your judgement, not a defect: none of these venues falls in the
day picker's museum or market bucket, so Nungwi days lean on food,
viewpoints and the two spas. That is expected for a beach village. Do
not recategorise anything to change it.

Gate:

```
python3 scripts/load_venues.py data/nungwi_tanzania.json --dry-run
```

must exit 0 with zero validation errors. Every venue must fall inside
the Nungwi box.

## 7. Flutter mirrors

Add `nungwi_tanzania` next to every `zanzibar_tanzania` entry:

- `RegionDefaults`: `(lat: -5.72720, lng: 39.29920)`
- `destination_tz`: `3` (EAT)
- display-name maps in `create_trip_screen.dart`, `date_scope.dart`,
  `add_booking_sheet.dart`: `'nungwi_tanzania': 'Nungwi (Zanzibar)'`
- `booking_parser.dart` `_inferGeoRegion`: add
  `nungwi` -> `nungwi_tanzania` and `kendwa` -> `nungwi_tanzania`
  **above** the existing `stone town` and `zanzibar` checks, so a hotel
  address like "Nungwi, Zanzibar, Tanzania" maps to Nungwi. Do not
  reorder the Laos or Dubai checks.

Dart tests:

- `spec37_destination_tz_test.dart`: Nungwi offset is 3 hours.
- `spec34_location_test.dart`: Nungwi coords present and not Dubai.
- `booking_test.dart`: two new tests using `extractBookingFromText`:
  1. a short hotel confirmation whose location line reads
     `Nungwi, Zanzibar, Tanzania` -> `geoRegion` equals
     `nungwi_tanzania`;
  2. a short confirmation whose location line reads
     `Stone Town, Zanzibar, Tanzania` -> `geoRegion` equals
     `zanzibar_tanzania`.
  Model them on the existing Vang Vieng test; assert only `geoRegion`
  (and `bookingType` if the text makes it unambiguous). Do not change
  existing tests.

## 8. Named tests (Python)

New file `tests/test_nungwi_trip_create.py`, mirroring the Zanzibar
file's helpers and style:

1. `test_nungwi_region_registered_and_require_region`
2. `test_nungwi_bbox_accepts_nungwi_and_rejects_stone_town_laos_and_dubai_points`
   (Nungwi default point and a Kendwa candidate inside; Stone Town
   `(-6.16590, 39.19170)`, the Laos point and the Dubai point outside)
3. `test_nungwi_catalog_dry_run_and_select_day_venues`
4. `test_trips_advertise_nungwi_after_zanzibar_when_seeded`
   (`nungwi_tanzania` present and its index is greater than
   `zanzibar_tanzania`'s)
5. `test_create_nungwi_uses_catalog_only`
   Create with `geo_region: "nungwi_tanzania"` and
   `start_date: "2026-12-28T09:00:00"`. Assert 4..6 nodes, every name in
   the Nungwi catalog, none in the Stone Town catalog, none in the Laos
   catalogs, none in `DUBAI_FIXTURE_NAMES`, every node inside the Nungwi
   box with `geo_region == "nungwi_tanzania"` and a `venue_id`, and the
   fetched trip's context location equals the region defaults.
6. `test_create_zanzibar_contains_no_nungwi_venue`
   Same create for `zanzibar_tanzania`; assert no node name is in the
   Nungwi catalog.
7. `test_empty_nungwi_catalog_is_not_advertised`
   (Zanzibar empty-catalog pattern; create returns 422
   `unsupported_region`)
8. `test_nungwi_catalog_matches_candidates_file`
   Same field-by-field check as the Zanzibar test 8, for 34 venues, plus:
   no venue carries `quality_signal` or `cuisine_osm`; every
   `typical_dwell_minutes` is at most 120.
9. `test_nungwi_and_zanzibar_catalogs_are_disjoint`
   No shared venue names and no shared `name_local_ref` values.
10. `test_seed_language_map_includes_nungwi`
    `CATALOG_LANGUAGES["nungwi_tanzania"] == "sw"` and equals the loader's
    `REGION_LANGUAGES` entry.

All existing tests must keep passing, including every test in
`tests/test_zanzibar_trip_create.py` and `tests/test_laos_trip_create.py`.

Do not hard-code pytest suite totals (R16).

## 9. R17 sabotage

Exact temporary change: make `get_bounding_box("nungwi_tanzania")` return
the Zanzibar (Unguja) box instead of the Nungwi box. A throwaway pytest
plugin in `/tmp` wrapping `get_bounding_box` is the preferred method (no
repo file changes); an in-place edit is acceptable if restored.

Expected: at minimum
`test_nungwi_bbox_accepts_nungwi_and_rejects_stone_town_laos_and_dubai_points`
fails (Stone Town would be accepted). Report every test that failed.
Restore, rerun the Nungwi and Zanzibar test files green, and confirm the
repo file hashes are unchanged. No sabotage artifact in the commit.

## 10. Stop rules

Stop and report if:

- PR #203 is not on main (section 2);
- you feel you need the network, a venue not in the candidates file, or
  to change a candidate coordinate;
- a candidate fails the dry-run or the Nungwi box (report the venue and
  the error; do not edit the candidates file);
- making the loader accept the catalog would require touching
  `INTENTIONALLY_NOT_PERSISTED`, `VENUES_RAG_WRITE_COLUMNS` or a
  migration;
- an existing Zanzibar, Laos or Dubai test fails for any reason other
  than the narrow case allowed in section 4;
- you are about to edit docs, the Stone Town catalog, or start Gap 4.

Never invent hours, dishes or quality claims. Never force-push. Never
"fix" unrelated failures (`test_sparse_create_with_limited_hours_succeeds`,
`test_today_tonight_includes_venue_name`).

## 11. Out of scope (remainders)

- Geographic day clustering, which would let one region span the island
- Persisting `quality_signal` / field-verification state per venue (needs
  a schema and SPEC work; it is the core of the data moat, so it gets its
  own spec, not a side edit here)
- Dishes, verified hours, Swahili names (owner field verification first)
- Matemwe, Paje, Jambiani, Jozani and other coasts
- SPEC-13 / SPEC-20, ODbL bulk ingest and SPEC-21 review
- Hosted `load_venues.py` apply (owner/ops after merge)

## 12. Why care matters here

Not a task, context only: the owner will use this pack on the trip. A
wrong coordinate or invented fact is worse than a missing venue. When in
doubt, leave the field null and say so in the report.

## 13. Gates

Use `ruff==0.16.3`. From repo root:

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
python3 scripts/load_venues.py data/nungwi_tanzania.json --dry-run
python3 scripts/load_venues.py data/zanzibar_tanzania.json --dry-run
git diff --check
```

Flutter: this compute has no Dart or Flutter SDK. Do NOT try to install
one. Mirror the existing `zanzibar_tanzania` Dart lines exactly. In your
report write `dart analyze: not run (no SDK on compute)` and
`flutter test: not run (no SDK on compute)`. The PR's CI `flutter` job
and the owner's local run are the gate before merge. Do not claim Dart
passed.

ASCII only on every touched file.

## 14. Delivery

1. One commit on `feat/nungwi-field-test-pack` with message:
   `Nungwi field-test pack: register nungwi_tanzania catalog and mirrors`.
2. Push and verify the SHA with `git ls-remote`.
3. Do not merge, deploy, or open other branches. No `gh` on this
   compute; the reviewer opens the PR.

## 15. Report (exactly these fields, in this order)

1. Base `origin/main` SHA, and confirmation PR #203 content was present.
2. Branch and pushed SHA (from the remote).
3. pytest last line plus every failing test name.
4. ruff check / format, both dry-runs (errors and warning count), diff
   check. Dart: `not run (no SDK on compute)`.
5. Files touched (must be a subset of section 4). If
   `tests/test_zanzibar_trip_create.py` changed, the exact diff and why.
6. Venue count by bucket and total; the three venues with structured
   hours.
7. Create proof for Nungwi (node names, all in catalog, none Stone Town /
   Laos / Dubai, bbox) and for Zanzibar (no Nungwi names).
8. `supported_regions` order when seeded.
9. R17: tests that failed under sabotage, restore confirmation, hashes.
10. Judgement calls: descriptions, estimates, anything unsure, and the
    Dart lines added.

Do not edit this brief, PROJECT_STATUS, or HANDOFF.
