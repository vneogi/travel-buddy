# SPEC-30: Retention Instrumentation and the "Did This Happen" Node State

> Status: DONE. Phase 1 merged in PR #32 (`f8349a8`); durable node outcomes and
> explicit cancel-target confirmation merged in PR #34 (`83c825f`).
>
> Depends on SPEC-02 (the outbox that transports it), SPEC-06/07 (the signal
> registry and emission path), and SPEC-16 (the observed_duration_minutes column
> this writes on `trip_edge`, not `trip_node`).
>
> Migration 0024 registers `session_start`. Apply on hosted Postgres before the
> first live ingest; until then ingest reports `rejected=1`.

## Goal

Make the north-star measurable, and give the transition-data column its missing
writer, with the smallest set of changes that survives the field test. The
metric that decides a Seed round -- do people reopen during a trip, and again on
the next one -- is recorded as `session_start`. Cohorts still cannot validate
retention; one traveller on one trip proves the software, not the curve.

## Why these are one spec

Three gaps share a shape: a signal that is registered but never emitted, a
metric that is stated but never measured, and a column that exists but has no
writer. They are one traveller action apart from each other. "I opened the app"
and "I actually did this stop" are the two facts the whole retention and
transition story is built on. Bundling them means
one lifecycle hook and one derivation pass instead of three, and it stops the
observed_duration writer being deferred a fourth time behind a bigger spec.

## Design decisions

1. **session_start is a behavioural signal, not analytics bolted on.** It rides
   the same outbox as every other signal (SPEC-02), so it works offline and syncs
   on reconnect exactly like a reroute. There is no second telemetry path to
   build, secure or delete under SPEC-27.

2. **The payload is trip-relative, because the metric is.** created_at already
   carries wall-clock on every signal; what analytics cannot reconstruct later is
   *where in the trip* an open fell. "Reopened on day 3 when the plan broke" and
   "reopened eight months later on the next trip" are the two retention questions,
   and both need the open located against the trip, not the calendar.
   `minutes_since_last_open` is computed on-device from the last emitted
   session_start and needs no server round-trip.

3. **Retention is derived, never asked, and not shipped for October.** Cohorts are
   computed server-side from the accumulated session_start stream, the same way
   arrival_delta is derived from visited_confirmed. No cohort table or dashboard
   ships for the field test; the raw signal is enough to compute the curve
   afterward, and building the derivation before there is data to derive from is
   premature. One traveller on one trip cannot validate retention regardless --
   that needs cohorts -- so this captures the shape, it does not claim the result.

4. **"Did this happen" reuses visited_confirmed and node_skipped; it invents no
   signal.** Both are already in the registry (SPEC-06). What is missing is the UI
   affordance that emits them, and the honesty that the current itinerary gives a
   traveller no way to say a stop happened. One control per active or past node --
   happened, or skipped with the closed node_skipped reason picker -- closes it.

5. **observed_duration_minutes is derived from that confirmation, on sync,
   server-side.** When a node is confirmed visited, observed duration is the span
   from its confirmed arrival to the next node's confirmed arrival, written to the
   SPEC-16 column on `trip_edge`. It cannot be computed at save time,
   only from arrival signals, which is exactly why SPEC-16 named it and left it
   empty until SPEC-30. It is absent, not zero, while the next node is unconfirmed.

6. **The "cancel next stop" bug is fixed by the same node state, not separately.**
   The client already has the node-window helper; targeting the next *movable*
   node rather than the first pending one is the on-device half, and the
   confirmation state is what tells it which nodes are behind the traveller.
   Recorded here because the cheapest writer for observed_duration and the correct
   target for cancel are the same fact about which stops already happened.

## Non-goals

- **No cohort or retention dashboard for October.** Raw signal only; the curve is
  computed after the field test from accumulated data.
- **No push or re-engagement.** SPEC-27 owns notifications; a retention *signal* is
  not a retention *nudge*.
- **No dwell or session-length tracking** beyond the open event. Dwell is a later,
  heavier signal and is not needed to answer the reopen question.
- **No background location or timer polling.** session_start fires on foreground
  from the existing app-lifecycle hook, not from a background loop.

## Shape

Registry addition (models/signal_types.py plus a migration seeding signal_type):

    session_start: "json"

    PAYLOAD_SHAPES["session_start"] =
      "json: {trip_id: optional str, trip_day: optional int,
              minutes_since_last_open: optional int, cold_start: bool}"

    category: behavioral      -- set in the migration, not Python
    decay_policy: none        -- an app open does not decay; it is history

trip_day is null when there is no active trip. minutes_since_last_open is null on
the first open on a device. Both are null rather than zero, because zero is a real
value here and a missing measurement is not.

## Tests

- session_start is client-emittable, rides the outbox, and a queued open survives
  a restart and syncs on reconnect (reuses the SPEC-02 crash-recovery drill).
- trip_day and minutes_since_last_open are computed on-device and are null in the
  two documented cases -- no active trip, and first open -- rather than zero.
- Confirming a node emits visited_confirmed; skipping emits node_skipped with a
  reason from the closed NODE_SKIPPED_REASONS set.
- observed_duration_minutes is written on sync from two confirmed arrivals, and is
  absent, not zero, when the next node is unconfirmed.
- "cancel next stop" targets the next movable node given a set of confirmed and
  past nodes, asserted by the existing current-window test extended with
  confirmation state.
- The drift guard (tests/test_signal_types.py) passes with the new type present in
  both Python and the migration.

## Acceptance

- [x] session_start in the registry (Python plus migration 0024), behavioral,
      decay none, drift guard green (`f8349a8`)
- [x] Client emits session_start on foreground through the outbox, carrying
      trip-relative timing (cold start and resume, 30s debounce; tripId from
      `/trip/:id`; client trip_day from cached itinerary)
- [x] A durable UI affordance emits visited_confirmed / node_skipped for active
      and past nodes without re-emitting on restore (`83c825f`)
- [x] observed_duration_minutes written on `trip_edge` on ingest of consecutive
      arrivals (`update_edge_observed_duration`); dual-write preserves observed
      minutes on matching from/to pairs
- [x] "cancel next stop" uses `nextMovableStop` (already in tree; not rebuilt)
- [x] Suite green on origin/main at `f8349a8` (lint, pytest, Flutter analyze,
      Flutter test)

## As built (PR #32)

Do not write observed minutes onto `trip_node`. The column lives on
`trip_edge.observed_duration_minutes` (SPEC-16 / migration 0014). An early Genie
draft targeted a non-existent node column; the merge retargeted the writer.

When `trip_id` is present, the server stamps authoritative `trip_day` from
`captured_at` versus `trip.created_at`. Client `trip_day` is still sent from
cached itinerary for offline honesty.

Emit is fire-and-forget with a catch-all; a failed open must not block launch.

Owner laptop: first ingest `rejected=1` until 0024 was applied on hosted
Postgres; after apply, `accepted=1 rejected=0`. Flutter `session_start` tests
need `NetworkException` mocked and `syncEngine.stop()` before `db.close()`.
