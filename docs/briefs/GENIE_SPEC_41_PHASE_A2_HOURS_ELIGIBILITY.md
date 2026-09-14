# Genie Brief: SPEC-41 Phase A2 -- Hours Eligibility on Create and Swap

Start a new branch from `origin/main` at or after `2d703f4`:

```text
feat/spec41-hours-eligibility
```

Do not merge. Do not deploy. Do not build an APK.

Read first:

- `docs/specs/SPEC-41-hours-aware-scheduling.md`
- `docs/ENGINEERING_RULES.md`
- `docs/WAYS_OF_WORKING.md`
- `services/opening_hours.py`
- `services/catalog_itinerary.py`
- `services/corridor_itinerary.py`
- `services/scheduler.py`
- `agents/state_machine.py` (`_node_venue_search`, `_node_apply_structural`, `_build_candidate_nodes`, `_node_from_venue`)
- `services/maps_service.py` (`check_venue_open`, `validate_venues`)

Do not edit this brief.

## Goal

Stop recommending venues the catalog already knows are closed for the proposed
destination-local slot. Create, corridor, swap search, and swap apply must all
call `check_slot` before persistence. The scheduler must use the same evaluator
and must not dump pre-existing hours warnings after an unrelated swap.

This slice is hours eligibility only. Do not add transit, lock-reachability,
window-retiming, ranking changes, personalization, or LLM behavior.

## Current defect

A1 added `check_slot` and preserved `opening_hours_structured`. Consumers still:

- flatten the first window into `HH:MM-HH:MM`;
- pick venues without asking whether they are open at the proposed time;
- keep the previous activity's start time on swap;
- validate the whole itinerary afterward with `maps_service.check_venue_open`;
- emit every saved-hours warning, including nodes the swap did not touch.

That is why a night market can be placed at 09:00 and then criticized.

## Shared helper

Add one production helper, used by create, corridor, swap, and the scheduler.
Do not copy `check_slot` into four files.

Suggested shape:

```text
hours_for_slot(structured, start_utc, duration_minutes, geo_region) -> HoursResult
```

Rules:

1. Convert `start_utc` to destination-local time with the existing region
   timezone helper. Never use UTC clock hour, device timezone, or `datetime.now()`.
2. Use the candidate's own dwell (`duration_for` / `typical_dwell_minutes`),
   not the replaced node's duration.
3. `HoursResult.CLOSED` is ineligible. Never schedule or offer it.
4. `HoursResult.UNKNOWN` remains eligible. Do not describe it as open.
5. `HoursResult.FITS` is eligible.
6. Flattened `opening_hours` strings are not authority. If structured hours
   are missing, the result is `UNKNOWN`.
7. Do not call Maps, an LLM, or `datetime.now()` inside this helper.

If hybrid search results omit `opening_hours_structured`, load it with
`get_venue_by_id` before evaluating. Do not treat a missing search DTO field
as unknown when the catalog row has structured hours.

## Create and corridor

Update:

- `nodes_from_catalog`
- `range_nodes_from_catalog` / `select_day_venues_scored`
- corridor day selection

When filling a day, evaluate each candidate at the cursor time for that stop
using that candidate's dwell. Skip `CLOSED`. Keep the current deterministic
order among `FITS` and `UNKNOWN` venues. Do not keep a known-closed venue to
preserve four or five stops.

If too few non-closed venues remain, raise the existing insufficient-capacity
error. A failed create still leaves no trip and no party.

Do not retime a closed venue into a later window in this slice. Window
retiming is Phase A3. A night market may appear only if the cursor already
falls inside an open window.

Copy structured hours onto each created `TripNode` so later validation does
not depend on a second lookup. Add optional
`opening_hours_structured` on `TripNode` with a null default. Keep the legacy
string field for rendering.

Advertised `max_days` may stay identity-capacity based. Do not redesign
SPEC-40 options in this slice.

## Swap search and apply

Search and apply must share the same hours predicate for the **target slot**.

Target slot:

- start = the existing node's `scheduled_start` (still preserved);
- duration = the **candidate's** dwell;
- timezone = the target node's `geo_region` or trip region.

Swap search:

- drop `CLOSED` candidates before they reach the sheet;
- do not use `maps_service.check_venue_open` or `datetime.now()` as slot
  authority;
- `UNKNOWN` candidates may remain, without an open claim.

Swap apply, including sheet `replacement_venue_id`:

- refuse `CLOSED` with the existing no-candidate / not-applied path;
- do not persist a closed replacement and then warn;
- write the candidate dwell and structured hours onto the replacement node.

If search would hide a venue, apply of that venue_id must also refuse. Add a
test that the same fixture is excluded from search and rejected on apply.

## Scheduler warnings

In `reschedule_and_validate`:

- use `check_slot` / the shared helper, not flattened-string
  `check_venue_open`;
- `CLOSED` on a node mutated by the current operation is a hard
  ineligibility, not a soft warning;
- `UNKNOWN` may produce a scoped uncertainty warning;
- emit hours warnings only for nodes whose `venue_id`, `scheduled_start`, or
  `duration_minutes` changed in this operation;
- one swap must not reprint pre-existing hours messages for untouched nodes.

Do not rewrite weather Heads-up copy. Do not delete `flatten_opening_hours`
yet if rendering still uses it.

## Required tests

Create / corridor:

- committed night-market / evening-only venue is not placed in a morning slot;
- committed Tuesday-closed venue is not placed on Tuesday;
- split-window venue is not placed across the lunch gap;
- unknown structured hours may still be scheduled;
- insufficient non-closed venues raise the typed capacity error and persist
  neither trip nor party;
- destination-local Tuesday in Asia/Vientiane is not evaluated as UTC Tuesday.

Swap:

- search omits a candidate `CLOSED` for the target slot;
- apply of that same `venue_id` does not persist;
- a `FITS` candidate at the same slot is offered and can apply;
- search and apply use the candidate dwell, so a long dwell that overruns
  closing is ineligible even if a 30-minute visit would fit;
- swap does not call an LLM.

Scheduler:

- swapping one node does not emit hours warnings for unrelated nodes;
- `UNKNOWN` on the mutated node may warn; `CLOSED` is not persisted then
  warned.

Sabotage:

1. Ignore `CLOSED` and keep packing by name. Name the night-market or
   Tuesday-closed create test that fails.
2. Evaluate swap hours with `datetime.now()` instead of the target slot.
   Name the swap test that fails.
3. Restore trip-wide hours warnings after swap. Name the scoped-warning test
   that fails.

Restore production code after each sabotage.

## Explicitly out

- transit / lock-reachability hard constraints (Phase A3);
- retiming a closed venue into another window the same day;
- changing interest ranking, party scoring, or personalization;
- deleting `flatten_opening_hours`;
- live Google Places `open_now`;
- Flutter UI;
- SPEC-10 paste, SPEC-25 Ask, SPEC-42 span;
- migrations;
- deploy / APK.

Existing SPEC-32 / SPEC-36 / SPEC-40 tests must stay green. If a golden
itinerary now contains a known-closed morning venue, update that fixture to
the hours-feasible deterministic successor and say so in the report. Do not
weaken the test to accept closed venues.

## Gates

```text
pytest -q tests/test_spec41_opening_hours.py tests/test_spec41_hours_eligibility.py
pytest -q -ra
ruff check .
ruff format --check .
git diff --check
```

Use the second test path above or an equivalent new focused file. Do not dump
hours-eligibility proofs only into unrelated legacy files.

Commit and push `feat/spec41-hours-eligibility`. Report the SHA, files
changed, named sabotage results, and any golden itinerary fixtures you had to
retarget. Stop for review.
