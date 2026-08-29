# Genie Brief -- Durable Hearts and Accurate Sync Status

> Status: READY TO IMPLEMENT.
> Land through a feature branch and PR to `main`; do not push directly to
> `main`. Keep this a small Flutter-only vertical slice.

## Context

`user_loved` emission already works:

`ItineraryScreen.onTapLoved` -> `SignalService.emitUserLoved()` -> SQLite
outbox -> `SyncEngine`.

Do not add a second emission path. The defect is that the filled-heart UI is
held only in `ItineraryState.lovedPlaceRefs`. The provider is `autoDispose`,
and `ItineraryController.load()` also replaces state, so hearts disappear when
the controller is recreated or reloaded.

There is a second defect in `SyncStatusScreen._refresh()`: it calls
`syncOnce()` without awaiting it, then reads counts while sync may still be in
flight.

## Goal

1. A loved place remains filled after controller recreation and app restart.
2. Restoring a filled heart never emits another `user_loved` signal.
3. Heart state is isolated by identity and trip.
4. Sync Status awaits the manual sync attempt before reading counts.
5. Existing retry, backoff, single-flight and 401 halt behavior remains intact.

## Non-goals

- No unlove/toggle semantics.
- No dish hearts.
- No backend or signal-registry changes; `user_loved` is already supported.
- No identity-scoping rewrite of the outbox.
- No queue-cap policy change.
- No UI redesign, provider rewrite or keepAlive workaround.
- Do not infer restored love state from outbox rows. Successfully synced rows
  are deleted, so the outbox is not a durable UI fact store.

## Required implementation

### 1. Add identity-scoped loved-place storage

In `mobile/lib/offline/offline_database.dart`, bump the database version from
3 to 4 and add:

```sql
CREATE TABLE loved_places (
  identity_scope TEXT NOT NULL,
  trip_id TEXT NOT NULL,
  place_ref TEXT NOT NULL,
  loved_at TEXT NOT NULL,
  PRIMARY KEY (identity_scope, trip_id, place_ref)
)
```

Create it both for fresh databases and in the `oldVersion < 4` upgrade path.
Follow the existing `alert_dismissals` identity-scope pattern.

Add production APIs equivalent to:

- `upsertLovedPlace(identityScope, tripId, placeRef)`, using insert-or-ignore.
- `getLovedPlaceRefs(identityScope, tripId) -> Set<String>`.

Use `identityCacheScopeProvider`: `account:<id>` when signed in and
`anonymous:<device-id>` otherwise.

### 2. Persist and restore in the itinerary controller

In `mobile/lib/features/itinerary/itinerary_notifier.dart`:

- Read the identity scope from `identityCacheScopeProvider`.
- Keep `markLoved(placeRef)` optimistic: update state immediately, then persist
  the place ref for the current trip. A cache write failure must not crash the
  itinerary.
- Restore persisted refs during `load()`.
- Preserve or merge loved refs through every success, cache fallback, retry and
  error state construction. Calling `load()` on the same controller must not
  clear an already filled heart.
- Restoration is state hydration only. It must never call `emit`,
  `emitUserLoved` or enqueue a signal.

Keep the existing screen call split:

- User tap: `emitUserLoved` once, then `markLoved`.
- Restore: read SQLite and fill state only.

Do not remove the heart boolean from the activity-card `ValueKey`; it is needed
for a heart-only rebuild.

### 3. Await sync before status counts

In `mobile/lib/features/debug/sync_status_screen.dart`, make the refresh path:

1. set loading,
2. `resetAuthHalted()`,
3. `await syncOnce()`,
4. `await getStatusCounts()`,
5. update state.

Extract this ordering into a small production helper that can be tested without
pumping the whole screen. Keep manual refresh resetting the auth halt. Do not
clear auth halt from timers or connectivity callbacks.

### 4. Close the 401 test gap

Add a test proving:

- first `syncOnce()` receives `UnauthorizedException`,
- the row remains pending and `authHalted` becomes true,
- a second `syncOnce()` does not make another POST,
- after `resetAuthHalted()`, a later manual attempt may run.

Preserve all existing typed-exception behavior. Do not string-match "401".

## Required tests

Use real `OfflineDatabase` storage for persistence assertions and existing
mocktail patterns for API calls.

1. **Loved refs survive controller recreation**
   - Override `identityCacheScopeProvider`.
   - Use one real database instance.
   - Drive the production `markLoved` and `load` paths.
   - Dispose/recreate the controller and confirm the ref is restored.

2. **Restore does not enqueue another signal**
   - Perform one real user action path: emit once and persist once.
   - Record outbox size.
   - Recreate/load the controller.
   - Assert the outbox size is unchanged.

3. **Reload preserves love**
   - Mark loved, call `load()` on the same controller, and confirm it remains.

4. **Identity and trip isolation**
   - A love stored for scope A/trip 1 is invisible to scope B and trip 2.

5. **Refresh waits before counts**
   - Enqueue one event.
   - Delay the mocked successful POST.
   - Await the extracted refresh helper.
   - Assert returned pending/inflight counts reflect completed sync, not the
     pre-sync or in-flight state.

6. **401 blocks a second POST**
   - Use `UnauthorizedException`.
   - Verify the API POST count remains one until `resetAuthHalted()`.

Update existing itinerary-controller mocks for the new database calls. Keep a
provider subscription open in autoDispose tests. Close every SQLite handle with
`addTearDown`.

## Sabotage proofs

Run each temporary break, prove the named test fails, then restore it:

1. Skip loved-ref restore in `load()` -> recreation test fails.
2. Emit `user_loved` during restore -> no-extra-enqueue test fails.
3. Remove `identity_scope` from the read predicate -> isolation test fails.
4. Remove `await` before status counts -> delayed-sync ordering test fails.
5. Remove the `_authHalted` early return -> second-POST test fails.

Do not commit sabotage changes.

## Verification

From `mobile/`:

```text
dart format --output=none --set-exit-if-changed lib test
flutter analyze --no-fatal-infos
flutter test
```

From the repository root:

```text
grep -rn '\\$' mobile/lib
git diff --check
```

The grep may match only intentional displayed dollar prices such as
`upgrade_screen.dart`. Fix any escaped Dart interpolation.

## Completion report

Report:

- branch and SHA,
- exact files changed,
- database upgrade behavior,
- test/analyze results,
- sabotage proof results,
- explicit confirmation that restore emits no signal,
- explicit confirmation that a halted sync makes no second POST.

Do not open a PR until review is requested.
