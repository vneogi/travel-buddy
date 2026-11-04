# Genie brief: SPEC-43 Gap 8 -- trip, date, and source version in the cache key

Landed on `main` as `606626e` (PR #142). Do not re-implement this slice.
Gap 8 active purge landed as `8fab43b` (PR #145). Remainder:
unused Supabase cache path. Do not start hosted 0026, Flutter,
deploy, or an APK without a new brief.

## Goal

Identity-scoped HMAC entries with restricted-response refusal still
hit across trips, calendar days, itinerary versions, and catalog
bumps. Same person, same venue name, yesterday's LIGHT answer can
come back today. A swap that bumped `trip.version` can still serve
the pre-swap prose.

Hits already use cosine plus identity, region, and venue. This
slice adds exact-match `trip_id`, region-local `local_date`, and
`source_version`. Matching is otherwise unchanged.

This is SPEC-43 Gap 8 trip/date/source-version on the live
in-memory cache only.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 8)
- `docs/ENGINEERING_RULES.md` (R4, R5, R14, R17)
- `services/cache_service.py` (`CacheEntry`, `check_cache`,
  `store_response`)
- `agents/state_machine.py` (`_node_check_cache`,
  `_store_light_response`)
- `services/booking_constraints.py` (`_local_date_of`)
- `services/ask_service.py` (`_CATALOG_VERSION`)
- `models/schemas.py` (`TripState.trip_id`, `TripState.version`)
- `tests/test_spec43_g8_cache.py`
- `tests/test_spec43_g8_hmac.py`
- `tests/test_spec43_g8_canaries.py`

Those three test files must stay green. Do not edit them.

Base branch: latest `main` (`895045a`), including Gap 8 canaries
(PR #140).

Create and push:

`feat/spec43-g8-context`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Gap 8 acceptance: a change in trip, date, source version, or
relevant venue facts causes a miss. Venue is already an exact
field. Trip, date, and source version are not.

Do not add an expiry sweeper this slice. Read-time `is_expired`
skip stays. Do not hash the question into these fields; HMAC of
the query is already stored separately.

## Current production seams to reuse

- Keep identity / region / venue, HMAC of the query, cosine
  threshold, and restricted-response refusal. Empty/`anonymous`
  still stores nothing and never hits.
- Keyword-only `trip_id`, `local_date`, `source_version` on both
  `check_cache` and `store_response`. Default each to `""` so
  existing HMAC / identity / canary tests that omit them still
  pass without edits. Hits require exact equality on all three
  (empty hits empty).
- `local_date` is ISO `YYYY-MM-DD`. Compute it with
  `_local_date_of(now_utc, geo_region)` already imported in the
  state machine. Do not invent a second timezone table.
- `source_version` is `f"{trip.version}:{_CATALOG_VERSION}"`.
  Import `_CATALOG_VERSION` from `services.ask_service`. Do not
  copy the string. Do not bump the catalog constant in this PR.
- Extract `_cache_scope(state) -> dict` (name flexible) used by
  both `_node_check_cache` and `_store_light_response`, so tests
  exercise the production store and check paths. Include
  `trip_id`, `local_date`, `source_version`, `geo_region`,
  `venue_name`. Keep passing `restricted_needles` on store.
- R4: do not add a second cache. Do not call supabase cache.
  Do not change `cached_responses` schema.

No CREATE TABLE. No Flutter. No live Postgres. Do not apply 0026.

## Scope

### 1. Exact-match trip, date, source version

`CacheEntry` stores `trip_id`, `local_date`, `source_version`
(strings). `check_cache` continues past an entry when any of
those three differs from the request. Cosine still runs only on
entries that match identity, region, venue, and these three.

Do not put trip/date/version into the HMAC. Do not embed them.

### 2. Named tests

Add `tests/test_spec43_g8_context.py`.

No widgets. No live Postgres. Use a private
`SemanticCacheService(hmac_key=b"g8-context-test-key")`.

Named tests that must exist with these exact names:

`test_cache_misses_when_trip_id_changes`

Identity `user-g8-context`, region `luang_prabang_laos`, venue
`Wat Xieng Thong`, query `What time is the boat?`, local_date
`2026-10-06`, source_version `1:test-cat`. Store ordinary prose
for `trip-g8-a`. `check_cache` with `trip-g8-b` (same everything
else) is None. Same trip id still hits.

`test_cache_misses_when_local_date_or_source_version_changes`

Same private service and trip id `trip-g8-a`. Store once.
`check_cache` with local_date `2026-10-07` is None.
`check_cache` with source_version `2:test-cat` is None.
`check_cache` with source_version `1:other-cat` is None.
Original triple still hits.

Also add (any name):

- identity isolation still holds
- unusable identity still stores nothing
- restricted-response refusal still holds (confirmation needle or
  `sk-` pattern is not stored)
- `_cache_scope` (or the production check/store wrappers) passes
  `trip.trip_id`, `_local_date_of(now_utc, geo)`, and
  `f"{trip.version}:{_CATALOG_VERSION}"`. Put two trips or two
  `now_utc` values through `_node_check_cache` / 
  `_store_light_response` and show a miss.
- existing identity, HMAC, and canary named tests stay green
  (do not change those files)

Do not assert on comments. Do not freeze wall-clock "today"
against ICT midnight; pass explicit `now_utc` / `local_date`.

### 3. R17 sabotage

Exact edit: in `check_cache`, skip the trip_id / local_date /
source_version equality (treat them as always matching).

`test_cache_misses_when_trip_id_changes` must fail (trip B hits).
Restore before the PR. Do not sabotage by deleting the test.
Do not sabotage identity isolation, HMAC, or restricted refusal.

## Out of scope

- Active expiry sweeper (`clear_expired` already exists;
  read-time skip stays)
- `supabase_service` cache path / `cached_responses`
- Admin IAM, Armor, Play Integrity
- `derived_feature`, hosted 0026
- Flutter, deploy, APK

## Gates

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

If `backend/.venv` exists, use that interpreter. No Flutter.

Do not "fix" `test_today_tonight_includes_venue_name`.

## Report

SHA, branch, pytest last line, files touched. Named tests in the
report must include
`test_cache_misses_when_trip_id_changes` and
`test_cache_misses_when_local_date_or_source_version_changes`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
