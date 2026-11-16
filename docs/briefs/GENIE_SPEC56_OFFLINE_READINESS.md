# Genie brief: SPEC-56 slice 1, honest offline status on the itinerary

Read this whole file before touching anything. It is the complete job.
If something here is unclear, stop and ask; do not guess and do not
widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA.

Owning spec: `docs/specs/SPEC-56-offline-readiness-indicator.md`.
Parent: SPEC-04 (offline vault), using SPEC-02 cache tables. This slice
is Flutter-only. No backend, no new endpoint, no SQLite schema change,
no migration, no Cloud Run deploy.

## 0. Context

Zanzibar and Nungwi connectivity will be patchy. The app already saves
the itinerary and per-stop driver card data on the phone, but the
traveller cannot see what is saved or how old it is.

Verified on `main` (re-verify in preflight):

1. `ItineraryController.load()` in
   `mobile/lib/features/itinerary/itinerary_notifier.dart`: on success it
   calls `db.cacheTrip(...)` (fire-and-forget) and `_preCachePlaces`
   (one `cachePlace` per node, ref `node.venueId ?? node.venueName`). On
   failure it reads `db.getCachedTrip(...)` and, if found, sets
   `banner: 'Offline: showing saved itinerary'`.
2. `cache_trip` and `cache_place` in
   `mobile/lib/offline/offline_database.dart` both have `identity_scope`
   and `cached_at` (UTC ISO string). `getCachedTrip` returns only the
   JSON, not `cached_at`. `isUsableIdentityScope` guards scopes.
3. The banner is a dismissible "heads up" row and is cleared by every
   `applyEvent`, so it is not a reliable offline indicator.
4. Home already shows "Last saved <age>" from `cache_trip_list` using a
   private `_cacheAge` helper in `home_screen.dart` (just now / Nm ago /
   Nh ago / Nd ago).
5. The `outbox` table holds analytics signals, not traveller edits, and
   has no identity scope. It is already visible in Profile > Sync
   Status. It is NOT part of this slice.

## 1. Goal

A small status row at the top of the itinerary that tells the truth
about what is saved on this phone for this trip, and a sheet with the
detail. Nothing more.

Status row text (exact):

| Condition | Text |
|---|---|
| showing the saved copy because load failed, cache found | `Offline: showing saved trip (saved <age>)` |
| loaded online, trip row cached | `Saved on this device (<age>)` |
| loaded online, no trip row yet | `Not saved on this device yet` |

`<age>` uses the same wording as Home: `just now`, `5m ago`, `3h ago`,
`2d ago`. If the saved copy is 24 hours old or more, the row uses the
existing `AppColors.warning` token and the sheet shows the stale note below.

Sheet (opened by tapping the row), lines in this order:

- `Itinerary: saved <phone-local date and time>`
  or `Itinerary: not saved on this device yet`.
- `Driver cards: X of Y stops saved` where Y is the number of distinct
  place refs (`venueId ?? venueName`) in the current nodes and X is how
  many of those have a `cache_place` row for this identity. Omit this
  line when Y is 0.
- Stale note, only when 24h or older: `Saved more than a day ago. Open
  this trip with a connection to refresh it.`
- Footnote, always: `Only what is listed here is saved on this phone.
  Maps, search and new suggestions need a connection.`
- A `Check again` button that re-reads the local status. It makes no
  network call.

Never show: `100%`, `ready`, `fully`, `downloaded`, `complete`, an
outbox or signal count, or any claim about maps, emergency contacts or
venues beyond the two lines above.

## 2. Preflight

1. `git fetch origin`. Work from the base SHA in the message that sent
   this brief.
2. Confirm on that SHA everything in section 0 items 1 to 3 (method
   names, columns, banner text, `_preCachePlaces` ref rule). If any
   differs, stop and report.
3. Confirm `mobile/lib/features/itinerary/offline_readiness.dart`,
   `mobile/test/spec56_offline_readiness_test.dart` and
   `origin/feat/spec56-offline-readiness` do not exist.
4. Branch: `feat/spec56-offline-readiness`.

## 3. Read before editing

- `docs/specs/SPEC-56-offline-readiness-indicator.md`,
  `docs/specs/SPEC-04-offline-vault.md`
- `docs/ENGINEERING_RULES.md` R14, R16, R17
- `mobile/lib/offline/offline_database.dart` (cache section and
  `isUsableIdentityScope`)
- `mobile/lib/features/itinerary/itinerary_notifier.dart` (`ItineraryState`,
  `load`, `_preCachePlaces`)
- `mobile/lib/features/itinerary/itinerary_screen.dart` (`build`, the
  body `Column`, `_HeadsUpBanner`, the existing lifecycle observer in
  `_ItineraryAlertsSectionState` as a pattern)
- `mobile/lib/features/home/home_screen.dart` (`_cacheAge`, read only)
- `mobile/test/spec43_g12_cache_test.dart` and
  `mobile/test/spec45_bottom_inset_test.dart` (real in-memory DB and
  itinerary harness patterns)

## 4. Files you may touch

- `mobile/lib/offline/offline_database.dart`: add ONE read-only method,
  `getTripCacheStatus` (section 5). No schema, version or write change.
- `mobile/lib/features/itinerary/itinerary_notifier.dart`: add a
  `showingSaved` bool to `ItineraryState` (default false, in the
  constructor and `copyWith`), and in the offline fallback of `load()`
  set `showingSaved: true` instead of the
  `banner: 'Offline: showing saved itinerary'` line. Nothing else.
- `mobile/lib/features/itinerary/offline_readiness.dart` (new): the
  status model, provider, age helper, row widget and sheet.
- `mobile/lib/features/itinerary/itinerary_screen.dart`: insert the row
  as the first child of the body `Column` (above the progress bar).
  Nothing else in this file.
- `mobile/test/spec56_offline_readiness_test.dart` (new).

Nothing else. No Home change (copy the age wording, do not import the
private helper), no backend, no docs, no router, no `pubspec`, no theme
files, no existing test file.

## 5. Implementation

`OfflineDatabase.getTripCacheStatus`:

```
Future<({DateTime cachedAt, int placesCached})?> getTripCacheStatus(
  String tripId, {
  required String identityScope,
  required List<String> placeRefs,
})
```

- Returns null when `!isUsableIdentityScope(identityScope)` (no query)
  or when there is no `cache_trip` row for (scope, trip).
- Reads only `cached_at` from `cache_trip` (never `state_json`).
- Counts `cache_place` rows WHERE `identity_scope = ?` AND `place_ref IN
  (...)` over the de-duplicated refs; 0 when the list is empty; chunk
  the IN list at 500.

`offline_readiness.dart`:

- `String savedAgeLabel(DateTime cachedAtUtc, {DateTime? nowUtc})` with
  Home's wording. `nowUtc` is for tests.
- `tripCacheStatusProvider`: `FutureProvider.autoDispose.family` keyed by
  trip id. It watches the itinerary controller's nodes (use `select` so
  unrelated state changes do not re-query), returns null while loading,
  otherwise calls `getTripCacheStatus` with the identity scope from
  `identityCacheScopeProvider` and the distinct refs.
- `OfflineStatusRow` (`ConsumerStatefulWidget`, key
  `Key('offline_status_row')`): reads `showingSaved` from the itinerary
  state and the provider; renders the section 1 text; tap opens the
  sheet (key `Key('offline_status_sheet')`). While the provider is
  loading or in error, render nothing (`SizedBox.shrink()`), never an
  error message. Registers a `WidgetsBindingObserver` and invalidates
  the provider on `AppLifecycleState.resumed`. Min 44dp tap height,
  text wraps (no ellipsis that hides the age), button semantics.
- `Check again` invalidates the provider only.

Timing note: `cacheTrip` is fire-and-forget. The provider re-reads when
nodes change and on resume, and `Check again` exists, so a brief "Not
saved on this device yet" right after a first online load is acceptable.
Do not make `load()` await `cacheTrip`, and do not change `cacheTrip`'s
signature.

## 6. Tests

`mobile/test/spec56_offline_readiness_test.dart`, exact names. Real
in-memory `OfflineDatabase(testPath:)` with sqflite FFI as the existing
cache tests do. Seed rows with a known `cached_at` by inserting directly
or by calling the cache methods and then updating `cached_at`.

DB and helper:

1. `status is null when the trip is not cached`
2. `status reads cached_at and counts only this identity's places`
   (rows for another scope with the same refs are not counted)
3. `unusable identity scope returns null`
4. `empty refs count zero and duplicate refs count once`
5. `savedAgeLabel matches Home wording` (just now, 5m ago, 3h ago, 2d ago
   with an injected now)

Widget (real `ItineraryController` with a mocked `TripRepository`;
override `tripRepoProvider`, `offlineDatabaseProvider`,
`identityCacheScopeProvider`, and stub `userStatusProvider` if the
screen pulls it):

6. `online load shows Saved on this device`: after load and flush, the
   row reads `Saved on this device (just now)`.
7. `failed load with a saved copy shows Offline showing saved trip`:
   `getTrip` throws `NetworkException`; DB pre-seeded 2h old; row reads
   `Offline: showing saved trip (saved 2h ago)`; the text
   `Offline: showing saved itinerary` does not appear anywhere.
8. `no saved copy shows Not saved on this device yet` (use a state where
   load succeeded but the trip row is absent, for example by stubbing
   the DB write to be a no-op or deleting the row before reading;
   explain the choice in a comment).
9. `stale saved copy shows the stale note` (cached 2 days ago).
10. `sheet lists itinerary time and driver card counts`: 3 distinct refs,
    2 cached -> `Driver cards: 2 of 3 stops saved`; insert the third,
    tap `Check again` -> `3 of 3`.
11. `no overclaiming words in row or sheet`: across states 6, 7, 8, 9,
    none of `100%`, `ready`, `fully`, `downloaded`, `complete`,
    `outbox`, `signal` appears (case-insensitive).
12. `app resume re-reads status`: insert a place row, send
    `AppLifecycleState.resumed`, count updates without tapping anything.
13. `itinerary screen shows the status row`: pump the real itinerary
    screen with the existing harness; `offline_status_row` is present
    above the stop list.
14. `row fits at 360dp and 2.0 text scale`: no overflow, age still
    visible.

## 7. R17

Run each, confirm the named test fails, then restore and confirm green:

A. Keep the old banner line and drop `showingSaved: true`: test 7 fails.
B. Remove the `identity_scope = ?` filter from the place count: test 2
   fails.
C. Remove the resume invalidation: test 12 fails.
D. Remove the stale note: test 9 fails.

## 8. Stop rules

Stop and ask if:

- you need any file outside section 4, or a schema/version change;
- an existing test needs an assertion changed, or fails because of the
  new row (report the test and failure; do not edit it);
- you want to show outbox counts, add a download or "make available
  offline" action, or add any wording beyond section 1;
- you want `load()` to await the cache write or to change `cacheTrip`.

## 9. Gates

```
cd mobile && flutter analyze && flutter test
git diff --check
```

`flutter analyze` 0 issues (infos as today), `flutter test` all passed.
ASCII only in every touched file. Do not add `SPEC-NN` references except
to numbers with a file under `docs/specs/`.

If you have no Flutter SDK, say so and rely on CI (the planning agent
runs it on the PR). Do not install Flutter without the owner's approval.
Teardown pattern that works in this repo: close harness listeners while
the widget is still mounted, then dispose the container (see
`spec46_what_now_test.dart`). Reverse/lazy lists may not build offscreen
rows; use a tall test surface if you assert on them.

## 10. Delivery

One commit on `feat/spec56-offline-readiness`:
`feat: SPEC-56 honest offline status on the itinerary`.
Push and verify the remote SHA. Do not merge. No `gh`. No APK build or
Cloud Run deploy.

## 11. Report

1. Base SHA.
2. Branch and remote SHA.
3. `flutter analyze` and `flutter test` last lines (or "no Flutter,
   CI only").
4. `git diff --check` result.
5. Files touched, with +/- counts.
6. R17 A to D results (or "not observed, CI only").
7. Confirmation that `cacheTrip`, `getCachedTrip`, the schema, Home,
   routing and the backend are unchanged.
8. Anything you were unsure about.

## 12. Owner device check (after merge and APK rebuild)

1. Online, open the Stone Town trip. The top row reads `Saved on this
   device (just now)` (tap `Check again` once if it first says not saved
   yet). Tap it: itinerary time and `Driver cards: X of Y stops saved`.
2. Airplane mode, close the app fully, reopen, open the same trip. The
   row reads `Offline: showing saved trip (saved <age>)`. The old
   dismissible "Offline: showing saved itinerary" banner is gone.
3. Still offline, open a driver card from a stop. It renders.
4. Largest system font: the row wraps and the age stays visible.
