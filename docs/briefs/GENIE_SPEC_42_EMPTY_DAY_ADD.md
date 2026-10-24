# Genie brief: SPEC-42 empty-day catalog Add

Landed on `main` as `b6ddecf` (PR #76). Do not re-implement this slice.
Trip-private uncatalogued Add landed as `05d917e` (PR #77).

## Goal

Turn an intentionally empty itinerary date into a useful day by letting the
traveller choose a named slot, select one server-approved catalog venue, and
explicitly confirm one new node.

One command inserts one node. Existing nodes keep their `node_id`, start,
slot, venue, lock, loved state, and outcome. Nothing else is reflowed.

This is the remaining SPEC-42 empty-day `Add activity` chrome. It is not
What Now Ask-to-Add, Move, swap, free-text place search, or uncatalogued
trip-private place capture.

Read before editing:

- `docs/specs/SPEC-42-flexible-trip-span.md`
- `docs/specs/SPEC-41-hours-aware-scheduling.md`
- `docs/briefs/GENIE_ASK_TO_ADD_THIN.md`
- `docs/briefs/GENIE_SPEC_42_MOVE_THIN.md`
- `docs/ENGINEERING_RULES.md`
- `docs/WAYS_OF_WORKING.md`

Base branch: latest `main`, including thin typed Move `e51513e` (PR #75)
and docs `654cb9d`.

Create and push:

`feat/spec42-empty-day-add`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

SPEC-42 already renders every date in the trip span, but an empty date still
shows only `Open day`. Ask-to-Add can confirm a What Now candidate, but it
does not start from a chosen itinerary date/slot. Bare `add_activity` is
correctly refused to prevent venue lottery.

This slice closes the catalog-backed empty-day loop without reopening the
unsafe legacy add path.

## Current production seams to reuse

- `POST /api/v1/trip/event` with `event_type=add_activity`
- `TripEventRequest.preferences`
- `services.day_slots.SLOT_ORDER` and `venue_fits_slot`
- `services.catalog_itinerary._slot_floor_utc`,
  `_slot_accepts_start`, existing deterministic interest scoring, and
  infrastructure exclusion
- `services.opening_hours.next_slot_start` / `hours_for_slot`
- `services.booking_constraints.fits_next_lock`
- `services.transit.walking_minutes`
- `db_service.list_venues_for_region` (both in-memory and Supabase)
- SPEC-42 `creation_context` / corridor segments for date-to-region
- Flutter `ItineraryController.applyEvent`, `_EmptyDayCard`, and
  `VenueSearchResult` presentation conventions

Do not create a second planner, chat, WebSocket, table, catalog write, or
Flutter command outbox. Do not call `hybrid_venue_search`: the date/slot and
trip region already define a deterministic catalog candidate set.

## Scope

### 1. Typed direct-add payload

Keep the existing closed `EventType.ADD_ACTIVITY`. Add a second typed mode:

```json
{
  "event_type": "add_activity",
  "preferences": {
    "mode": "direct_add",
    "venue_id": "v1",
    "target_date": "2026-10-13",
    "target_slot": "dinner"
  }
}
```

Rules:

- `mode` must be `direct_add`
- `venue_id` is required and must identify one catalog venue
- `target_date` is required `YYYY-MM-DD` in the destination-local calendar
- `target_slot` is required and must be one of `SLOT_ORDER`
- unknown extra preference keys may be ignored
- invalid or incomplete payload -> typed refusal / 422, never venue search

Preserve the current modes exactly:

- `mode=ask_to_add` keeps its What Now behavior
- bare or unknown-mode `add_activity` remains refused

Do not add a new event enum and do not accept free-text venue names.

### 2. Shared candidate evaluator

Create one direct-add service used by **both** candidate listing and confirm
apply. Candidate listing must not be a weaker preview.

Inputs:

- trip
- `target_date`
- `target_slot`
- optional exact `venue_id` for apply
- catalog rows from `list_venues_for_region`

Resolve the target region first:

- single-city trip: `trip.geo_region`
- corridor: exactly one stored segment must contain `target_date`; use that
  segment's `geo_region`
- date must be inside the inclusive creation/segment span
- no containing segment or overlapping ambiguous segments -> refuse

For every candidate, apply these predicates in order:

1. Stable nonblank `venue_id`; venue region equals target region.
2. Exclude infrastructure with the existing shared helper.
3. Exclude a `venue_id` already on the itinerary.
4. Slot type passes `venue_fits_slot`; whole-day excursions are out of this
   slice.
5. Canonical `typical_dwell_minutes` is present and valid. Missing dwell is
   ineligible; do not use the legacy/default 90 minutes.
6. Target slot is not already occupied by another flexible node on that
   local date. Apply must re-check this after selection.
7. Resolve the earliest start from the destination-local slot floor. If a
   previous non-hotel node is on that date, add its dwell plus walking time.
   Then use `next_slot_start` and require `_slot_accepts_start`.
8. Known structured hours must fit start plus canonical dwell.
9. Previous/next non-hotel neighbour reachability must pass. When a transfer
   is required, missing/non-finite coordinates on either endpoint make the
   candidate ineligible; missing walk cannot claim reachability.
10. The next locked non-hotel must pass shared `fits_next_lock` (including
    canonical flight cutoff). Do not copy a weaker lock check.

Hotels remain background anchors under the existing lock helper. No candidate
may move, replace, or re-time another node.

Candidate ordering is deterministic:

1. existing catalog interest score using
   `creation_context.interest_ids` (highest first)
2. destination-local planned start
3. normalized venue name
4. `venue_id`

Return at most five. Same trip/catalog/date/slot produces the same IDs and
order. Zero LLM calls.

### 3. Candidate endpoint

Add an authenticated owner-only endpoint:

```text
GET /api/v1/trip/{trip_id}/add_candidates
    ?target_date=2026-10-13
    &target_slot=dinner
```

Response:

```json
{
  "target_date": "2026-10-13",
  "target_slot": "dinner",
  "geo_region": "vientiane_laos",
  "candidates": [
    {
      "venue_id": "v1",
      "name": "Example",
      "category": "restaurant",
      "micro_location": "Riverside",
      "vibe_tags": ["local"],
      "planned_start": "2026-10-13T17:00:00+07:00",
      "typical_dwell_minutes": 60
    }
  ],
  "refusal_code": null,
  "refusal_copy": null
}
```

Use a closed response DTO in Python and Dart. When no candidate fits, return
an empty list plus bounded `refusal_code` / honest copy (`no_catalog`,
`duplicate`, `hours`, `reachability`, `occupied`, or `invalid_date`).
Do not return a random fallback.

The endpoint is read-only: no reroute quota, persistence, version bump,
command record, signal, or model call.

### 4. Apply direct add

On `add_activity` + `preferences.mode=direct_add`:

1. Run the exact shared evaluator against the requested `venue_id`.
2. Recompute planned start server-side. Do not trust a client timestamp.
3. If any predicate now fails, return typed 422 `direct_add_refused` before
   persistence. Trip/version/quota remain unchanged.
4. On success, insert exactly one new flexible `TripNode`:
   - new `node_id`
   - requested catalog identity and target region
   - server-computed `scheduled_start`
   - requested `slot_name`
   - canonical dwell, hours, coordinates, location, and vibe fields
   - pending, unlocked, `node_kind=activity`
5. Preserve every existing node byte-for-byte apart from response ordering.

Successful direct Add is structural and consumes one reroute exactly like
successful Ask-to-Add. A failed direct Add consumes none.

Return the real `process_event` contract:
`updated_trip_state`, `response`, `routing_tier_used`, `from_cache`,
`venues_found`, and `schedule_warnings`.

### 5. Flutter empty-day flow

Carry each empty date through `_TimelineItem` into `_EmptyDayCard`; do not
infer it from the clock.

For an empty date render:

- intentional-open copy
- `Add activity` button:
  `Key('empty_day_add_YYYY-MM-DD')`

No `Add activity` button appears in a populated date section in this slice.

Tap behavior:

1. If offline, show the existing unavailable/retry banner. Do not open a
   network-backed sheet, enqueue, or mutate local nodes.
2. Open `Key('direct_add_sheet_v1')`.
3. Show the four named slot chips:
   `direct_add_slot_<slot>`.
4. After slot selection, call `add_candidates` with the exact date/slot.
5. Render loading, typed empty/refusal, retry, and candidate states.
6. Candidate keys: `direct_add_candidate_<venueId>`.
7. Selecting a candidate shows venue, date, slot, planned local time, and
   dwell. Confirm is explicit:
   - `Key('direct_add_confirm')`
   - `Key('direct_add_cancel')`
8. Confirm sends one existing `EventType.addActivity` with exact
   `direct_add` preferences. Cancel sends nothing.

After success, the previously empty date renders the new card and named slot.
No other card changes.

Reuse visual pieces where practical, but do not reuse `SwapSheet` semantics
or call `/venues/search`. Keep the 280px chat bubble unrelated.

Capture Riverpod locals before awaits. Do not use `pumpAndSettle`. Sheet
open/close uses `pump()` plus a timed pump. Use `ensureVisible` / `_tapKey`;
do not set `physicalSize`. Drain SQLite FFI before disposing test containers.

### 6. Tests

Backend, focused file `tests/test_spec42_direct_add.py`:

- candidate endpoint resolves an empty Vientiane date and returns at most five
  deterministic slot-typed candidates
- corridor date uses its segment region (Luang Prabang never returns
  Vientiane/Dubai)
- infrastructure, duplicates, unknown dwell, wrong slot type, known-closed,
  and unreachable candidates are excluded
- missing coordinates refuse when a neighbour transfer is required
- no-fit response has typed refusal copy and performs no write/quota change
- each listed candidate succeeds on confirm against the unchanged trip
  (search/apply parity)
- success adds one node with new ID, exact date/slot, canonical dwell, and
  leaves all old nodes unchanged
- stale occupied slot at confirm -> 422, no write/version/quota change
- invalid date/slot/mode/venue and ambiguous corridor date refuse
- `ask_to_add` still works; bare `add_activity` still refuses
- zero `llm.complete` and zero `hybrid_venue_search` calls
- both in-memory and Supabase venue-list seams use the same pure evaluator
- top-level `process_event` contract uses `updated_trip_state`

Flutter, focused file `mobile/test/spec42_direct_add_test.dart`:

- empty date renders keyed Add activity; populated date does not
- slot selection calls candidate endpoint with exact date/slot
- typed empty result displays server refusal copy
- confirm sends one `add_activity` with exact `direct_add` preferences
- cancel sends nothing
- server refusal leaves the date empty and shows its message
- offline tap queues/sends nothing and shows existing offline copy

Regression files:

- `mobile/test/spec42_move_test.dart`
- `mobile/test/spec_ask_to_add_test.dart`
- `mobile/test/spec46_what_now_test.dart`
- SPEC-42 sparse-span rendering tests

Use unique in-memory `OfflineDatabase(testPath:)`, `tester.runAsync`,
`_flushFfi`, no `pumpAndSettle`, and no `physicalSize` hacks.

### 7. R17 sabotage

1. Temporarily remove previous-neighbour walking time from the shared
   direct-add evaluator.
2. Run the named test
   `test_previous_walk_pushes_candidate_out_of_slot`.
3. Confirm that exact test fails.
4. Restore.
5. Re-run the focused file green.

Report the test name that failed. A generally red file is not proof.

## Non-goals

- uncatalogued / trip-private places
- free-text place search or arbitrary user-entered coordinates
- Add buttons on populated days
- more than one inserted node per confirmation
- Ask NLQ or `PlanChangeProposal` changes
- Move, swap, or silent day reflow
- whole-day excursions
- GPS, LLM, trip-less Ask
- new migration
- offline command queue
- hosted deploy, APK, non-owner distribution
- fixing `postgres-proof` apt baseline
- the recorded Move missing-coordinate remainder

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
flutter test test/spec42_direct_add_test.dart
flutter test test/spec42_move_test.dart test/spec_ask_to_add_test.dart test/spec46_what_now_test.dart
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
