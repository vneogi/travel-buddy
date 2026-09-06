# Genie Brief: SPEC-36 Laos Corridor Trip

## Read first

- `docs/WAYS_OF_WORKING.md`
- `docs/ENGINEERING_RULES.md`
- `docs/specs/SPEC-36-laos-corridor-trip.md`
- `docs/specs/SPEC-31-date-scoped-itinerary.md`
- `docs/specs/SPEC-32-real-laos-trip-creation.md`
- `docs/specs/SPEC-35-proactive-itinerary-notifications.md`

The spec is authoritative. Stop and report any contradiction before coding.
Do not edit this brief.

## Goal

Implement one complete vertical slice for `laos_northbound_v1`: create one trip
with independent date ranges for Vientiane, Vang Vieng, and Luang Prabang, then
render its existing activity cards in collapsible city/day sections.

Do not add synthetic transport, hotels, maps, OS push, background location,
meal copy, review claims, an LLM call, or a migration.

## Preflight and branch

1. `git fetch origin`
2. Confirm `origin/main` contains:
   - PR #52 / commit `1379da8`;
   - `docs/specs/SPEC-36-laos-corridor-trip.md`;
   - this brief.
3. Stop if the working tree is not clean.
4. Create `feat/spec36-laos-corridor` from `origin/main`.
5. Read the current implementations before editing. Do not reconstruct files
   from this brief.

## Required implementation

### A. One corridor registry

Add `config/corridors.py` as the sole backend registry for:

```text
corridor_id: laos_northbound_v1
display_name: Vientiane to Luang Prabang
geo_regions:
  vientiane_laos
  vang_vieng_laos
  luang_prabang_laos
max_days: 7
max_days_per_segment: 3
```

Do not mirror this list in router logic. Validation and advertisement must read
the registry. Add a drift/usage test that would fail if the router hardcodes a
different order.

### B. Typed request and state models

In `models/schemas.py`:

1. Add `TripSegmentIn` and `TripSegment` with `geo_region`, `starts_on`, and
   `ends_on`.
2. Make `CreateTripRequest.start_date` optional and add optional `segments`.
3. Add model validation for exactly one create mode:
   - single city: `start_date` and `geo_region`, no `segments`;
   - corridor: `segments`, no `start_date` or top-level `geo_region`.
4. Add optional `corridor_id` and typed `segments` to `TripState`.
5. Add optional `corridor_id` to `TripSummary` and `FeaturedTrip`.

Do not make existing stored trips fail parsing. Missing corridor fields must
default to null or an empty list.

### C. Deterministic corridor builder

Keep single-city `nodes_from_catalog` behavior unchanged.

Add corridor helpers in `services/catalog_itinerary.py` or a focused
`services/corridor_itinerary.py`:

1. Validate the exact registry order.
2. Validate inclusive ranges: one to three days each, ordered, no overlap, and
   no more than seven days total.
3. Interpret every requested date as 09:00 in the region IANA timezone and
   store UTC.
4. Select exactly four eligible catalog venues per day.
5. Preserve category-bucket diversity.
6. Exclude infrastructure, missing coordinates, missing names, and missing
   stable venue IDs.
7. Exclude all venue IDs already used in that city segment.
8. Keep the sequence deterministic.
9. Build and validate every segment before any call to `save_trip` or
   `save_trip_party`.

Raise typed internal errors that the router maps to:

- 422 `invalid_corridor` for request shape/order/date errors;
- 422 `unsupported_corridor` for catalog capacity.

Never return a partial trip ID.

### D. Create and list API

In `routers/trip_router.py`:

1. Preserve the current single-city branch and response shape.
2. Add corridor mode to POST `/api/v1/trip/create`.
3. For a corridor trip:
   - set `corridor_id = "laos_northbound_v1"`;
   - persist typed segments;
   - keep trip `geo_region` and `current_context` at the first segment;
   - set every node's actual `geo_region`;
   - set `schedule_basis = "region_local_v1"`;
   - save once only after the whole build succeeds.
4. Add `supported_corridors` to GET `/api/v1/trips`.
5. Advertise the corridor only when every member city can supply four eligible
   one-day venues.
6. Add `corridor_id` to trip and featured summaries without exposing full
   state JSON.

Existing clients that ignore `supported_corridors` must remain compatible.

### E. Normalized day indexes

In `services/itinerary_normaliser.py`, replace the constant
`day_index = 0` assignment with a pure derivation:

1. Convert each stored instant into its node region timezone.
2. Assign zero-based indexes to ordered distinct local calendar dates.
3. Preserve the existing global `seq`.
4. Keep single-day trips at zero.
5. Preserve every node's `geo_region` through decompose/compose.

Use the existing region registry as the timezone source. Do not add another
timezone dictionary.

### F. Flutter models, repository, and offline Home cache

Update:

- `mobile/lib/data/models.dart`
- `mobile/lib/data/repositories.dart`
- Home snapshot tests and repository tests

Add typed Dart models for supported corridors and trip segments. Missing
fields from old API responses or old SQLite Home snapshots must parse safely.

Add a repository corridor-create method that POSTs:

```json
{
  "segments": [
    {
      "geo_region": "vientiane_laos",
      "starts_on": "2026-10-02",
      "ends_on": "2026-10-03"
    },
    {
      "geo_region": "vang_vieng_laos",
      "starts_on": "2026-10-04",
      "ends_on": "2026-10-05"
    },
    {
      "geo_region": "luang_prabang_laos",
      "starts_on": "2026-10-06",
      "ends_on": "2026-10-08"
    }
  ]
}
```

The body must not contain `start_date`, top-level `geo_region`, a user ID, or
client-generated activities.

### G. Flutter create flow

In the Home create flow:

1. Keep current single-city create unchanged.
2. Show `Create Laos corridor` only when the server advertises it.
3. Show the three server-ordered city rows with an inclusive date range picker.
4. Start with a valid non-overlapping default, no more than seven total days.
5. Validate before submit and show a specific safe reason for overlap, wrong
   order, over-three-day segment, or over-seven-day total.
6. Disable duplicate submits and retain the current error handling.
7. Navigate to the one created trip.

Do not hardcode venue names, stops, or itinerary times in Flutter.

### H. Collapsible city/day itinerary

Update the SPEC-31 grouping and itinerary UI:

1. Keep `groupNodesByCalendarDate` unchanged as the date primitive.
2. Add a pure corridor grouping helper that follows `TripState.segments` and
   preserves input node order.
3. Render city section headers with display name, inclusive range, and chevron.
4. Render existing date headers and ActivityCards inside expanded sections.
5. Initially collapse a section only when every node in it ends before now.
6. Current and future sections start expanded.
7. A user can reopen a collapsed section without data loss.
8. Missing/unknown node regions render under `Other stops`.
9. Preserve existing ActivityCard key expressions and callbacks.

Do not add tabs, a pager, a new state-management package, or a nested scrolling
package.

### I. City-scoped targeted actions

Keep the existing target-node region behavior in `agents/state_machine.py`.
Add a regression test proving a Luang Prabang target cannot resolve a
Vientiane replacement.

Fix the client coordinate path in:

- `mobile/lib/features/itinerary/itinerary_screen.dart`
- `mobile/lib/features/swap_sheet/swap_search_coords.dart`

The current itinerary swap path derives coordinates from the first trip node.
Pass the tapped target node through the production resolver so a Luang Prabang
card searches around its own coordinates, not Vientiane. Extend the real
SwapSheet request test to capture the latitude and longitude sent to the API.
A pure coordinate-helper test alone is not sufficient.

Do not use `trip.geo_region`, the first segment, or the last itinerary node as
a targeted swap proxy.

## Required tests

Add `tests/test_spec36_corridor.py` for backend/API proofs and
`mobile/test/spec36_corridor_test.dart` for Flutter/model/widget proofs.
Extend existing tests only where the changed compatibility contract belongs.

Cover every required proof case in SPEC-36, including:

- valid create and fetch;
- all request validation failures;
- atomic capacity refusal;
- four unique venues per city-day;
- deterministic repeated create;
- region-local 09:00 storage;
- no LLM, hybrid search, or quota;
- truthful normalized day indexes;
- target-node swap isolation;
- earlier-city mutations preserve the next city's requested date boundary;
- old and new Home snapshot parsing/cache round-trip;
- exact corridor POST body;
- invalid create UI;
- city order plus nested date order;
- past collapse and expansion through the production widget;
- later-city SwapSheet search uses the tapped node's coordinates;
- callback/node-ID preservation;
- unchanged single-city rendering;
- 800x600 overflow.

Do not call a pure helper test a widget proof. The collapse sabotage must pump
the production city-section widget, and the request-shape proof must drive the
real repository method.

## Mandatory sabotage run

Perform each sabotage from SPEC-36 separately. For each:

1. make only that break;
2. run the named targeted test;
3. record that the named test fails at the intended assertion;
4. revert only the sabotage;
5. rerun the test green.

Report all nine spec sabotage cases by test name. Stop if any
sabotage stays green.

## Gates

From repository root:

```bash
pytest -q -ra
pytest -q tests/test_docs_hygiene.py
ruff check .
git diff --check
```

Run `ruff format --check` on changed Python files only. Format only files you
changed.

From `mobile/`:

```bash
flutter analyze --no-fatal-infos
flutter test
```

R1 check for changed Dart files:

```bash
git diff --name-only origin/main...HEAD -- '*.dart' |
  xargs rg -n '\\\$'
```

Any `\$` match in a changed Dart file is a failure. Ordinary `$variable`
interpolation is correct.

Report passed and skipped counts separately with a reason for every skip.
If Flutter is unavailable, say it was not run; do not report a structural
inspection as a pass.

## Completion

1. Read the final diff from the branch, not the generation transcript.
2. Confirm there is no migration and no synthetic transport/stay node.
3. Update SPEC-36 status and acceptance boxes only for evidence actually
   produced.
4. Update `docs/PROJECT_STATUS.md` to IMPLEMENTED, not device verified.
5. Commit and push `feat/spec36-laos-corridor`.
6. Attempt to open a PR titled:
   `feat: create and render a multi-city Laos corridor`
7. If PR creation is blocked, report branch, full SHA, base SHA, compare URL,
   files changed, exact gate results, skips, and sabotage results. Do not claim
   the PR exists.
8. Do not merge.
