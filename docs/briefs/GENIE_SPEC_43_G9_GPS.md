# Genie brief: SPEC-43 Gap 9 -- GPS plausibility on ingest

This is the open Gap 9 GPS first slice. Implement it. Do not start
`derived_feature`, hosted 0026, Flutter, deploy, or an APK.

## Goal

A client that sends coordinates on a trip-linked presence signal
must not attach a visit/skip to a place from another continent.
Today closed `value_json` schemas reject `lat`/`lng`, so GPS never
arrives, and ingest never checks distance to the itinerary node.

This is SPEC-43 Gap 9 GPS plausibility only. Ownership, schemas,
ranking isolation, and trip-place are already on main. It is not
`derived_feature`, sample-size columns, contributor quality, Flutter
emit, Gap 11 remainders, deploy, or an APK.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 9)
- `docs/ENGINEERING_RULES.md` (R4, R14, R17)
- `routers/signal_router.py` (ingest loop; trip-place then consent)
- `models/signal_types.py` (`VALUE_JSON_ALLOWED_KEYS`)
- `services/trip_ownership.py` (`is_place_on_trip`, `get_trip`)
- `models/schemas.py` (`TripNode.lat`, `TripNode.lng`)
- `tests/test_spec43_g9_trip_place.py` (helpers, in-memory `_trips`)

Base branch: latest `main` (`658ae32`), including Gap 11
`2077d8d` (PR #119).

Create and push:

`feat/spec43-g9-gps`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Trip-place membership stops `dubai-aquarium` on a Laos trip. It
does not stop `visited_confirmed` for a real Laos node with GPS in
Dubai. That is still a poisoning channel into any later aggregator
keyed by `(trip_id, place_ref)`.

Do not build a `derived_feature` table this slice. GPS reject on
ingest is the first bar.

## Current production seams to reuse

- After trip-place, before consent / `record_signal` / derive.
  Rejected items write and derive nothing.
- Duplicate `signal_id` that is already stored skips this check
  (same as trip-place: `get_signal` not None -> existing path).
- Resolve the trip with existing `get_trip`. Match `place_ref` to a
  node the same way trip-place does (`venue_id` or `venue_name`,
  case-insensitive strip). Use that node's `lat`/`lng`.
- GPS is optional. Missing `lat`/`lng` is not a reject. Do not
  require the Flutter client to send coordinates.
- No trip_id: range-check only (no node to compare). Session and
  free-floating loves without coords stay as today.
- Exempt types (no GPS keys, no distance check): `session_start`,
  `booking_added`, `reroute_accepted`, `reroute_rejected`,
  `prompt_dismissed`, `driver_card_shown`, `name_confirmed`.
- Types that may carry GPS this slice:
  `visited_confirmed`, `node_skipped`, `user_loved`, `dish_loved`,
  `dish_ordered`.
- Distance check only for `visited_confirmed` and `node_skipped`
  when `trip_id` is set and the matched node has both `lat` and
  `lng`. If the node has no coords, skip distance (range still
  applies). `user_loved` / dish types: range only (home-screen
  love is not a presence claim).

No CREATE TABLE. No new pip dependency. No Flutter. No live
Postgres. Do not apply 0026. Do not change `_interest_score`.
Do not create `derived_feature`.

R4: a helper that reads trips uses `get_trip` (already on both
backends). Haversine is math-only; no DB method required.

## Scope

### 1. Allowlist and constants

In `models/signal_types.py` add `lat`, `lng`, `accuracy_m` to
`VALUE_JSON_ALLOWED_KEYS` for the five types above. Do not add
them to exempt types.

Put named constants in one Python module used by ingest
(e.g. `services/gps_plausibility.py`):

- `MAX_GPS_OFFSET_M = 50000`  (50 km)
- `MAX_ACCURACY_M = 10000`

Range:

- `lat` and `lng` must both be present, or both absent. One
  without the other is a reject.
- Values must be finite numbers (int or float, not bool).
- `lat` in `[-90, 90]`, `lng` in `[-180, 180]`.
- `accuracy_m` if present: finite number, `0 < accuracy_m <= 10000`.

Distance: haversine meters from (lat, lng) to the matched node's
(lat, lng). If greater than `MAX_GPS_OFFSET_M`, reject.

Reject reason must contain `gps`. Examples:

- `gps: lat/lng out of range`
- `gps: coordinates too far from trip place`

Do not log the coordinates.

### 2. Named tests

Add `tests/test_spec43_g9_gps.py`.

In-memory `db_service` only. No widgets. No live Postgres.
Reuse the trip-create / `_signal` / `_post` pattern from
`tests/test_spec43_g9_trip_place.py`.

Named tests that must exist with these exact names:

`test_impossible_gps_coords_are_rejected`

POST `visited_confirmed` on a real trip node with
`value_json: {"lat": 999, "lng": 0}`. HTTP 200, that item in
`rejected`, reason contains `gps`, `get_signal` is None, no
`arrival_delta` row.

`test_gps_too_far_from_trip_node_is_rejected`

Ensure the matched node has coords (patch `node.lat`/`node.lng`
if the created trip node is missing them). POST `visited_confirmed`
with valid-range coords about 1000 km away (e.g. node at 17.97,
102.6 and GPS at 25.2, 55.27). Item rejected, reason contains
`gps`, nothing stored, nothing derived.

Also add (any name):

- Same node, GPS within 1 km, accepts
- No `lat`/`lng` still accepts (GPS optional)
- Only `lat` (no `lng`) rejects with `gps`
- `user_loved` with Dubai coords on a Laos node still accepts
  (range ok; no distance check on loves)
- Stored `signal_id` retry with bad GPS is a duplicate, not a
  gps reject
- `session_start` still rejects unknown key `lat` (schema, not gps)

Do not assert on comments.

### 3. R17 sabotage

Exact edit: skip the range reject (treat any finite lat/lng as
in range). Keep the distance check.

`test_impossible_gps_coords_are_rejected` must fail. Restore
before the PR. Do not sabotage by deleting the test. Do not
sabotage the distance check.

## Out of scope

- `derived_feature` table, method_version, sample_size
- Wiring GPS or loves into `pack_day` / ranking
- Time-plausibility beyond existing `captured_at` skew
- Contributor quality / anomaly models
- Flutter emit of lat/lng
- Gap 11 remainders, Gap 7 Flutter, Gap 8 HMAC, Gap 10 IAM
- Hosted 0026, deploy, APK, `pm clear`

## Gates

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

If `backend/.venv` exists, use that interpreter. No Flutter.

## Report

SHA, branch, pytest last line, files touched. Named tests in the
report must include `test_impossible_gps_coords_are_rejected` and
`test_gps_too_far_from_trip_node_is_rejected`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.