# Genie brief: SPEC-42 trip-private uncatalogued Add

## Goal

Let the traveller put a place that is not in the catalog onto an empty
date and named slot as a trip-private node, after explicit confirmation.

One command inserts one node. Existing nodes keep their `node_id`, start,
slot, venue, lock, loved state, and outcome. Nothing else is reflowed.
The shared catalog is not written. Other trips and other travellers never
see this place.

This is the remaining SPEC-42 empty-day remainder after catalog
`direct_add`. It is not What Now Ask-to-Add, Move, swap, OSM persist,
free-text search, or Add on a populated date.

Read before editing:

- `docs/specs/SPEC-42-flexible-trip-span.md`
- `docs/briefs/GENIE_SPEC_42_EMPTY_DAY_ADD.md`
- `docs/ENGINEERING_RULES.md`
- `docs/WAYS_OF_WORKING.md`

Base branch: latest `main`, including empty-day catalog Add `b6ddecf`
(PR #76).

Create and push:

`feat/spec42-uncatalogued-add`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Field use added locally discovered places that the catalog did not have.
Empty-day catalog Add can only insert a `venues_rag` row. Typing a name
into that path would either fail or pollute the shared catalog.

SPEC-42 already says an uncatalogued place may become a trip-private node
after confirmation, with the minimum identity and source needed to render
it honestly. It does not enter ranking or another traveller's results
until SPEC-17/47 review exists. That review is not this slice.

## Current production seams to reuse

- `POST /api/v1/trip/event` with `event_type=add_activity`
- `TripEventRequest.preferences`
- `services.day_slots.SLOT_ORDER`
- empty-day region resolution in `services/direct_add_service.py`
  (trip region, or the unique containing corridor segment)
- occupancy, previous-walk + slot floor, `fits_next_lock`
- `services.transit.walking_minutes`
- Flutter `DirectAddSheet` (`direct_add_sheet_v1`) and
  `empty_day_add_YYYY-MM-DD`
- `ItineraryController.applyEvent`

Do not create a second planner, chat, WebSocket, table, catalog write, or
Flutter command outbox. Do not call `hybrid_venue_search` or
`list_venues_for_region` to invent a venue. Do not reuse `_make_node`
from a catalog row.

## Scope

### 1. Typed uncatalogued payload

Keep closed `EventType.ADD_ACTIVITY`. Add a third typed mode. Do not
overload `direct_add` or `ask_to_add`.

```json
{
  "event_type": "add_activity",
  "preferences": {
    "mode": "uncatalogued_add",
    "name": "Papao viewpoint",
    "target_date": "2026-10-13",
    "target_slot": "afternoon_evening_tour",
    "typical_dwell_minutes": 60,
    "micro_location": "east bank",
    "lat": 19.888,
    "lng": 102.135
  }
}
```

Rules:

- `mode` must be exactly `uncatalogued_add`
- `name` is required, trimmed, 2 to 80 characters, not a catalog `venue_id`
- `target_date` is required `YYYY-MM-DD` inside the inclusive trip span
- `target_slot` is required and must be one of `SLOT_ORDER`
- `typical_dwell_minutes` is required, finite, integer, 15 to 240 inclusive.
  Never fill missing dwell with 90.
- `micro_location` optional trimmed text
- `lat`/`lng` optional; both present and finite, or both absent
- client timestamps are ignored; the server computes start from slot floor
  plus previous dwell/walk, same as catalog direct-add
- unknown extra keys may be ignored
- `ask_to_add` and `direct_add` stay unchanged
- bare `add_activity` still refuses

### 2. Trip-private node, not a catalog row

On success, insert exactly one new `TripNode`:

- new `node_id`
- `venue_name` = trimmed name
- `venue_id` is null (do not mint a fake catalog UUID)
- `slot_name` = requested slot
- `duration_minutes` = the posted dwell
- `geo_region` = the date's resolved region
- `lat`/`lng` only when posted
- `micro_location` only when posted
- `opening_hours` / `opening_hours_structured` stay null
- `place_source` (or equivalent existing optional field) = `trip_private`.
  Existing nodes without the field deserialize as catalog. Prefer an
  optional TripNode field with default `catalog` so old cached trips load.
- `is_locked` false, `node_kind` activity

Persist only through the existing trip write. Assert:

- no insert/update/upsert into `venues_rag`, `venue_dish`,
  `venue_external_id`, or taxonomy tables
- the place is not returned by `list_venues_for_region` or
  `hybrid_venue_search` after confirm
- another trip listing the same region does not see this name as a
  catalog venue

If a normalized name matches a catalog venue in that region, refuse with
typed copy that the traveller should pick it from the catalog list.
Do not silently attach catalog identity.

### 3. Shared feasibility without claiming catalog facts

Reuse empty-day region, occupancy, previous-walk slot floor, and
`fits_next_lock`. Differences from `direct_add`:

- no `venue_fits_slot` category check (there is no catalog category)
- no structured-hours check; unknown hours must not claim "open"
- missing/non-finite coordinates refuse with `reachability` when a
  neighbour transfer is required (same honesty as catalog Add)
- a true empty day with no neighbours may omit coordinates
- duplicate: same date + slot already occupied, or the same normalized
  name already on that local date

Start time is server-computed. Do not invent opening windows.

### 4. HTTP / quota

Same 422-before-persist pattern as `direct_add`:

- success: one new node, one reroute consumed, version +1
- refusal: 422 `uncatalogued_add_refused` with `code` and traveller copy;
  trip, version, and quota unchanged
- payload errors (`invalid_mode`, `invalid_slot`, `invalid_name`,
  `invalid_dwell`) also 422 before persist
- top-level `process_event` contract stays `updated_trip_state`
- zero `llm.complete`, zero `hybrid_venue_search`, zero catalog writes

Do not add a listing endpoint. Uncatalogued Add is confirm-only.

### 5. Flutter

Reuse the empty-day `Add activity` button and `direct_add_sheet_v1`.
Do not add a second empty-day button.

After slot selection:

- keep the existing catalog candidate / refusal / retry UI
- add a keyed action `uncatalogued_add_open` labelled for a place not
  in the catalog
- that path shows a name field, required dwell chips (15/30/45/60/90/120
  minutes, traveller-stated stay, not catalog typical dwell), optional
  micro-location, and explicit confirm/cancel
- confirm copy states the name, date, slot, dwell, and that this place
  is only on this trip
- confirm sends one `add_activity` with the exact `uncatalogued_add`
  preferences (no `venue_id`, no client timestamp)
- cancel sends nothing
- offline tap of empty-day Add still uses the existing offline banner;
  no sheet, no queue, no send
- populated dates still have no Add button

Render the new node with the posted name. Do not invent hours. A short
honest "Added by you" (or equivalent) is enough. Do not open a map picker
in this slice.

Capture Riverpod locals before awaits. Same harness rules as
`spec42_direct_add_test.dart`: unique in-memory `OfflineDatabase`,
`tester.runAsync`, `_flushFfi`, no `pumpAndSettle`, no `physicalSize`,
`_settle` after sheet close.

### 6. Tests

Backend, focused file `tests/test_spec42_uncatalogued_add.py`:

- success on an empty Vientiane date inserts one node, null `venue_id`,
  trip-private source, posted dwell, server start, old nodes unchanged
- corridor date uses the containing segment region
- catalog `venues_rag` (or in-memory venue list) is unchanged after success
- matching catalog name in-region refuses; no write
- occupied slot, invalid date/slot/name/dwell, missing dwell refuse
  with no write/quota/version change
- missing coords with a previous neighbour requiring a walk refuse
  `reachability`; true empty day without neighbours may omit coords
- `direct_add` and `ask_to_add` still dispatch; bare add still refuses
- zero LLM, zero venue search, zero catalog upsert
- top-level contract uses `updated_trip_state`

Flutter, focused file `mobile/test/spec42_uncatalogued_add_test.dart`:

- uncatalogued action is reachable from the empty-day sheet
- confirm sends one `add_activity` with exact `uncatalogued_add`
  preferences (name, date, slot, dwell; no venue_id)
- cancel sends nothing
- server 422 leaves the date empty and shows the message
- offline empty-day tap still opens nothing and queues nothing
- existing catalog `direct_add` confirm still works

Regression files:

- `mobile/test/spec42_direct_add_test.dart`
- `mobile/test/spec42_move_test.dart`
- `mobile/test/spec_ask_to_add_test.dart`

### 7. R17 sabotage

1. Temporarily allow confirm to upsert the posted name into the venue
   list / `venues_rag` write path.
2. Run the named test that asserts the catalog is unchanged after success.
3. Confirm that exact test fails.
4. Restore.
5. Re-run the focused file green.

Report the test name that failed. A generally red file is not proof.

## Non-goals

- catalog writes or provisional venues_rag rows
- SPEC-18 OSM/Wikidata persist
- SPEC-17/47 review promotion into the shared catalog
- ranking signals that affect other trips
- map picker, GPS, or free-text geocoding
- Add buttons on populated days
- unknown-time whole-day excursions
- Move, swap, Ask NLQ, `PlanChangeProposal`
- new migration if an optional TripNode field plus state_json is enough
- offline command queue
- hosted deploy, APK, non-owner distribution
- fixing `postgres-proof` apt baseline
- the catalog `direct_add` `_make_node` missing-lat crash remainder

## Gates

```bash
ruff check .
ruff format --check .
pytest -q -ra --strict-markers
git diff --check
```

Flutter (say so if the SDK is absent; do not claim it green):

```bash
flutter analyze --no-fatal-infos
flutter test test/spec42_uncatalogued_add_test.dart
flutter test test/spec42_direct_add_test.dart test/spec42_move_test.dart test/spec_ask_to_add_test.dart
```

R1: after any Dart write, `grep -rn '\\$' mobile/lib` must still show
only the two `upgrade_screen.dart` price strings.
