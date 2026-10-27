# Genie brief: SPEC-43 Gap 12 -- identity-scoped trip and place cache

Landed on `main` as `290f821` (PR #85). Do not re-implement this slice.
Chat URLs `14ce56d`. ATS `be89128`. Deep-link `f486079`. Gap 9
schemas `fb72545`. Next:
`docs/briefs/GENIE_SPEC_43_G5_SQLCIPHER.md`.

## Goal

A second identity on the same install must not read the first identity's
offline itinerary or driver-card cache.

`cache_trip_list` is already keyed by `identityCacheScopeProvider`
(`account:<sub>` or `anonymous:<deviceId>`). `cache_trip` is keyed only
by `trip_id`. `cache_place` is keyed only by `place_ref`. Offline
itinerary fallback and the driver card therefore serve whoever last
wrote that trip or place, including after a failed wipe or a guessed
trip id.

This is SPEC-43 Gap 12 cache keys only. HTTPS fail-closed is already
on main (`6f1dab8`, PR #82). Do not re-implement HTTPS. This is not
chat query strings, deep links, Android network-security XML, iOS ATS,
Gap 5 SQLCipher, Gap 6 sign-out (already landed), Gap 9 schema, deploy,
or an APK.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 12)
- `mobile/lib/offline/offline_database.dart` (`cacheTrip`, `getCachedTrip`,
  `cachePlace`, `getCachedPlace`, `_dbVersion` is 8)
- `mobile/lib/core/providers.dart` (`identityCacheScopeProvider`)
- `mobile/lib/features/itinerary/itinerary_notifier.dart`
- `mobile/lib/features/driver_card/driver_card_screen.dart`
- `mobile/lib/features/booking/add_booking_sheet.dart`
- `mobile/lib/main.dart` (`tripDayFromCachedTrip`)
- `mobile/lib/features/home/home_controller.dart` (already scoped; do
  not rework `cache_trip_list`)
- `docs/ENGINEERING_RULES.md` (R1, R14, R17)
- `docs/WAYS_OF_WORKING.md`

Base branch: latest `main`, including Gap 12 HTTPS `6f1dab8` (PR #82)
and docs `e5b15e2` (PR #83).

Create and push:

`feat/spec43-g12-cache`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Gap 6 deletes cache tables on sign-out. That is not enough. Unscoped
primary keys still mean: identity B who opens `/trip/<A's id>` offline
gets A's JSON; the driver card for a shared `place_ref` shows A's
cached hours and names. SPEC-43 Gap 12 acceptance: switching identity
cannot read a stale trip or place row.

## Current production seams to reuse

- `identityCacheScopeProvider` -- the only identity string for caches.
  Do not invent a second namespace.
- `cache_trip_list.cache_key` already uses that provider. Leave it.
- `alert_cache`, `loved_places`, `node_outcome` already use
  `identity_scope` plus a composite primary key. Match that shape.
- Gap 6 wipe still deletes whole tables. Keep that. Scoped keys are
  the second line of defense, not a replacement for wipe.

Do not encrypt SQLite (Gap 5). Do not change HTTPS. Do not put chat
text into a new table. Do not call the service-role key from the app.

## Scope

### 1. Schema

Bump `OfflineDatabase._dbVersion` from 8 to 9.

`cache_trip` columns:

- `identity_scope TEXT NOT NULL`
- `trip_id TEXT NOT NULL`
- `state_json TEXT NOT NULL`
- `cached_at TEXT NOT NULL`
- `PRIMARY KEY (identity_scope, trip_id)`

`cache_place` columns:

- `identity_scope TEXT NOT NULL`
- `place_ref TEXT NOT NULL`
- `data_json TEXT NOT NULL`
- `cached_at TEXT NOT NULL`
- `PRIMARY KEY (identity_scope, place_ref)`

On create (fresh db) use the new DDL.

On upgrade from version < 9: rebuild both tables to the new DDL.
**Do not copy old unscoped rows.** Those rows have no owner. Dropping
them is the fail-closed migration. Update
`mobile/test/offline_node_outcome_test.dart` (it currently opens a v5
file, upgrades, and expects `cache_trip` length 1). After this slice,
unscoped `cache_trip` / `cache_place` rows from v5 must be gone; other
tables in that test still migrate.

### 2. API

Change `cacheTrip`, `getCachedTrip`, `cachePlace`, and `getCachedPlace`
so every call takes `identityScope` (named argument preferred).

Rules:

- Write: if `identityScope` is empty, or is `anonymous:` / `account:`
  with nothing after the colon, throw (do not insert an unscoped row).
- Read: the same invalid scope returns null (do not scan all rows).
- Read: `WHERE identity_scope = ? AND trip_id = ?` (same for place).
  Never look up by `trip_id` or `place_ref` alone.
- Never rewrite or ignore a foreign scope. Never fall back to "any
  row with this trip_id".

### 3. Callers

Pass `ref.read(identityCacheScopeProvider)` (or `ref.watch` where the
existing file already watches) at every production write and read:

- `ItineraryController.load` cache write and offline fallback
- `ItineraryController._preCachePlaces`
- `ItineraryController._cacheUpdatedTripNodes`
- `DriverCardScreen` load and save
- `AddBookingSheet` `cachePlace`
- `tripDayFromCachedTrip` in `main.dart` -- add `identityScope`;
  the session-start caller must pass the current scope
- any other production `cacheTrip` / `getCachedTrip` / `cachePlace` /
  `getCachedPlace` call site (`rg` them; do not leave a two-arg call)

Mocks and fakes in tests must compile. Search at least:

- `mobile/test/itinerary_controller_test.dart`
- `mobile/test/session_start_test.dart`
- `mobile/test/offline_sync_test.dart`
- `mobile/test/spec43_g6_signout_test.dart`
- `mobile/test/features/driver_card/driver_card_test.dart`
- widget tests that stub `cacheTrip` / `cachePlace` / `getCachedTrip`

`cacheTripList` / `getCachedTripList` stay as they are.

### 4. Tests

New file: `mobile/test/spec43_g12_cache_test.dart`.

Open SQLite with unique in-memory paths, same harness as Gap 6:

```dart
testPath: 'file:spec43_g12_cache_$_dbCounter?mode=memory&cache=shared'
```

`sqfliteFfiInit(); databaseFactory = databaseFactoryFfi;` in the file
setup. Increment the counter per test. `close` in tearDown. No live
network. No `pumpAndSettle`. No `physicalSize`. No widgets required.

Must include named test:

`test_foreign_identity_cannot_read_cached_trip`

That test:

1. Writes a trip JSON under `account:user-a` for `trip-1`.
2. Reads with `account:user-b` and the same `trip-1`.
3. Expects null.
4. Reads with `account:user-a` and expects the written JSON.

Also cover:

- foreign identity cannot read `cache_place` for the same `place_ref`
- same identity can read what it wrote
- empty / `anonymous:` / `account:` scope is refused on write
- a v8-shaped (unscoped) on-disk db upgraded through OfflineDatabase
  does not yield the old `cache_trip` row to any identity

Do not assert a hardcoded pytest count in any doc.

### 5. R17 sabotage

Do this exact edit. Do not replace a single keyword.

In `getCachedTrip`, find the query that includes `identity_scope` in
the WHERE clause. Change **only** that lookup so it queries by
`trip_id` alone (drop `identity_scope` from `where` and `whereArgs`).
Leave `cachePlace` / writes / schema alone.

Then run:

```bash
flutter test test/spec43_g12_cache_test.dart --name test_foreign_identity_cannot_read_cached_trip
```

**Required:** that exact test fails because user-b now receives
user-a's JSON (or equivalent: a non-null foreign read). A compile
error, a load failure, or a red file for a different test is not
proof.

Restore the original WHERE (or `git checkout --` the file). Re-run
the focused file green.

If Flutter SDK is absent, say so, still push the Dart, and write the
R17 steps in the PR so the owner laptop can run them. Do not invent a
Flutter pass.

R1: after any Dart write, `grep -rn '\\$' mobile/lib` must still show
only the two price strings in `upgrade_screen.dart`. Do not grep for
bare `$` (that matches normal interpolation).

R14: this brief and any living-doc touch stay ASCII.

## Non-goals

- chat text in route URLs
- deep-link ownership
- network_security_config.xml / ATS plist
- lock-screen notification privacy
- Gap 5 SQLCipher / backup exclusion
- Gap 6 sign-out sequence (do not rewrite it)
- remaining Gap 9 trip-place / GPS
- hosted deploy, APK, applying 0026
- production LLM

## Gates

```bash
ruff check .
ruff format --check .
pytest -q -ra --strict-markers
git diff --check
```

Flutter (say so if the SDK is absent):

```bash
flutter analyze --no-fatal-infos
flutter test test/spec43_g12_cache_test.dart
```

Also run the files you had to touch for the new `identityScope`
argument (at least `itinerary_controller_test.dart`,
`session_start_test.dart`, `offline_node_outcome_test.dart`,
`spec43_g6_signout_test.dart` if those call sites changed).
