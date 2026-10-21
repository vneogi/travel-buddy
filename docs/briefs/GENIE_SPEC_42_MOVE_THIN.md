# Genie brief: thin typed Move

## Goal

Let the traveller move one flexible itinerary node to another date and
named slot inside the trip span, after explicit confirmation. The same
`node_id`, venue, loved state, and outcome stay on that node. Nothing
else on either day is rewritten.

This is the SPEC-42 Move command. It is not swap, not Ask-to-Add, not
the empty-day `Add activity` button, and not uncatalogued place capture.

Read before editing:

- `docs/specs/SPEC-42-flexible-trip-span.md` (move vs add vs swap)
- `docs/specs/SPEC-41-hours-aware-scheduling.md` (slots, hours, walking, locks)
- `docs/ENGINEERING_RULES.md`
- `docs/WAYS_OF_WORKING.md`

Base branch: latest `main`, including Ask-to-Add `0344b4b` (PR #74) and
docs `83aecfd`.

Create and push:

`feat/spec42-move-thin`

Do not merge. Open a PR after the gates below are green.

## Why this exists

Oct 11 field use needed lunch-to-dinner and defer-to-another-day without
the app rewriting the rest of the day. Swap changes venue in a slot.
Ask-to-Add inserts a new catalog node. There is still no command that
changes only the date/slot of an existing flexible node.

## Current production seams to reuse

- `POST /api/v1/trip/event`
- `TripEventRequest.target_node_id` and `preferences`
- `TripNode.node_id`, `slot_name`, `scheduled_start`, `is_locked`,
  `node_kind`, `geo_region`, `duration_minutes`
- `services.day_slots.SLOT_ORDER` and `has_matching_slot` / `is_food_venue`
- `services.catalog_itinerary._slot_floor_utc` (or the same floors:
  morning 00:00, lunch 11:00, afternoon 14:00, dinner 17:00 local)
- `services.opening_hours.hours_for_slot`
- `services.booking_constraints.fits_next_lock`
- `services.transit.walking_minutes`
- Flutter `ItineraryController.applyEvent` / `sendEvent`
- `ActivityCard` overflow menu and `ActivityDetailScreen` actions
- SPEC-42 date-span rendering (`creationContext` start/end)

Do not create a second planner, a second chat, a WebSocket, a new table,
or a catalog write. Do not add a Flutter command-queue outbox (SPEC-44
later). Do not parse natural language ("later today", "move lunch to
dinner") in this slice; the picker sends an explicit date and slot.

## Scope

### 1. New closed event type

Add `move_activity` to the Python `EventType` enum and the Dart
`EventType` enum (`wire: 'move_activity'`). Update any exhaustive
parity / models tests that list event types.

Do not add `move_activity` to `PlanChangeProposal` in this slice. Ask
confirm of a move proposal is a later remainder.

`move_activity` is structural: add it to `STRUCTURAL_EDIT_EVENTS` and
the trip-router reroute-quota set, same as swap/cancel. Consume quota
only after locked-target refusal, same pattern as locked cancel.

### 2. Typed move payload

Wire shape:

```json
{
  "event_type": "move_activity",
  "target_node_id": "n1",
  "preferences": {
    "mode": "move",
    "target_date": "2026-10-12",
    "target_slot": "dinner"
  }
}
```

Rules:

- `target_node_id` is required and must exist on the trip
- `mode` must be `move`
- `target_date` is required `YYYY-MM-DD` in the destination-local
  calendar and must fall inside the inclusive trip span
- `target_slot` is required and must be one of `SLOT_ORDER`:
  `morning_tour`, `lunch`, `afternoon_evening_tour`, `dinner`
- unknown extra keys on preferences may be ignored
- invalid mode / missing date / unknown slot is a typed refusal or
  request error, not a swap and not a venue_search

Do not accept a free-text place, a clock time as the primary target, or
a different `venue_id`.

### 3. Apply-time feasibility (production predicates)

On `move_activity`:

1. Load the target node. Missing id -> refuse, no write.
2. Locked nodes, `node_kind=booking`, and `is_locked` -> refuse before
   persistence and before quota. Same honesty as locked swap/cancel.
3. Completed or skipped nodes -> refuse.
4. Whole-day excursion vibe tags (`day_slots.WHOLE_DAY_VIBE_TAGS`) ->
   refuse in this slice.
5. Slot type must match the venue: food categories only `lunch` /
   `dinner`; non-food only `morning_tour` / `afternoon_evening_tour`.
   Reuse `has_matching_slot` / `is_food_venue`. Do not invent a second
   mapping.
6. `target_date` region: the moved node's `geo_region` (else trip
   `geo_region`) must match that date's city. For a single-city trip
   every in-span date is allowed, including currently empty dates.
   For a corridor, only dates that already have at least one node in
   the same `geo_region` as the moved node. Cross-city moves refuse.
7. Occupancy: if another flexible (unlocked, non-booking) node already
   has the same `slot_name` on that local date, refuse. Do not swap
   in place. Do not push the occupant to another slot.
8. Resolve planned start from the destination-local slot floor for
   `target_date` + `target_slot` (`_slot_floor_utc` or equivalent).
   Then apply `hours_for_slot` with the node's existing
   `duration_minutes`. If known structured hours cannot fit the slot
   band, refuse. Do not hardcode 90.
9. Walking: when the previous and/or next neighbour on the target date
   (flexible or locked, skipping hotel for lock-fit the same way
   `fits_next_lock` already skips hotel) have finite coordinates, and
   the moved node has finite coordinates, walking time must fit.
   Missing walk cannot claim reachability.
10. `fits_next_lock` must pass for the moved start + dwell against the
    next locked non-hotel on/after that placement. Reuse the shared
    helper. Do not copy a weaker check.
11. Same `node_id` + same local date + same slot as today is a no-op
    refuse (nothing to confirm).

On any failed predicate: itinerary unchanged, typed honest refusal, no
partial rewrite.

On success: update **only** that node's `scheduled_start` and
`slot_name`. Preserve `node_id`, `venue_id`, `venue_name`, loved
storage key, outcome, lock, duration, coords, region, and every other
node. Sort order in responses may follow `scheduled_start`; do not
assign new ids.

Return the real `process_event` HTTP contract
(`updated_trip_state`, `response`, `routing_tier_used`, `from_cache`,
`venues_found`, `schedule_warnings`). Do not return internal
`trip_state` as the top-level key (Ask-to-Add remainder 1).

Zero `llm.complete` calls.

### 4. Flutter: Move from the itinerary card

On an unlocked, non-booking, pending/active flexible card:

- Keep the inline Swap icon.
- Add **Move** to the overflow menu (`Key('move_menu_${node.nodeId}')`).
  Do not add a second 44dp title-row icon (SPEC-45 overflow rule).
- Activity detail gets the same Move action with the same key prefix
  `move_detail_${node.nodeId}`.
- Locked, booking, completed, and skipped cards have no Move.

Tap opens a modal sheet (`Key('move_sheet_v1')`):

- dates: in-span local dates allowed by rule 6 above
- slots: chips for slots the venue type may occupy
- confirm (`Key('move_confirm')`) / cancel (`Key('move_cancel')`)
- date keys `move_date_YYYY-MM-DD`, slot keys `move_slot_<slot>`

Confirm copy names the venue, source date/slot, and target date/slot.
Cancel sends nothing.

Confirm sends **one** `move_activity` via existing `applyEvent` /
`sendEvent` with `targetNodeId` and the preferences object above.
`message` may be a short canned string; it is not parsed.

Offline: existing live-unavailable refusal; do not enqueue; do not
rewrite local nodes.

After success, the itinerary list must show the node on the new date
under the new slot label. Other cards keep their times.

Capture Riverpod locals before awaits. Do not use `pumpAndSettle`.
After widget tests that persist SQLite, drain FFI before
`container.dispose()`. Sheet open needs `pump()` plus `pump(500ms)`
(What Now lesson). Use `ensureVisible` / `_tapKey` for overflow items;
do not set `physicalSize`.

### 5. Tests

Backend, new file `tests/test_spec42_move.py`:

- lunch node moves to dinner on the same Vientiane date; `node_id` and
  `venue_id` unchanged; `slot_name` is `dinner`; other nodes unchanged
- node deferred to an empty in-span date in the same city; source date
  no longer lists it
- locked hotel/flight refuse; itinerary unchanged; quota not consumed
  if the existing locked-cancel pattern skips quota
- occupied target slot refuses (two dinners)
- food node to `morning_tour` refuses; activity node to `dinner` refuses
- corridor cross-city date refuses
- unknown dwell is not invented; keep existing duration; closed hours
  refuse
- next locked flight remains reachable; sabotage `fits_next_lock` walk
  omission must fail the named lock test (R17)
- missing `target_node_id` / missing mode / bad slot refuse
- zero `llm.complete` calls
- `process_event` contract keys include `updated_trip_state`

Flutter widget tests in `mobile/test/spec42_move_test.dart`:

- unlocked card overflow shows Move
- locked / booking card has no Move
- confirm sends one `move_activity` with exact preferences
- cancel sends nothing
- occupied-slot or locked-target server refusal does not locally move
  the card
- offline confirm refuses and enqueues nothing

Reuse unique in-memory `OfflineDatabase(testPath:)`, `tester.runAsync`,
`_flushFfi`, no `pumpAndSettle`, no `physicalSize` hacks.

Closed enums only. Dart/Pydantic `EventType` round-trip for the new
wire value.

### 6. R17 sabotage

1. Temporarily drop the walking term from move-time `fits_next_lock`.
2. Run the named next-lock test.
3. Confirm that exact test fails.
4. Restore.
5. Re-run the focused file green.

Report the test name that failed. A generally red file is not the proof.

## Non-goals

- empty-day itinerary `Add activity` chrome
- uncatalogued / trip-private nodes
- Ask NLQ ("later today", "tomorrow", "move lunch to dinner")
- `PlanChangeProposal` / Ask confirm of move
- swap-in-place or silent day reflow
- moving locked bookings or whole-day excursions
- corridor empty-date moves (no same-region node on that date)
- GPS, LLM, trip-less Ask
- new migration
- hosted deploy, APK, non-owner distribution
- fixing `postgres-proof` apt baseline

## Gates

```bash
ruff check .
ruff format --check .
pytest -q -ra --strict-markers
git diff --check
```

Flutter (say so if the SDK is absent; do not claim it green):

```bash
cd mobile
flutter analyze --no-fatal-infos
flutter test test/spec42_move_test.dart
flutter test test/spec_ask_to_add_test.dart
flutter test test/spec46_what_now_test.dart
flutter test
```

After any Dart edit, R1:

```bash
grep -rn '\\$' mobile/lib
```

Only the two price strings in `upgrade_screen.dart` may match.

Force-push this feature branch as needed. Do not `git pull` after a
force push; fetch and `reset --hard` to origin. No APK. No deploy.
One PR. Do not merge.
