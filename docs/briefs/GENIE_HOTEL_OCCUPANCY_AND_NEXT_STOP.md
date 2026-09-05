# Genie Brief -- Hotel Occupancy and Time-Aware Next Stop

> Status: READY TO IMPLEMENT.
> Land through a feature branch and PR to `main`; do not push directly to
> `main`. Branch from latest `main`. Do not combine this with durable hearts.
> Hearts is a separate Flutter slice on `feat/durable-hearts-sync-status`.

## Context

Two independently-correct features now break the Vang Vieng path.

**B1 -- hotel stay duration occupies the timeline.**
`booking_parser.dart` stores real stay length (`checkOut - checkIn`). For the
Mad Monkey email that is 2760 minutes (`booking_test.dart` asserts `46 * 60`).
`add_booking_sheet.dart` sends `duration_minutes`. `ADD_BOOKING` creates a
locked node with that duration. `services/scheduler.py` then sets
`prev_active_end = start + duration_minutes` for every non-skipped node,
including hotels. Every later unlocked activity is pushed to checkout and
stacked from there. Adding a real Booking.com hotel moves Oct 4 evening and
Oct 5 onto Oct 6.

The scheduler has no `booking_type` / occupancy concept. Existing booking
tests use 180-minute flights, so they stay green.

**B2 -- "cancel next stop" cancels the first pending stop of the day.**
`chat_screen.dart` picks
`status == pending && !isLocked` with no time filter. Nothing in the app
assigns `NodeStatus.completed` (do not add that in this slice). Morning nodes
stay pending all day. At 17:00 the canned copy can say
`Canceled <09:00 venue>`. The same picker feeds swap-next and the
"no movable stop" guard.

`nodeIsCurrentWindow` in `mobile/lib/features/itinerary/current_window.dart`
already reasons about start/end. This path does not use it.

## Goal

1. A multi-night hotel booking must not shift later unlocked activities past
   checkout.
2. Check-in time of a locked hotel stays fixed (existing lock rules).
3. Flights, trains, and tours that occupy a real window still occupy the
   timeline.
4. "cancel next stop" and "swap next stop" target the first unlocked pending
   node whose window has not ended.
5. Named sabotage tests fail on today's code and pass after the fix.

## Non-goals

- Do not invent `NodeStatus.COMPLETED` writers, GPS, dwell, or
  `observed_duration_minutes`.
- Do not change Booking.com parsing or shorten hotel duration to 30 minutes
  as the product fix. Keep the real stay length on the node.
- Do not invent Fair Fare, synthetic transit copy, or dietary claims.
- Do not rewrite hotel rescue selection or date grouping.
- Do not touch hearts/sync/alerts.
- Do not apply hosted migrations.

## Required implementation

### B1 -- hotels are background anchors

In `services/scheduler.py`, a hotel booking must **not** advance
`prev_active_end`.

Preferred model: a node occupies the timeline unless it is a hotel booking
(`node_kind == "booking"` and `booking_type == "hotel"`). Flights stay
occupying (180 minutes remains correct).

After processing a non-occupying hotel:

- Do not set `prev_active_end = start + duration`.
- Locked hotel start time still never moves.
- Hard-conflict for *other* locked nodes must not be triggered by hotel
  checkout math.

Keep SPEC-29 rules: skipped nodes stay in place; do not emit synthetic
transit / "unreachable" user copy.

Optional small helper on `TripNode` or in the scheduler is fine. Do not add
a database migration for an `occupies_timeline` column in this slice unless
you can derive it purely from existing `booking_type`.

### B2 -- time-aware next movable stop

Extract a testable helper next to `nodeIsCurrentWindow`, for example
`nextMovableStop(nodes, now)`:

- pending
- not locked
- window has not ended:
  `scheduledStart + durationMinutes` is after `now`
- first match in list order

Use it in `chat_screen.dart` for cancel-next, swap-next, and the empty
movable-stop message.

Do not pump the full chat widget if a helper test can sabotage the
predicate. Inject `now` (parameter), do not hide `DateTime.now()` inside
the helper.

A currently-in-progress unlocked stop (window contains `now`) **is** a
valid target. A stop that already ended is not.

## Required tests

### B1 (pytest)

1. Two-night hotel Oct 4 14:00, duration 2760 minutes, locked,
   `booking_type=hotel`, plus an unlocked activity Oct 5 09:00. After
   `reschedule_and_validate`, the activity `scheduled_start` is still
   Oct 5 09:00.
2. Control: a 180-minute locked **flight** ending after a later unlocked
   node's planned start still pushes that node (occupying bookings unchanged).
3. Existing scheduler / cancel-correctness / synthetic-transit tests stay
   green.

### B2 (Flutter)

1. Pending nodes at 09:00, 13:00, 17:00, each 60 minutes, `now = 15:00`.
   `nextMovableStop` is the 17:00 node.
2. Same list, `now = 09:30`. Target is the 09:00 node (window still open).
3. All remaining pending windows already ended -> helper returns null
   (feeds the "no movable upcoming stop" copy).

## Sabotage proofs

1. Hotel still advances `prev_active_end` -> B1 hotel test fails.
2. Flight no longer occupies -> B1 flight control fails.
3. Helper ignores end time and takes `.first` pending unlocked -> 15:00
   test returns 09:00.
4. Helper requires `scheduledStart.isAfter(now)` only, skipping the current
   window -> 09:30 test fails.

Do not commit sabotage.

## Verification

Backend:

```text
ruff check . --config pyproject.toml
ruff format --check .
pytest tests/test_scheduler.py tests/test_booking_anchors.py tests/test_cancel_correctness.py tests/test_synthetic_transit.py -q
```

Add new scheduler tests in `tests/test_scheduler.py` or a dedicated file
imported by pytest.

Flutter (when the SDK is available):

```text
cd mobile
dart format --output=none --set-exit-if-changed lib test
flutter analyze --no-fatal-infos
flutter test test/features/itinerary/current_window_test.dart
```

If analyze is already red from `db_init_web.dart` / `sqflite_common_ffi_web`
on Linux (known since `84b4926`), do not "fix" that in this slice. Report it
as pre-existing. New tests must still be added.

Root:

```text
grep -rn '\\$' mobile/lib
git diff --check
```

Only intentional displayed prices in `upgrade_screen.dart` may match.

## Completion report

- branch and SHA
- files changed
- how hotel occupancy is gated
- pytest results
- named sabotage results
- explicit confirmation that Mad Monkey-scale hotel duration no longer moves
  the Oct 5 activity
- explicit confirmation that at 15:00 the next-stop helper returns the 17:00
  node

Do not open a PR until review is requested.
