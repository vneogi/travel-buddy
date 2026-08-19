# Genie Brief -- Itinerary signal, auth gate, Flutter CI

> Status: READY TO IMPLEMENT. Paste this entire file to Genie Code.
> Land via PR to main, not direct push. Owner has no laptop -- unit and
> widget tests plus `flutter analyze` in CI. Device E2E stays deferred.

A third-party review (verified against the tree) found production bugs on
the itinerary and identity path. This PR is those bugs only. It is not
SPEC-12. It is not a rewrite of chat intent. It is not a growth plan.

Canonical rules: `docs/ENGINEERING_RULES.md` (R1, R3, R14, R17).
Identity: SPEC-09 is live (`Authorization: Anonymous <uuid>`). Do not
reintroduce `TB_DEBUG_USER_ID`.

## Goal

1. `reroute_accepted` records the venue that actually replaced the
   swapped node.
2. The visited control and NOW treatment can appear for the node whose
   time window contains now.
3. A device with real Supabase env vars can open the app using the
   anonymous device id (no session required).
4. Chat empty-state copy matches what `ask_info` can do.
5. `flutter analyze` and `flutter test` run in CI.
6. `docker-compose` does not feed a Python file to psql.
7. Outbox reconnect does not wipe retry `attempts`.

## Do not do

- Do not change `_node_from_venue` to mint a new `node_id` on swap.
  SPEC-16 requires `node_id` stable. The bug is the client lookup.
- Do not add `package:collection` for `firstOrNull`. SDK is `>=3.2.0`;
  `Iterable.firstOrNull` is in `dart:core`. If analyzer disagrees, paste
  the error; do not "fix" it by adding a dependency.
- Do not delete `NodeStatus.active` or `emitVisitedConfirmed`.
- Do not write `ACTIVE` on the server in this PR. Client-side window is
  enough for October.
- Do not wire chat text to `swap_activity`. Copy only.
- Do not wire `cacheTrip` / `getCachedTrip` into `ItineraryController`.
  That is SPEC-12 / thin SPEC-04.
- Do not RAG-ify `POST /trip/create`. Demo fixture stays.
- Do not "fix" `1 << attempts` overflow. Dart VM ints are arbitrary
  precision; `_backoffMs` already clamps to 15 minutes. The real bug is
  `attempts = 0` in `resetBackoff`.
- Do not implement SPEC-24 merge, email auth, or re-auth UI.
- Do not edit this brief.

## 1. replacement_ref (blocking, R17)

File: `mobile/lib/features/itinerary/itinerary_screen.dart` `_swap`.

Today:

```
updatedNodes.where((n) => n.nodeId != node.nodeId).firstOrNull
```

Swap keeps `node_id` (`agents/state_machine.py` passes `node.node_id`
into `_node_from_venue`). That filter excludes the node that changed.

Extract a top-level function (same library or a tiny helper file under
`mobile/lib/features/itinerary/`) so tests call production code:

```
String replacementRefForSwap({
  required String originalNodeId,
  required String originalVenueKey,
  required List<TripNode> updatedNodes,
})
```

`originalVenueKey` is `venueId ?? venueName` of the pre-swap node.

Correct rule: the replacement is the updated node whose `nodeId` **equals**
`originalNodeId` and whose `venueId ?? venueName` **differs** from
`originalVenueKey`. Return that new key. If none, return `'unknown'`.

`_swap` must call this function; it must not inline a different predicate.

### Test

New file e.g. `mobile/test/features/itinerary/replacement_ref_test.dart`.

Fixture: original node id `n1` venue `old_venue`. `updatedNodes` contains
`n1` with venue `new_venue` AND `n2` with venue `other_venue` (sibling).

Assert the function returns `new_venue`, not `other_venue`, not
`'unknown'`.

### Sabotage (must run, name the test)

Change the production predicate to `nodeId != originalNodeId` (the old
bug). The named test `replacementRefForSwap picks the same node_id with a
new venue` must fail. Restore. If a different test fails instead, the
guard is wrong.

Do not build a signal map in the test and assert on that map. Assert on
the string the helper returns.

## 2. Current window -> active UI (blocking)

`NodeStatus.active` is never assigned. `activity_card.dart` gates the
visited button and NOW treatment on `node.status == NodeStatus.active`,
so `emitVisitedConfirmed` never fires.

Add a pure helper with injectable `now`:

```
bool nodeIsCurrentWindow(TripNode node, DateTime now)
```

True when status is not skipped/completed AND
`scheduledStart <= now < scheduledStart + durationMinutes`.

The card (or a wrapper that the itinerary already uses) must use this
helper for visited/NOW, not raw `status == active`. Keep rendering
completed/skipped from `node.status`.

If you instead stamp `NodeStatus.active` onto in-memory nodes after
load/event, do it in `ItineraryController` with injectable `now`, and
still unit-test the window function. Do not persist a new status to the
API in this PR.

### Test

Times: now = 10:30 UTC; node 10:00 for 90 minutes -> true; node 12:00
-> false; skipped node in window -> false.

Sabotage: force the helper to `return false;`. Named test must fail.

## 3. Auth gate vs SPEC-09 (blocking)

`mobile/lib/routing/app_router.dart`: when Supabase env is set and
`currentSession` is null, redirect to `/onboarding`.
`onboarding_screen.dart` "Get Started" / "Skip" / "Continue with Email"
all call `context.go('/')` and never create a session. Loop.

SPEC-09 identity does not use a Supabase session. The redirect must not
require one.

Required behaviour:

- Remove (or never take) the `!isAuth -> /onboarding` branch.
- `/` is reachable with no session.
- `/onboarding` may remain as a skippable route. Get Started still goes
  to `/` and must stay there.
- Do not call `Supabase.initialize` with dummy creds (R6).

### Test

Widget or GoRouter test: with a fake that makes `_supabaseReady` true
(or inject a redirect callback / test seam -- do not rely on real
Supabase). Opening `/` does not redirect to `/onboarding`. Tapping
through onboarding `go('/')` does not bounce back.

If the current `bool get _supabaseReady` is hard to fake, extract
`redirectForAuth({required bool supabaseReady, required bool hasSession,
required String location})` and unit-test it: `supabaseReady true,
hasSession false, location '/'` returns null.

Sabotage: restore `if (!isAuth && !isOnboarding) return '/onboarding'`.
Named test must fail.

## 4. Chat copy (blocking, one string)

`mobile/lib/features/chat/chat_screen.dart` empty state currently
suggests swapping a stop. Chat always sends `EventType.askInfo`.
`classify_intent` does not rewrite `event_type`. Structural edits only
run for cancel/swap/add/reroute.

Replace that suggestion with copy that is a question (hours, what is
nearby), not a mutation. Do not change `EventType.askInfo`.

No new test required beyond `flutter analyze` if the file is
already covered; a goldens-free find in a small test that the old
substring `"Swap the next stop"` is absent is acceptable.

## 5. Flutter CI (blocking)

`.github/workflows/` has no Flutter job. Add one job (prefer
`.github/workflows/test.yml` so it does not sit behind Docker/Railway
in `ci.yml`):

- `actions/checkout`
- `subosito/flutter-action` on channel `stable`
- working directory `mobile`
- `flutter pub get`
- `flutter analyze` (errors must fail the job; `--no-fatal-infos` is
  allowed if the tree already has infos; do not disable rules to go
  green)
- `flutter test`

Fix the compile error: `profile_screen.dart` uses `AppTypography.body2`.
The token is `bodyMedium`. That is the whole rename. Grep `body2` in
`mobile/` and leave zero hits.

Do not add a Flutter job that `continue-on-error: true`.

## 6. docker-compose (blocking, one line)

`docker-compose.yml` mounts `./models/database.py` as
`/docker-entrypoint-initdb.d/init.sql`. Remove that volume. Do not
invent an init SQL in this PR unless it is a trivial `CREATE EXTENSION
vector` one-liner you already trust. pgvector image may already include
the extension; if you add SQL, keep it ASCII and do not copy Python.

## 7. resetBackoff (blocking)

`OfflineDatabase.resetBackoff` currently:

```
UPDATE outbox SET next_retry_at = NULL, attempts = 0 WHERE state = 'pending'
```

Change to clear `next_retry_at` only. Keep `attempts`. Reconnect still
makes rows immediately eligible; the next failure continues the existing
backoff ladder.

Update `mobile/test/offline_sync_test.dart` test 12: still expects the
row eligible and `next_retry_at` null; assert `attempts` is **not**
reset to 0 (it stays at the markRetry value).

### Sabotage

Re-add `attempts = 0` to the SQL. Named test must fail.

## 8. 401 halt (non-blocking if timeboxed; do it if small)

`SyncEngine` catches `UnauthorizedException`, logs "halting", then the
60s timer and `finally` pending-reset keep retrying. Add `_authHalted`;
`syncOnce` returns immediately while set; connectivity regain must not
clear it. No re-auth UI. Test: after a fake 401, a second `syncOnce`
does not POST. If this fights the existing fake, skip and say so in the
PR; do not spend the PR on a new mock framework.

## Proof

- `grep -rn body2 mobile/` -- no hits
- `grep -rn '\\$' mobile/lib` -- only the two price strings in
  `upgrade_screen.dart` (R1)
- Named sabotage tests above: break, fail, restore
- `flutter analyze` and `flutter test` from `mobile/`
- Backend: `ruff` + `pytest` for any Python you touch (compose-only
  change needs no pytest)

## PR

Branch: `fix/itinerary-signal-auth-ci`
Title: `fix(mobile): replacement_ref, current-window visited, anonymous gate, flutter CI`

PR body: list the seven items. Name the sabotage tests. State that
SPEC-12 is not in this PR.
