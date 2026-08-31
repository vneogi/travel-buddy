# Genie Brief -- SPEC-30 Remainder

> Status: IMPLEMENTED ON `feat/spec30-remainder`; AWAITING GENIE REVIEW.
> Do not re-implement from this brief. Use
> `docs/briefs/GENIE_SPEC_30_REMAINDER_REVIEW.md` for the review-only handoff.
> Base every implementation branch on `origin/main` at or after `e689346`.
> SPEC-30 phase 1 landed in PR #32 (`f8349a8`). Do not rebuild
> `session_start`, migration 0024, or the `trip_edge` observed-duration writer.
> Spec: `docs/specs/SPEC-30-retention-instrumentation.md`.

## Goal

Finish the two traveller-facing gaps left after SPEC-30 phase 1:

1. Let a traveller record whether an active or elapsed itinerary node happened.
   The decision must survive app restart and must not emit twice after restore.
2. Before chat executes "cancel next stop", show which stop it selected and
   require explicit confirmation. Dismissing or declining must make no backend
   call and consume no reroute quota.

This is one client-only PR. No Python, Supabase migration, signal registry, or
observed-duration change belongs in it.

## Current code: preserve these facts

- `mobile/lib/features/itinerary/itinerary_screen.dart` already emits
  `visited_confirmed` and `node_skipped`.
- `_SkipReasonSheet` already owns the closed skip-reason set. Reuse or extract
  it; do not create a second vocabulary.
- `ActivityCard` only shows "I'm here" while `nodeIsCurrentWindow` is true.
  Elapsed pending nodes have no outcome control.
- Confirming visited only emits a signal. It does not change `TripNode.status`.
- Active skip emits `node_skipped` and then sends `cancel_activity`.
- `chat_screen.dart` silently selects `nextMovableStop(...)` and immediately
  sends the event.
- `nextMovableStop` already excludes elapsed, locked, completed, and skipped
  nodes. Keep that behavior.
- Durable hearts demonstrate the local persistence pattern, but node outcomes
  are keyed by stable `node_id`, not by venue. The same venue can occur twice.

## Product decisions

### 1. A recorded outcome is durable local state

Add a small identity-scoped SQLite table:

```text
node_outcome(
  identity_scope TEXT NOT NULL,
  trip_id        TEXT NOT NULL,
  node_id        TEXT NOT NULL,
  outcome        TEXT NOT NULL,  -- visited | skipped
  reason         TEXT,           -- required for skipped, null for visited
  recorded_at    TEXT NOT NULL,
  PRIMARY KEY (identity_scope, trip_id, node_id)
)
```

Bump `OfflineDatabase` from version 5 to 6. Create the table in `_onCreate` and
in `_onUpgrade` when `oldVersion < 6`.

Add a small immutable `NodeOutcome` value and:

```text
upsertNodeOutcome(...)
getNodeOutcomes(identityScope, tripId) -> Map<nodeId, NodeOutcome>
```

Use insert-or-replace so a traveller can correct a local decision. Validate the
two outcome strings in Dart before writing. A skipped outcome requires a reason.

This table is the client hydration layer, not a second analytics stream. Only a
real tap emits a signal. Restoring it after navigation, reload, or process death
must never emit.

Known boundary: another device will not hydrate this local acknowledgement yet.
The accepted signals remain server history; a server projection can be added
later. Do not invent that API in this slice.

### 2. Show one clear outcome control

Add pure helpers in `current_window.dart` with injected `now`:

```text
nodeCanRecordOutcome(node, now, recordedOutcome)
nodeIsElapsed(node, now)
```

Rules:

- Show the control for a pending node whose window is active or has ended.
- Hide it for future, completed, or skipped nodes.
- Hide it when a local outcome already exists.
- Do not key eligibility on venue or list position.

The card control should say **"Did this happen?"**. Opening it presents:

- **Yes, I went**
- **No, I skipped it**
- **Not sure yet** (dismiss only)

For "No", use the existing closed reason picker.

After a decision, replace the control with a compact non-interactive state:

- visited: **Visited**
- skipped: **Skipped: <human reason>**

Do not rely only on color or an icon.

### 3. Persist and emit in the right order

Route both actions through `ItineraryController`, not private fire-and-forget
methods in the screen. The controller already owns identity scope, trip state,
and local hydration.

For visited:

1. Call `emitVisitedConfirmed`; awaiting it means the outbox insert completed,
   not that network sync completed.
2. Persist `node_outcome`.
3. Update controller state optimistically.

For skipped:

1. Call `emitNodeSkipped` with the selected closed reason.
2. Persist `node_outcome`.
3. Update controller state.
4. If the node is currently active, unlocked, and still pending, send the
   existing `cancel_activity` so the remaining plan can reflow.
5. If the node is elapsed or locked, do not send a structural cancel. Recording
   what happened is not the same as retroactively mutating a booking or spending
   reroute quota.

If local outcome persistence fails after a successful outbox insert, retain the
in-memory acknowledgement and show ordinary recoverable copy. Never enqueue the
same signal again automatically.

Disable the outcome sheet while a decision is being persisted so a double tap
cannot enqueue duplicates.

### 4. Hydrate without overwriting server nodes

Add `nodeOutcomes` and an `outcomeRecordingNodeIds` set to `ItineraryState`.
Restore outcomes during `load()` in the same failure-tolerant style as durable
hearts. Preserve them through reload and `applyEvent`.

Do not rewrite `TripNode.status` in cached JSON. A local acknowledgement and the
server itinerary status are distinct until a server projection exists.

### 5. Make cancel targeting outcome-aware

Extend `nextMovableStop` with an optional set of excluded node IDs, or add a
small wrapper. Chat passes locally recorded node IDs so an active node already
marked visited/skipped cannot be selected.

Do not change the existing rules for elapsed, locked, completed, and skipped
nodes.

### 6. Confirm the exact chat target

For `AskIntent.cancelNext` only:

1. Resolve the outcome-aware target.
2. Show a modal confirmation before `sendEvent`:
   - title: **Cancel this stop?**
   - body includes the venue name and scheduled local time
   - actions: **Keep it** and **Cancel this stop**
3. Only the destructive action may call `sendEvent`.

If the traveller keeps it or dismisses the dialog:

- make no repository/API call,
- clear the thinking state,
- add concise assistant copy such as `Kept <venue>.`,
- leave the itinerary unchanged.

The initial user message can remain in chat history. The app must not display a
success message before the server result.

Do not add a confirmation to `swap next stop` in this slice.

## Files expected to change

- `mobile/lib/offline/offline_database.dart`
- `mobile/lib/features/itinerary/current_window.dart`
- `mobile/lib/features/itinerary/itinerary_notifier.dart`
- `mobile/lib/features/itinerary/itinerary_screen.dart`
- `mobile/lib/widgets/activity_card.dart`
- `mobile/lib/features/chat/chat_screen.dart`
- focused tests under `mobile/test/`

Keep this client-only. If implementation appears to require a backend or schema
migration, stop and report why before adding one.

## Required tests

### Pure helper tests

Extend `mobile/test/features/itinerary/current_window_test.dart`:

- active pending node can record an outcome,
- elapsed pending node can record an outcome,
- future pending node cannot,
- completed/skipped node cannot,
- a locally recorded node cannot,
- `nextMovableStop` excludes a locally acknowledged active node and selects the
  following eligible node,
- all pre-existing target-selection tests still pass.

### Offline database tests

Use real SQLite:

- v6 fresh create can upsert and read visited and skipped outcomes,
- identity and trip isolation,
- two nodes at the same venue remain distinct by `node_id`,
- replace corrects an outcome without creating a second row,
- upgrade from a real v5 schema to v6 preserves existing outbox, cache,
  `loved_places`, and `app_kv` rows.

The upgrade test must open an actual version-5 database, close it, then open it
through production `OfflineDatabase`; calling `_onUpgrade` directly is not
proof.

### Controller tests

- restore hydrates state and emits no signal,
- visited tap enqueues exactly one `visited_confirmed` and persists one outcome,
- skipped tap enqueues exactly one `node_skipped` with the selected reason,
- double tap while recording enqueues once,
- elapsed skip sends no structural event,
- locked skip sends no structural event,
- active unlocked skip sends one existing `cancel_activity`,
- persistence failure does not crash or remove the in-memory acknowledgement.

Use the real `SignalService` + real in-memory `OfflineDatabase` where asserting
outbox behavior. Mock exceptions with the production exception type.

### Widget tests

- elapsed card shows "Did this happen?",
- selecting visited changes it to textual "Visited",
- selecting skipped requires a reason and shows textual skipped state,
- future card has no outcome control,
- cancel-next confirmation names the selected venue,
- **Keep it** and barrier dismissal make zero `sendEvent` calls,
- **Cancel this stop** makes exactly one call with the displayed node ID,
- swap-next behavior remains unchanged.

Widget tests must not open real network, SQLite, fonts, or timers. Override
providers explicitly.

## Sabotage proofs

Break each behavior, run the named test, then restore. Do not commit sabotage.

1. Remove the v5-to-v6 upgrade block: the real upgrade test fails.
2. Key outcomes by venue instead of node ID: repeated-venue isolation fails.
3. Emit during hydration: restore-without-emission fails.
4. Remove the in-flight node guard: double-tap test fails.
5. Structurally cancel an elapsed or locked node: corresponding controller test
   fails.
6. Bypass the confirmation dialog: Keep-it zero-call test fails.
7. Send a different node than the one displayed: exact-node-ID test fails.

## Verification

From `mobile/`:

```text
dart format --output=none --set-exit-if-changed lib test
flutter analyze --no-fatal-infos
flutter test
```

From repository root:

```text
pytest -q -ra
git diff --check
```

No test count belongs in living docs.

## Completion report

Report:

- branch, SHA, and exact files changed,
- database version and v5-to-v6 upgrade proof,
- outcome eligibility and locked/elapsed behavior,
- confirmation decline/dismiss/accept call counts,
- full format, analyze, Flutter test, pytest, and diff-check results,
- each sabotage proof and the test that failed.

Do not open a PR until review is requested.
