# Genie Brief: SPEC-41 Phase A3b -- Deterministic Transit and Locked-Anchor Reachability

Start a new branch from `origin/main` at or after `eb54c0c`:

```text
feat/spec41-reachability
```

Do not merge. Do not deploy. Do not build an APK.

Read first:

- `docs/specs/SPEC-41-hours-aware-scheduling.md`
- `docs/ENGINEERING_RULES.md`
- `docs/WAYS_OF_WORKING.md`
- `services/opening_hours.py` (`next_slot_start`, `hours_for_slot`)
- `services/catalog_itinerary.py` (`pack_day`, `duration_for`)
- `services/corridor_itinerary.py`
- `services/scheduler.py`
- `services/maps_service.py` (`get_transit_time`, `calculate_distance_km`)
- `agents/state_machine.py` (`_node_venue_search`, `_node_apply_structural`, `_build_candidate_nodes`)
- A3a tests in `tests/test_spec41_window_packing.py`
- A2 tests in `tests/test_spec41_hours_eligibility.py`
- `tests/test_scheduler.py`
- `tests/test_synthetic_transit.py`
- `tests/test_booking_anchors.py`

Do not edit this brief.

## Why this slice exists

A3a packs each venue into its earliest fitting same-day opening window, then
advances the cursor by dwell plus a fixed 30-minute transfer buffer.

That buffer is not travel time. The scheduler still calls
`maps_service.get_transit_time`, which uses `datetime.now()` and
`random.uniform`. Create and swap therefore do not treat previous-node travel
or the next locked booking as hard constraints.

SPEC-41 Stage 1 requires:

- reachable from the preceding active node using a deterministic transit
  estimate;
- enough time left to reach the next locked booking;
- no random transit multipliers and no server clock.

A3b owns that contract. Do not reopen A3a window packing, hours evaluation,
or truthful `max_days` except where the planner must consume the new transfer
helper.

## Goal

Replace the fixed 30-minute buffer and the random/clock mock transit path with
one deterministic walking-time helper. Use it in day packing, swap search,
swap apply, and scheduler validation.

After this slice:

- identical coordinates always produce identical minutes;
- create/corridor/range packing accounts for walking time between consecutive
  stops, not a constant 30 minutes;
- a candidate that cannot arrive from the previous active stop is ineligible;
- a candidate that cannot reach the next locked non-hotel booking is
  ineligible;
- hotels remain background calendar anchors and do not occupy the activity
  timeline;
- swap search and apply share the same reachability result;
- user-facing copy still never quotes synthetic transit minutes;
- SPEC-35 live Distance Matrix stays on the departure-notification path only.

## 1. Canonical transit helper

Add one public deterministic helper. Suggested module:
`services/transit.py`, imported by packing, swap, and the scheduler.

Suggested shape:

```text
walking_minutes(
    origin_lat, origin_lng,
    dest_lat, dest_lng,
) -> int
```

Contract:

1. Haversine distance from the existing formula in
   `maps_service.calculate_distance_km`. Prefer moving that formula next to
   the helper rather than copying it a third time.
2. Walking speed is a named constant, 5.0 km/h. Minutes =
   `ceil(distance_km / 5.0 * 60)`, then a named floor of 5 minutes.
3. Same inputs always return the same integer. No `random`, no
   `datetime.now()`, no traffic multiplier, no network, no LLM, no Maps.
4. Missing or non-finite coordinates raise a programmer `ValueError`. Callers
   that lack coordinates must not call the helper.
5. Do not invent driving, taxi, or metro modes in this slice. Intra-day
   feasibility is walking. A long walk that does not fit is ineligible, not a
   reason to assume a car.
6. Return minutes only. Do not attach user-facing copy, traffic labels, or
   mode strings used in responses.

`maps_service.get_transit_time` must not remain the authority for create,
swap, packing, or `reschedule_and_validate`. Either:

- make `get_transit_time` delegate to `walking_minutes` with no clock/random,
  and keep its dict shape for leftover callers; or
- stop calling it from those four paths.

Do not leave `random.uniform` or `datetime.now().hour` on any feasibility
path. A test must fail if they return.

Do not call `services/google_maps_real.py` or `services/route_provider.py`
from create, swap, packing, or the scheduler. Those remain SPEC-35
departure-only.

## 2. Geometry eligibility

SPEC-41 already says missing required geometry makes a venue ineligible.

In `pack_day` and swap candidate filtering:

- a candidate without both `lat` and `lng` is ineligible;
- if a previous active node exists and lacks coordinates, do not treat
  transfer as zero; the candidate is ineligible for that sequenced slot;
- first stop of a local day has no previous transfer.

Do not silently default Dubai coordinates.

## 3. Shared day planner

Update `pack_day` only. `nodes_from_catalog`, `range_nodes_from_catalog`, and
`build_corridor_nodes` must keep using it.

Per stop, after hours-window evaluation:

1. If this is not the first node of the local day, earliest start for
   candidate C is `prev_end + walking_minutes(prev, C)`.
2. Pass that earliest start into `next_slot_start`. Do not use one shared
   cursor plus 30 minutes for every candidate. Transfer depends on C.
3. `prev_end` is previous activity start plus its dwell. Hotels are not
   previous activity nodes inside packing (packing still emits activities).
4. After a candidate's slot and dwell are known, if a next locked
   non-hotel booking exists on the same local day with coordinates, require:

   ```text
   slot + dwell + walking_minutes(C, locked) <= locked.scheduled_start
   ```

5. Keep earliest-start selection, then deterministic rank/name/`venue_id`
   ties, category diversity, no-repeats, unknown-hours-at-cursor, and the
   existing stop-count contracts.
6. Delete the hardcoded `+ 30` transfer in `pack_day`.

Create/corridor currently have no bookings in the candidate list. The
next-lock check must still exist so range/create packing can receive an
optional lock later and so swap can share the predicate. If no lock is
supplied, skip that clause.

`compute_max_days_for_region` already uses `pack_day`. Coordinate changes
already invalidate the fingerprint. Do not rebuild capacity with identity
count. Do not add Maps or clock inputs to the cache key.

## 4. Swap search and apply

Swap still preserves the target slot time (A2). Add reachability to the same
eligibility predicate used by search and apply.

For candidate C at the target slot, with candidate dwell:

1. Hours: existing `hours_for_slot` / apply recheck. CLOSED remains refuse.
2. Previous active node (skip `SKIPPED`; skip hotel background anchors):
   `previous_end + walking_minutes(prev, C) <= target_start`.
3. Next locked non-hotel booking after the target (flight, train, tour):
   `target_start + dwell + walking_minutes(C, locked) <= locked.scheduled_start`.
4. Missing geometry on C, prev, or that locked neighbour => ineligible.
5. Search omitting C must also refuse C on direct apply.
6. Do not call `validate_venues` / `check_venue_open` / live Maps.
7. Do not put transit minutes into the user-facing response
   (`tests/test_synthetic_transit.py` must stay green).

Hotel bookings remain background anchors: they do not act as the previous
timeline occupier and do not act as the next locked reachability target.

## 5. Scheduler

`reschedule_and_validate` must use `walking_minutes` whenever both consecutive
active nodes have coordinates.

Keep:

- locked nodes immovable;
- hotel background-anchor end time;
- skipped nodes out of the forward pass;
- hours scoping from A2 (`mutated_node_ids`, skip booking hours);
- `has_hard_conflict` when a locked non-hotel node is overrun, or when a
  mutated/shifted activity is CLOSED.

Change:

- no `maps_service.get_transit_time` random/clock path;
- overrun math uses `walking_minutes`;
- do not append synthetic "N min transit" strings to user-visible warnings.
  Hard conflict remains a boolean plus existing hours warning copy.

Retarget `tests/test_scheduler.py` patches from
`maps_service.get_transit_time` to the new helper if the production call
site moves. Do not weaken locked-overrun proofs.

## 6. Required tests

New file: `tests/test_spec41_reachability.py`.

Helper unit tests:

- identical coordinates => identical minutes on repeated calls;
- ~5 km at 5 km/h is 60 minutes before the 5-minute floor, prove the
  arithmetic with a known Haversine pair;
- very short distance still returns 5;
- naive/missing coordinates raise `ValueError`;
- helper source contains neither `random` nor `datetime.now`.

Packing tests:

- two nearby venues pack with transfer equal to `walking_minutes`, not 30;
- a far second venue that cannot walk from the first before its window
  closes is absent;
- a candidate without coordinates is absent;
- first stop of the day does not add transfer;
- day N still cannot push day N+1;
- current Oct 2-9 Laos corridor still builds with four stops per day.

Lock tests (direct planner or swap, not vacuous helper-only):

- an attractive venue that overruns a same-day locked flight is omitted;
- a venue that fits before the same flight remains;
- a hotel booking does not omit that venue;
- missing lock coordinates omit the candidate rather than assuming zero
  transfer.

Swap tests through production state-machine paths:

- search omits a candidate unreachable from the previous activity;
- search omits a candidate that cannot reach the next locked flight;
- the remaining reachable candidate is the one applied (exact name);
- direct apply refuses the omitted candidate;
- Maps `validate_venues` / `get_transit_time` random path is not called;
- no LLM.

Scheduler tests:

- locked flight overrun using the walking helper sets `has_hard_conflict`;
- hotel does not create that overrun by occupying its dwell;
- two calls on the same nodes produce the same starts (no random drift).

Capacity:

- advertised `max_days` for every current region still creates successfully
  through the API (A3a truthful contract). If walking reduces a region's
  guaranteed span, the advertised value must drop with it. Do not restore
  the identity-capacity allowlist.

Sabotage (restore production after each; name the failing tests):

1. Restore `random.uniform` or `datetime.now()` on the packing/scheduler
   transit path.
2. Restore the hardcoded 30-minute `pack_day` buffer and ignore
   `walking_minutes`.
3. Skip the next-locked-booking check on swap apply.
4. Treat missing coordinates as zero transfer in packing.
5. Use a hotel as the next locked reachability target so a valid afternoon
   venue is refused.

## Explicitly out

- live Google Distance Matrix / `RouteProvider` for itinerary feasibility;
- driving/taxi/metro mode choice;
- changing swap to retarget a different clock time (still A2 slot);
- hours evaluator changes except consuming the new earliest-start;
- ranking-weight or personalization changes;
- Flutter;
- SPEC-10 paste, SPEC-25 Ask, SPEC-42 span, SPEC-43 security;
- migrations;
- deploy / APK.

Existing SPEC-32 / SPEC-36 / SPEC-40 / SPEC-41 A1-A3a tests must stay green.
If a golden itinerary changes because a stop was unreachable on foot, record
the exact before/after venue IDs in the report. Do not weaken hours tests to
keep an unreachable stop.

## Gates

```text
pytest -q tests/test_spec41_opening_hours.py \
  tests/test_spec41_hours_eligibility.py \
  tests/test_spec41_window_packing.py \
  tests/test_spec41_reachability.py \
  tests/test_scheduler.py \
  tests/test_synthetic_transit.py \
  tests/test_booking_anchors.py
pytest -q -ra
ruff check .
ruff format --check .
git diff --check
```

Commit:

```text
feat: enforce deterministic walking reachability
```

Push `feat/spec41-reachability`. Report the SHA, files changed, full gate
results, exact skipped tests, named sabotage failures, any golden itinerary
ID changes, and advertised `max_days_by_region`. Stop for review.
