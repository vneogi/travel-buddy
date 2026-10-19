# Genie brief: thin typed Ask-to-Add

## Goal

Let the traveller add one What Now catalog candidate to the trip as a new
node, after explicit confirmation. One command inserts one node. Existing
nodes keep their `node_id`, start time, and slot. Nothing else on the day
is rewritten.

This is not the SPEC-42 empty-day `Add activity` button, not Move, and not
uncatalogued place capture. Those remain the next remainders after this PR.

Read before editing:

- `docs/specs/SPEC-42-flexible-trip-span.md` (direct add vs move vs swap)
- `docs/specs/SPEC-46-what-now-foreground-context.md`
- `docs/specs/SPEC-25-ask-anything.md`
- `docs/ENGINEERING_RULES.md`
- `docs/WAYS_OF_WORKING.md`

Base branch: latest `main`, including `d1df944` (SPEC-46 Phase A, PR #73)
and docs `97bee79`.

Create and push:

`feat/ask-to-add-thin`

Do not merge. Open a PR after the gates below are green.

## Why this exists

What Now Phase A returns feasible catalog candidates and stops at
`View details`. The owner field evidence needs accepted advice to become a
typed, confirmed command. Current `EventType.ADD_ACTIVITY` apply is not that
command: it venue-searches, inserts after a target using the previous node's
start and a hardcoded 90-minute dwell, and does not re-check
`fits_next_lock`. Ask confirm of a bare `add_activity` proposal can therefore
insert a lottery venue. This slice closes that hole for the What Now path
and refuses identity-less adds.

## Current production seams to reuse

- `POST /api/v1/trip/event` with `event_type=add_activity`
- `TripEventRequest.preferences` for the typed add payload
- `WhatNowCandidate.venue_id` and `scheduled_start`
- `services/booking_constraints.fits_next_lock`
- SPEC-41 hours and walking helpers already used by What Now / swap
- `ChatScreen._confirmAskProposal` and `WhatNowBubble`
- `TripEventService.sendEvent(..., preferences: ...)`

Do not create a second planner, a second chat, a WebSocket, a new table, or
a catalog write. Do not add a Flutter command-queue outbox (SPEC-44 later).

## Scope

### 1. Typed add payload

Confirmed add must identify exactly one catalog venue. Wire shape:

```json
{
  "mode": "ask_to_add",
  "venue_id": "v1",
  "candidate_id": "what_now:v1"
}
```

Rules:

- `mode` must be `ask_to_add`
- `venue_id` is required and must exist in the active trip region catalog
- `candidate_id` is optional; if present it is ignored for ranking and used
  only as a trace of which What Now card was confirmed
- unknown extra keys on the outer preferences object may be ignored
- invalid `mode` or missing/blank `venue_id` is a request error or a typed
  refusal, not a venue_search fallback

Do not accept free-text place names in this slice. Do not invent coordinates.

### 2. Apply-time feasibility (production predicates)

On `add_activity` with `preferences.mode=ask_to_add`:

1. Load the venue by `venue_id`. Wrong or missing id -> refuse, no write.
2. Venue `geo_region` must match the trip / context region. Cross-region
   refuse.
3. Exclude infrastructure venues with the same production helper What Now
   uses.
4. If `venue_id` is already on the active itinerary -> refuse duplicate.
5. Resolve planned start:
   - prefer the What Now candidate `scheduled_start` when the client sends
     it as `scheduled_start` (ISO destination-local or UTC, same convention
     as existing nodes);
   - otherwise place the node after the current/next movable stop on the
     same local day using that stop's end, not its start;
   - never copy another node's start as the new node's start.
6. Duration is canonical `typical_dwell_minutes` when present; if dwell is
   unknown, refuse rather than hardcoding 90.
7. Known structured hours must fit the planned start plus dwell.
8. `fits_next_lock` must pass (hotel skip, same region/day, flight cutoff,
   walking arrival). Reuse the shared helper. Do not copy a weaker check.
9. Walking time is computed only when both endpoints have finite
   coordinates. Missing walk cannot claim reachability.

On any failed predicate: itinerary unchanged, typed honest refusal, no
partial node.

On success: insert **one** new `TripNode` with a new `node_id`. Do not
replace an existing node. Do not change any other node's start, duration,
slot_name, venue, lock, or outcome.

`ADD_ACTIVITY` remains a structural event and still consumes reroute quota
like swap/cancel. Do not add a quota bypass.

### 3. Close the lottery add

If `event_type=add_activity` arrives **without** `preferences.mode=ask_to_add`
and a valid `venue_id`:

- do not call venue_search to pick a stand-in
- do not insert using the current `state_machine` 90-minute after-target
  path
- return a bounded refusal: the client must confirm a specific catalog
  venue (What Now Add to plan)

Existing tests that expect keyword `insert` -> `PLAN_CHANGE` / proposal
`add_activity` may keep the **proposal**. Confirming that proposal without
a venue_id must not mutate. Update those tests if they currently imply a
write.

### 4. Flutter: live What Now Add to plan

On a **live** What Now card (not history):

- keep `View details`
- add `Add to plan` (`Key('what_now_add_${venueId}')`)
- tap opens an explicit confirm dialog (venue name + planned time/dwell
  when known)
- confirm sends **one** `add_activity` via existing `sendEvent` with
  `preferences` `{mode: ask_to_add, venue_id, candidate_id, scheduled_start?}`
- cancel sends nothing
- offline: existing live-Ask-unavailable refusal; do not enqueue; do not
  write a fabricated node locally

History-loaded What Now cards stay display-only: no Add, no details
mutation, no `sendEvent`.

After a successful add, the itinerary provider must show the new node.
Do not silently reflow other cards.

Capture Riverpod locals before awaits in any new async ChatScreen path
(same lesson as `_sendWhatNow` on `d1df944`). Do not use `pumpAndSettle`.
After widget tests that persist SQLite, drain FFI before
`container.dispose()`.

### 5. Tests

Backend, new file `tests/test_ask_to_add.py` (name may vary, keep focused):

- Vientiane `venue_id` adds one node in Vientiane, never Dubai
- duplicate `venue_id` refuses; node count unchanged
- missing `venue_id` / missing mode refuses; no venue_search insert
- unknown dwell refuses (no hardcoded 90)
- next locked flight/hotel remains reachable; sabotage
  `fits_next_lock` walk omission must fail the named lock test (R17)
- other nodes' `node_id` and `scheduled_start` unchanged
- infrastructure venue_id refuses
- cross-region venue_id refuses
- zero `llm.complete` calls

Flutter widget tests in a focused file next to `spec46_what_now_test.dart`:

- live card shows Add to plan
- confirm sends one `add_activity` with exact preferences
- cancel sends nothing
- history card has no Add to plan
- offline confirm refuses and enqueues nothing
- View details still does not mutate

Reuse the SPEC-46 harness: unique in-memory `OfflineDatabase(testPath:)`,
`tester.runAsync`, `_flushFfi`, no `pumpAndSettle`, no `physicalSize` hacks.

Contract tests: Dart/Pydantic preferences round-trip if you add a typed
model. Closed enums only.

### 6. R17 sabotage

1. Temporarily drop the walking term from add-time `fits_next_lock`.
2. Run the named next-lock test.
3. Confirm that exact test fails.
4. Restore.
5. Re-run the focused file green.

Report the test name that failed. A generally red file is not the proof.

## Non-goals

- empty-day itinerary `Add activity` chrome (rest of SPEC-42)
- Move / later today / lunch-to-dinner editor
- uncatalogued / trip-private nodes (immediate follow-up, not this PR)
- shared catalog writes or SPEC-17/47 review promotion
- silent day reflow or swap-in-place
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
flutter test test/spec46_what_now_test.dart
flutter test test/spec25_durable_threads_widget_test.dart
# plus the new Ask-to-Add widget file
flutter test
```

After any Dart edit, R1:

```bash
grep -rn '\\$' mobile/lib
```

Only the two price strings in `upgrade_screen.dart` may match.

Force-push this feature branch as needed. Do not `git pull` after a force
push; fetch and `reset --hard` to origin. No APK. No deploy. One PR.
Do not merge.
