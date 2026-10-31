# Genie brief: SPEC-43 Gap 9 -- trip-linked place must be on the trip

Landed on `main` as `cafba3c` (PR #103). Do not re-implement this slice.
Next: `docs/briefs/GENIE_SPEC_43_G5_SQLCIPHER_OPEN_FAILED.md`. Remaining Gap 9
(GPS coords, derived_feature sample-size) stays later. Do not start
SQLCipher, Gap 7, Gap 10, Gap 11, deploy, or an APK without a new brief.

## Goal

A `trip_id` on a venue signal is not a write primitive for an
arbitrary `place_ref`. If the client names a trip, `place_ref` must
be a node already on that trip (`venue_id` or `venue_name`).

Today ownership checks the trip belongs to the caller. Rate caps
floods. Neither stops `user_loved` on `dubai-aquarium` attached to a
Laos itinerary that does not contain that place. SPEC-43 Gap 9
location plausibility (catalog, not GPS): trip-linked venue signals
must name a place on that trip.

This is SPEC-43 Gap 9 trip-place only. Ownership (`163a14c`),
schemas (`fb72545`), and ranking isolation (`9b49fd0`) are on main.
It is not GPS, `derived_feature`, Gap 5, deploy, or an APK.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 9)
- `docs/ENGINEERING_RULES.md` (R4, R14, R17)
- `routers/signal_router.py` (ingest loop)
- `services/database_service.py` (`get_trip`, `TripState.nodes`)
- `services/supabase_service.py` (`get_trip`)
- `models/schemas.py` (`TripNode.venue_id`, `venue_name`)
- `tests/test_spec43_g9_signal_ownership.py` (`_place_ref`)
- `tests/test_spec43_g9_signal_schema.py`
- `tests/test_party.py`
- `tests/test_spec43_g9_ranking_isolation.py`

Base branch: latest `main` (`9b49fd0`, PR #101).

Create and push:

`feat/spec43-g9-trip-place`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Owning a trip must not let a client stamp loves, visits, or skips
onto a venue that is not on that itinerary. That is a poisoning
channel into any later aggregator keyed by `(trip_id, place_ref)`.

## Current production seams to reuse

- After ownership (and schema / rate as they already run), before
  `record_signal`. Rejected items write and derive nothing.
- Resolve the trip with existing `get_trip`. Match `place_ref` to
  any node `venue_id` or `venue_name`, case-insensitive string
  equality after strip. Uncatalogued nodes still have `venue_name`.
- No trip_id: no place-on-trip check (session and free-floating
  loves stay as today).
- Exempt types this slice: `session_start`, `booking_added`
  (`place_ref` may be `booking` / `app`). All other client-emittable
  types with a trip_id must match a node.
- Duplicate `signal_id` that is already stored skips this check
  (same as rate: `get_signal` not None -> existing idempotent path).

Do not add CREATE TABLE. If you somehow add one, grant `service_role`
only. Do not create `derived_feature`. Do not change Flutter emit.

R4: if you add a helper, put it on both DB backends. Prefer using
`get_trip` which already exists on both.

## Scope

### 1. Check

Reject reason must contain `place`. Example:
`place: 'dubai-aquarium' is not a node on this trip`.

### 2. Tests

New file `tests/test_spec43_g9_trip_place.py`.

Named test that must exist with this exact name:

`test_trip_linked_signal_for_unknown_place_is_rejected`

Create a trip as the debug user (same as ownership tests). POST
`user_loved` with that `trip_id` and `place_ref` that is not any
node's `venue_id` or `venue_name` (use `not-on-this-trip`). Expect
HTTP 200, that item in `rejected`, reason contains `place`,
`get_signal` is None, no derive rows.

Also:

- `user_loved` with `place_ref` equal to a real node's `venue_id`
  (or `venue_name` if no id) still accepts
- same for `node_skipped` with `reason: too_tired`
- `session_start` with `trip_id` and `place_ref: app` still accepts
- no `trip_id` plus `place_ref: not-on-this-trip` still accepts
- mixed batch: on-trip item accepts, unknown place rejects

Update `test_party.py` / schema tests that send `trip_id` with
`dubai-aquarium` or `test-venue` so they use a real node place_ref
(or drop trip_id if the test is not about parties). Do not keep a
test that proves an off-itinerary place is stored on a trip.

No Flutter. No live Postgres.

### 3. R17 sabotage

Exact edit: skip the place-on-trip reject (comment out or always
return ok) so `not-on-this-trip` is stored.

`test_trip_linked_signal_for_unknown_place_is_rejected` must fail.
Restore before the PR. Do not sabotage by deleting the test.
Do not sabotage schema or rate helpers.

## Out of scope

- GPS / lat-lng plausibility
- `derived_feature`, sample_size columns
- Changing clock-skew 30d / 5min
- Gap 5 SQLCipher, Gap 7, Gap 10, Gap 11
- Hosted 0026, Gap 1 Cloud Run, APK
- Flutter

## Gates

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

If `backend/.venv` exists, use that interpreter. No Flutter.

## Report

SHA, branch, pytest last line, files touched. The named test in the
report must be `test_trip_linked_signal_for_unknown_place_is_rejected`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
