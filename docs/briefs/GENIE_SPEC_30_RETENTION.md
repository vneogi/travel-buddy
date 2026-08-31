# Genie Brief -- SPEC-30 Retention Instrumentation

> Status: LANDED on `main` as `f8349a8` (PR #32). Do not re-implement.
> Observed duration writes **`trip_edge.observed_duration_minutes`**, not a
> column on `trip_node` (that column does not exist). Remainder of the spec is
> past-node confirm/skip UI and explicit cancel-target confirmation.
>
> Historical brief below is kept so the original slice split is readable.

## Why this brief is smaller than the spec

Read the spec, then read this. Three of the things SPEC-30 describes are already
in the repo, and you must NOT rebuild them:

- **`visited_confirmed` and `node_skipped` emission already ship.**
  `itinerary_screen.dart` has `_confirmVisited` and `_skipNode` with a closed
  `_SkipReasonSheet`, wired to `SignalService.emitVisitedConfirmed` /
  `emitNodeSkipped`.
- **"cancel next stop" is already fixed.** `chat_screen.dart:98` uses
  `nextMovableStop(state.nodes, DateTime.now().toUtc())`
  (`features/itinerary/current_window.dart`). Leave it alone.
- **`arrival_delta` already derives server-side** in
  `services/arrival_delta_service.py`, called from `routers/signal_router.py`
  after a new `visited_confirmed` ingests.

So the real gap is two things that do not exist: the retention **open** signal,
and the `observed_duration_minutes` **writer**. That is all this brief covers.

---

# Slice 1 -- `session_start` (the pre-Oct-2 gate). SHIP THIS FIRST.

## Context

The north-star (VISION section 7) is on-trip retention, and nothing records an
app open, so the curve cannot be computed. This slice adds one behavioural
signal that rides the existing outbox (SPEC-02). No second telemetry path.

## Goal

1. A `session_start` signal is emitted through the outbox when the app comes to
   the foreground, both on cold launch and on resume from background.
2. Its payload carries trip-relative timing: which open this is relative to the
   trip and to the previous open.
3. It is durable and offline-safe exactly like every other signal -- persisted
   to SQLite before any network, synced on reconnect.

## Non-goals

- **No cohort or retention dashboard.** Raw signal only; the curve is computed
  later, off the accumulated stream.
- **No push, notifications or re-engagement** (that is SPEC-27).
- **No dwell / session-length tracking.** Only the open event.
- **No background timer or GPS polling.** Fire from the existing lifecycle
  observer, not a loop.
- No new outbox, sync, or identity mechanism.

## Required implementation

### 1. Register the type

`models/signal_types.py`:

- `SIGNAL_TYPES["session_start"] = "json"`
- `PAYLOAD_SHAPES["session_start"] =
  "json: {trip_id: optional str, trip_day: optional int, minutes_since_last_open: optional int, cold_start: bool}"`

New migration `supabase/migrations/0024_session_start.sql`, modelled exactly on
`0021_booking_anchors.sql`:

```sql
INSERT INTO signal_type (key, category, value_kind, enum_values, decay_policy, description) VALUES
    ('session_start', 'behavioral', 'json', NULL, 'none',
     'App came to the foreground; carries trip-relative timing for retention')
ON CONFLICT (key) DO NOTHING;
```

The drift guard `tests/test_signal_types.py` compares Python against the
migrations, not the live DB, so it passes once both land. Leaving 0024 unapplied
on the hosted DB is consistent with 0019-0023.

### 2. Emit on foreground (client)

`session_start` has no venue. Follow the `emitBookingAdded` precedent and pass a
sentinel `placeRef: 'session'` (it resolves to a null venue_id, which is a valid
state in `_resolve_venue_id`). Keep `entityType` default.

Add to `mobile/lib/services/signal_service.dart`:

```dart
Future<void> emitSessionStart({
  required bool coldStart,
  int? minutesSinceLastOpen,
  int? tripDay,
  String? tripId,
}) =>
    emit(
      signalType: 'session_start',
      placeRef: 'session',
      tripId: tripId,
      valueJson: {
        'cold_start': coldStart,
        if (minutesSinceLastOpen != null) 'minutes_since_last_open': minutesSinceLastOpen,
        if (tripDay != null) 'trip_day': tripDay,
      },
    );
```

Hook it into the **existing** `WidgetsBindingObserver` in `mobile/lib/main.dart`
(the one already handling `didChangeAppLifecycleState` for SPEC-29 alert
refresh). Emit:

- once on first foreground of the process (`cold_start: true`), and
- on each `AppLifecycleState.resumed` after a real background
  (`cold_start: false`).

Debounce a resume that fires within a few seconds of the last emit so an OS
flicker does not double-count.

### 3. Compute the trip-relative fields

- **`minutes_since_last_open`** is on-device. Persist a `last_session_at`
  timestamp durably and read it before overwriting. Add a minimal durable getter
  and setter to `OfflineDatabase` (a tiny `app_kv(key TEXT PRIMARY KEY, value
  TEXT)` table, created in `_onCreate` and the upgrade path, is fine). Null on the
  first ever open on the device -- null, not zero.
- **`cold_start`** is an in-memory bool: false until the first emit of this
  process, so the launch open is the only `cold_start: true` per process.
- **`trip_day`** is best-effort on the client from the active trip's cached start
  date when one is open; null otherwise. Do not block the emit on resolving it.

### 4. Server: stamp an authoritative `trip_day`

Client `trip_day` is best-effort and absent when offline caches are cold, so make
the server the source of truth when a trip is known. In
`routers/signal_router.py`, in the ingest loop where `value_json` is built, add:

```python
if sig.signal_type == "session_start" and sig.trip_id:
    trip = db_service.get_trip(sig.trip_id)
    if trip:
        start = trip.created_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        cap = sig.captured_at
        if cap.tzinfo is None:
            cap = cap.replace(tzinfo=timezone.utc)
        value_json["trip_day"] = (cap.date() - start.date()).days
```

This mirrors the existing `day_index` computation in `_build_party_context`, works
retroactively off the verbatim `captured_at`, and does not depend on a party
existing. It overrides any client-sent `trip_day`.

## Required tests

Backend (`tests/`):

- `session_start` is accepted by `POST /api/v1/signals` (not in
  `SERVER_DERIVED_TYPES`, valid type).
- A `session_start` with a known `trip_id` gets `value_json["trip_day"]` stamped
  as days since `trip.created_at`, computed from `captured_at` (prove with an old
  `captured_at` that the day is trip-relative, not wall-clock-today).
- A `session_start` with no `trip_id` ingests fine and carries no `trip_day`.
- `tests/test_signal_types.py` passes with the new type in Python and 0024.

Client (`mobile/test/`):

- `emitSessionStart` enqueues one outbox row with the documented `value_json`
  shape (real `OfflineDatabase`, assert the enqueued payload).
- `minutes_since_last_open` is null on the first open and is the elapsed minutes
  on the second, computed from the persisted `last_session_at`.
- The first emit of a process carries `cold_start: true` and a subsequent resume
  carries `cold_start: false`.
- A resume within the debounce window does not enqueue a second row.

## Sabotage proofs (slice 1)

Break each, prove the named test fails, then restore. Do not commit sabotage.

1. Remove `session_start` from `SIGNAL_TYPES` -> drift guard fails.
2. Compute `trip_day` from `datetime.now()` instead of `captured_at` -> the
   old-`captured_at` test fails.
3. Return zero instead of null for a first open -> the null-on-first-open test
   fails.
4. Drop the debounce -> the double-emit test fails.

---

# Slice 2 -- `observed_duration_minutes` writer. SEPARATE PR.

## Context

`observed_duration_minutes` on `trip_node` (SPEC-16) has no writer, so no
transition data accumulates -- the last open SPEC-16 defect, and a standing
Medium risk in `PROJECT_STATUS`. It is derivable from the confirmations that
already ingest, the same shape as `arrival_delta`.

## Goal

When a node's arrival is confirmed and the previous scheduled node's arrival was
also confirmed, write the previous node's observed duration = the span between
the two confirmed arrivals. Never break ingest; idempotent on re-derivation.

## Required implementation

Add `services/observed_duration_service.py`, modelled on
`services/arrival_delta_service.py`:

```
derive_observed_duration(source_signal_id, user_id, place_ref, captured_at, trip_id)
```

Behaviour:

- Return early (log, no raise) if `trip_id` is missing or the trip/node is not
  found -- identical failure discipline to `arrival_delta`.
- Resolve the target node for `place_ref` (reuse `_find_node_for_place` logic).
- Find the node scheduled immediately **before** the target in the trip.
- Look up that previous node's `visited_confirmed.captured_at` from the stored
  signals. If it is absent, return (the pair is not complete yet).
- Write `observed_duration_minutes` on the **previous** node =
  `(target.captured_at - prev_confirmed.captured_at)` in minutes, rounded to 1
  decimal, only if positive.
- Idempotent: writing the same value is a no-op; re-processing must not change
  the result.

Call it from `routers/signal_router.py` right after the existing
`derive_arrival_delta` call in the `visited_confirmed` branch.

Add the two db operations this needs, in **both** backends (Supabase and
in-memory) behind `db_service`:

- fetch the most recent `visited_confirmed` for a given `trip_id` + node/place,
- update `trip_node.observed_duration_minutes` for a node.

## Required tests (`tests/`)

- Two confirmed arrivals on consecutive nodes write the first node's
  `observed_duration_minutes` as the minute span between them.
- A single confirmation writes nothing (pair incomplete), and the column stays
  absent, not zero.
- Re-posting the same `visited_confirmed` does not change the written value
  (idempotent).
- A confirmation whose computed span is negative (clock skew / out-of-order)
  writes nothing.
- Derivation failure (unknown trip) never rejects the source `visited_confirmed`
  -- the batch still reports it accepted.

## Sabotage proofs (slice 2)

1. Write the duration on the target node instead of the previous node -> the
   consecutive-pair test fails.
2. Remove the "previous confirmed exists" guard -> the single-confirmation test
   fails.
3. Let a negative span through -> the skew test fails.

---

## Verification (both slices)

From `mobile/`:

```text
dart format --output=none --set-exit-if-changed lib test
flutter analyze --no-fatal-infos
flutter test
```

From the repository root:

```text
pytest -q -ra
git diff --check
grep -rn '\\$' mobile/lib
```

Install `requirements-dev.txt` before pytest. The `grep` should match only
intentional displayed dollar prices; fix any escaped Dart interpolation.

## Completion report

For each slice, report:

- branch and SHA, exact files changed,
- migration behaviour (0024) and the `app_kv` upgrade path,
- test / analyze results,
- sabotage proof results,
- explicit confirmation that `session_start` rides the outbox and never blocks
  the UI thread,
- for slice 2, explicit confirmation that a derivation failure leaves the source
  `visited_confirmed` accepted.

Do not open a PR until review is requested. Slice 1 and slice 2 are separate PRs;
slice 1 lands first.
