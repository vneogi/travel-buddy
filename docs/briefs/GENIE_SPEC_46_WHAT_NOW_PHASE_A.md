# Genie brief: SPEC-46 What Now Phase A

Landed on `main` as `d1df944` (PR #73). Do not re-implement this slice.
Phase B GPS is a later spec after SPEC-43.

## Goal

Build the first deterministic, no-GPS What Now mode inside the existing
trip-scoped Ask surface.

The traveller supplies temporary context, receives a short structured list of
feasible catalog candidates, and can inspect why each candidate fits. This is
not a generic chat answer and it does not mutate the itinerary.

Read before editing:

- `docs/specs/SPEC-46-what-now-foreground-context.md`
- `docs/specs/SPEC-25-ask-anything.md`
- `docs/ENGINEERING_RULES.md`
- `docs/WAYS_OF_WORKING.md`

Base branch: latest `main`, including merge commit `7d825c0`.

Create and push:

`feat/spec46-phase-a-what-now`

Do not merge. Open a PR after the gates below are green.

## Current production seams to reuse

- `POST /api/v1/trip/event` with `event_type=ask_info`
- `TripEventRequest.preferences` for structured temporary request context
- `services/ask_service.py` for closed Ask intents and deterministic retrieval
- `agents/state_machine.py` for current/next trip context and SPEC-41
  reachability helpers
- `services/opening_hours.py`, `services/transit.py`,
  `services/booking_constraints.py`, and existing scheduler predicates
- `ChatScreen` and its durable SQLite thread from SPEC-25 Phase C
- `AskResponseEnvelope` and the Dart `AskResponse` model

Do not create a second chat screen, a second planner, a WebSocket path, or a
new persistence table.

## Scope

### 1. Closed request context

Add a typed What Now request model. The wire shape is:

```json
{
  "mode": "what_now",
  "available_minutes": 45,
  "energy": "low",
  "walking": "short",
  "intent": "quiet",
  "context_node_id": "optional-node-id"
}
```

Allowed values:

- `available_minutes`: `45`, `90`, or `120`
- `energy`: `low`, `normal`, or `high`
- `walking`: `short`, `normal`, or `longer`
- `intent`: `quiet`, `food`, `indoors`, `culture`, or `anything`
- `context_node_id`: optional node from the active trip

Use Pydantic validation. Unknown keys may be ignored by the outer legacy
preferences object, but an invalid What Now field must produce a bounded
refusal or request-validation error. Do not silently coerce an unsupported
duration or enum.

The context is request-scoped. Do not write energy, walking, intent, or a
derived location into trip state, user preferences, signals, Ask telemetry,
cache keys, or SQLite columns.

### 2. Closed Ask intent and response contract

Add `what_now` to:

- backend `AskIntent`
- `AskResponseEnvelope.intent`
- Dart `AskResponseIntent`

Extend the Ask envelope with an optional structured result:

```text
what_now:
  location_source
  context_label
  candidates[]
```

Each candidate contains:

```text
candidate_id
venue_id
name
micro_location_display
category
typical_dwell_minutes
scheduled_start
reason_codes[]
unknown_fields[]
```

Use JSON field names from SPEC-46. Keep `answer` as short deterministic
summary/refusal copy so old clients remain safe. The structured list is the
source of truth for the new widget.

No candidate carries a mutation proposal in this slice. The primary action is
`View details`. Thin Ask-to-Add and polished Move are later slices. This
prevents What Now Phase A from inventing an add/move contract while still
proving retrieval, feasibility, reasons, rendering, and durable history.

`AskResponse.toJson()` and `fromJson()` must round-trip the structured result
so reopened device-local threads render the same cards without a network call.

### 3. Deterministic context source

Resolve location source in this order:

1. `context_node_id` when it belongs to this trip and has a usable region
2. current actionable node or most recently completed node
3. current/next trip node
4. active trip region anchor for city browsing only

For node-based context:

- `location_source = "trip_position"`
- visible label: `Using your trip position`

For region-anchor fallback:

- `location_source = "region_anchor"`
- visible label: `Browsing in <city>`
- never emit distance, walking duration, `near you`, or
  `short_walk_from_context`

There is no device permission, GPS request, foreground coordinate, background
watcher, geofence, or raw-coordinate persistence in Phase A.

### 4. Candidate retrieval and feasibility

Retrieve only catalog venues in the active context region.

Exclude:

- venues outside that region
- infrastructure candidates
- the context venue
- venue IDs already present in the active itinerary
- malformed or missing IDs

Map the request intent to existing catalog categories. Keep this mapping
closed and tested. Do not infer a new category with an LLM.

Return at most five candidates. Three valid candidates is a good result; fewer
is an honest result. Do not pad with infeasible or cross-region venues.

For every candidate:

1. use canonical typical dwell when present;
2. compute deterministic walking time only when both endpoints have finite
   coordinates and the context is node-based;
3. require `dwell + walking <= available_minutes`;
4. require known structured hours to fit the proposed slot;
5. preserve the next locked flight, train, tour, and hotel-return boundary;
6. apply temporary energy/walking/intent filters;
7. rank the feasible set deterministically.

Reuse or extract production predicates. Do not copy a weaker approximation
into `ask_service.py`. If a SPEC-41 predicate currently lives as a private
state-machine helper, extract a shared pure helper and keep existing callers
on that helper.

An unknown required feasibility input is not permission to assert a fit:

- unknown coordinates cannot earn a walking reason;
- unknown hours cannot earn an open reason;
- unknown dwell cannot earn a time-window reason;
- region anchor cannot earn any proximity reason.

The candidate may still appear only when the remaining predicates can support
it honestly and the missing values are named in `unknown_fields`.

### 5. Reason registry

For this slice, support only reason codes whose production predicates are
implemented:

- `fits_available_window`
- `open_for_planned_time`
- `keeps_next_booking_reachable`
- `matches_requested_type`
- `matches_trip_interest`
- `same_neighbourhood`
- `short_walk_from_context`
- `lower_typical_dwell`
- `indoor_option`

It is acceptable to ship a strict subset. It is not acceptable to emit a code
without its predicate.

Each displayed reason must be derived from the same boolean used to admit or
rank the candidate. Do not reconstruct reasons from prose or category labels
after selection.

Allowed unknown fields for Phase A:

- `price`
- `live_crowds`
- `traffic`
- `opening_hours`
- `walking_time`
- `typical_dwell`

Do not emit `cheaper`, `quieter now`, `faster`, `hidden gem`, `locals prefer`,
weather-safe, or live traffic/crowd claims.

### 6. Backend integration

Route `ask_info` with `preferences.mode == "what_now"` directly to the
deterministic What Now handler. Do not depend on keyword classification alone.

Pass the full trip nodes and a testable `now_utc` into the handler. Preserve
destination-local date/time behavior.

Response paths:

- feasible candidates: `grounded_deterministic`, tier `hedge`
- no feasible candidates: `retrieval_miss`, tier `refuse`, with bounded copy
- malformed/foreign context node: bounded refusal; never fall back to another
  trip or region

Do not call `llm.complete`, consume an LLM budget, use semantic similarity,
or cache private trip-position results in the public Ask cache.

### 7. Flutter entry and sheet

Inside `ChatScreen`, add a visible `What now?` affordance above the composer.
It opens a compact sheet with:

- available time chips: `45 min`, `90 min`, `2 hours`
- energy chips: `Low`, `Normal`, `High`
- walking chips: `Short`, `Normal`, `Longer`
- optional intent chips: `Quiet`, `Food`, `Indoors`, `Culture`, `Anything`
- context label, defaulted from the itinerary
- one submit action: `Find options`

Defaults:

- 90 minutes
- normal energy
- normal walking
- anything

Submitting sends one `ask_info` request through the existing
`TripEventService.sendEvent`, with `message = "What now?"` and the typed
preferences above. The user question and structured answer persist in the
current durable thread.

Render a `WhatNowBubble` (or equivalently named widget) for the structured
result:

- context label
- candidate name and micro-location
- dwell when known
- reason chips from a closed copy registry
- explicit unknowns
- `View details`

`View details` may open the existing place-detail surface if a safe route
already exists. If not, render the candidate detail inline. Do not invent a
new mutation action.

History-loaded What Now cards are display-only and perform no network call.

Offline submit:

- show the existing live-Ask-unavailable refusal;
- do not enqueue;
- do not persist a fabricated assistant candidate list.

### 8. Tests

Add focused backend tests, for example
`tests/test_spec46_what_now.py`, covering:

- Vientiane context never returns Dubai or another Laos city
- infrastructure and itinerary venue IDs are excluded
- 90-minute window rejects dwell plus walking over 90
- known-closed candidate is excluded
- next locked booking and hotel return remain reachable
- region anchor emits no distance/walking claim
- invalid or foreign `context_node_id` refuses
- missing coordinates cannot emit `short_walk_from_context`
- every emitted reason code has a true production predicate
- no feasible candidate returns `retrieval_miss`
- What Now makes zero `llm.complete` calls and does not consume Ask budget
- request context is absent from telemetry and public cache keys

Add model/contract tests:

- Pydantic envelope includes the structured result
- Dart parses and serializes every new enum/field
- unknown intent/reason remains closed and fails safely

Add Flutter widget tests:

- entry opens the sheet
- defaults and chip changes produce the exact preferences payload
- one submit causes one `ask_info`
- candidate cards render reasons and unknowns
- region-anchor result never renders `near you` or distance
- history round-trip renders cards without `sendEvent`
- `View details` causes no itinerary mutation
- offline submit refuses and enqueues nothing

Use real SQLite for the durable history round-trip. Follow the existing
`tester.runAsync` and unique in-memory database pattern. Do not use
`pumpAndSettle` while a repeating animation is present.

### 9. R17 sabotage proof

Before claiming the guard:

1. Temporarily weaken the available-window predicate from
   `dwell + walking <= available_minutes` to `dwell <= available_minutes`.
2. Run the named over-window test.
3. Confirm that exact test fails.
4. Restore the production predicate.
5. Re-run the focused file green.

Also temporarily force `short_walk_from_context` true for a candidate with
missing coordinates. Confirm the named missing-coordinate reason test fails,
then restore it.

Report the exact test names observed failing. A generally red test file is not
the sabotage proof.

## Non-goals

- device GPS or location permission
- background location
- raw coordinate persistence
- production LLM or model phrasing
- trip-less Ask
- Ask-to-Add, Move, or silent reflow
- live traffic, crowds, weather, price, or fare claims
- new city data
- new database migration
- hosted deploy, APK, or non-owner distribution
- fixing the known `postgres-proof` apt installation baseline

## Gates

Run:

```bash
ruff check .
ruff format --check .
pytest -q -ra --strict-markers
git diff --check
```

Also run Flutter:

```bash
cd mobile
flutter analyze --no-fatal-infos
flutter test test/spec46_what_now_test.dart
flutter test test/spec25_durable_threads_widget_test.dart
flutter test
```

If Flutter is unavailable, say so explicitly and stop short of claiming it
green. The owner will run the Windows Flutter gates.

After any Dart edit, run the R1 interpolation scan described in
`docs/ENGINEERING_RULES.md`.

No APK. No deploy. One PR. Do not merge.
