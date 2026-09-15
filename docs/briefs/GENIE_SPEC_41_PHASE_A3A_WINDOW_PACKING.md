# Genie Brief: SPEC-41 Phase A3a -- Window-Aware Day Packing

Start a new branch from `origin/main` at or after `377125e`:

```text
feat/spec41-window-packing
```

Do not merge. Do not deploy. Do not build an APK.

Read first:

- `docs/specs/SPEC-41-hours-aware-scheduling.md`
- `docs/ENGINEERING_RULES.md`
- `docs/WAYS_OF_WORKING.md`
- `services/opening_hours.py`
- `services/catalog_itinerary.py`
- `services/corridor_itinerary.py`
- `config/interests.py`
- A2 tests in `tests/test_spec41_hours_eligibility.py`

Do not edit this brief.

## Why A3 is split

Phase A2 prevents known-closed create and swap candidates from being persisted.
It exposed a second issue: identity-based capacity can advertise a trip span
that the current 09:00-forward greedy packer cannot fill. All three Laos
regions currently have this mismatch.

A3a fixes deterministic same-day window packing and truthful advertised
capacity. A3b will replace synthetic/random transit and enforce previous-node
and next-locked-anchor reachability. Do not combine A3b into this branch.

## Goal

Use the existing structured weekday windows to schedule each selected venue at
its earliest valid same-day start at or after the current cursor. Prefer
candidates available sooner, preserve deterministic ranking for ties, and
advertise only a `max_days` value that the same planner can actually fill for
every possible start weekday.

After this slice:

- morning-only venues remain in morning windows;
- lunch-gap venues move to a later split window instead of being discarded;
- evening markets can be placed in the evening;
- no activity crosses its closing time or local-day boundary;
- every region/date span accepted by advertised `max_days` can be built with
  the current catalog;
- the three-region mismatch allowlist is deleted.

## 1. Canonical next-window helper

Extend `services/opening_hours.py` with one public deterministic helper. Choose
a clear typed result; suggested shape:

```text
next_slot_start(
    structured,
    earliest_start_utc,
    duration_minutes,
    geo_region,
    local_day,
) -> datetime | None
```

Contract:

1. Convert through the existing region IANA timezone helper.
2. Return a UTC-aware datetime.
3. If `earliest_start` already fits, return it unchanged.
4. Otherwise return the earliest declared window start on `local_day` where
   the complete dwell fits.
5. Split windows are independent. If dwell misses the first, try the second.
6. A window may be considered only if its start is at or after the cursor.
7. Do not search minute-by-minute. Parse and compare declared boundaries.
8. Do not move an activity to another local calendar day.
9. The activity must end on `local_day`, even when catalog hours use an
   overnight window.
10. Null or malformed structured hours are `UNKNOWN`; schedule them at the
    cursor and preserve uncertainty. Do not invent a window.
11. Explicitly closed/no fitting window returns no slot.
12. Naive datetimes and invalid durations follow the A1 programmer-error
    contract.
13. No `datetime.now()`, Maps, LLM, random value, or network call.

Keep `check_slot` and `hours_for_slot` backward compatible.

## 2. Shared deterministic day planner

Extract one planner used by:

- `nodes_from_catalog`;
- `range_nodes_from_catalog`;
- `build_corridor_nodes`.

Do not maintain three independent retry loops.

Suggested inputs:

- ordered candidate rows;
- target stop count;
- destination-local date and 09:00 start;
- region;
- already-used venue IDs;
- existing category/ranking order.

For each stop:

1. Exclude invalid identity/geometry, infrastructure categories, and used IDs
   under the current contracts.
2. For every remaining candidate, compute its earliest fitting same-day start.
3. Select the candidate with the earliest start.
4. For equal starts, retain the caller's existing deterministic rank/category
   order, then normalized name and `venue_id`.
5. Append the node at that start.
6. Advance the cursor by dwell plus the existing fixed 30-minute transfer
   buffer. A3b will replace that buffer with deterministic travel time.
7. Repeat until the requested stop count is reached or no candidate fits.

Preserve:

- SPEC-40 interest scoring and category diversity;
- corridor category diversity;
- no repeats;
- legacy/unknown-hours venues as eligible at the cursor;
- the exact stop counts: legacy create `MIN_STOPS..TARGET_STOPS`, range and
  corridor four per day.

Do not make a high-ranked night market force an all-day wait when another
candidate can start earlier. Earliest feasible start is compared before rank;
rank resolves equal-start candidates.

The planner returns nodes and updated used IDs without mutating caller input.
A failed multi-day build returns no partial result to persistence.

## 3. Truthful `max_days`

Delete the temporary mismatch behavior for:

- `luang_prabang_laos`;
- `vang_vieng_laos`;
- `vientiane_laos`.

`compute_max_days_for_region` must use the same day planner, not raw identity
count alone.

Because options are requested before dates, compute a conservative guaranteed
maximum:

1. Evaluate all seven possible local start weekdays.
2. For each weekday, try consecutive spans from one day through the product
   ceiling.
3. Use the same no-repeat, hours-window, dwell, category/ranking, and stop-count
   behavior as real range create.
4. The advertised value is the largest span buildable for every start weekday.
5. Clamp to the existing product ceiling.
6. Unknown hours remain eligible, matching real create.

Use fixed calendar anchors whose weekdays are explicit; do not depend on the
server clock. Do not issue network/model calls. Keep computation small and
deterministic for the current catalogs.

If a region cannot build one day, omit it from advertised create options under
the existing unsupported-region contract.

## 4. Required tests

Next-window helper:

- cursor already inside a fitting window is unchanged;
- cursor before opening moves to opening;
- cursor in a lunch gap moves to the second split window;
- dwell too long for first window uses a later fitting window;
- dwell too long for every window returns no slot;
- evening-only venue moves to evening;
- overnight venue may run in the evening but cannot cross local midnight;
- explicitly closed weekday returns no slot;
- unknown hours stay at cursor;
- destination timezone differs from UTC;
- input datetime is not mutated.

Day planner:

- an open-now venue is chosen before a night market despite rank order;
- equal-start candidates retain interest/category/name/ID determinism;
- morning, lunch, and evening venues produce chronological starts;
- no venue repeats across days;
- day N evening work does not push day N+1 past 09:00;
- every emitted node returns `FITS` or `UNKNOWN` from `hours_for_slot`;
- input rows and used-ID sets are unchanged;
- insufficient capacity raises the existing typed path with no trip or party.

Truthful capacity:

- for every advertised region, create at advertised max succeeds for all seven
  possible start weekdays;
- one day above advertised max is rejected by date validation when below the
  product ceiling;
- the three-region A2 mismatch allowlist is removed;
- Dubai legacy null structured hours retain deterministic capacity;
- sabotage raw identity-count capacity and name the test that fails.

Golden cases:

- committed Luang Prabang night market appears only in an evening window;
- committed split-window venue never crosses its lunch gap;
- current Oct 2-9 Laos corridor still builds with four stops per day;
- each golden node is validated against its structured hours.

Sabotage:

1. Return the cursor instead of the next split/evening window. Name the helper
   and golden test failures.
2. Rank before earliest start so a night market blocks an open-now venue. Name
   the planner test that fails.
3. Carry day N cursor into day N+1. Name the independent-day test that fails.
4. Restore identity-only `max_days`. Name the seven-weekday capacity test that
   fails.
5. Permit a node to end after local midnight. Name the boundary test that
   fails.

Restore production after every sabotage and report the failing test names.

## Explicitly out

- changing swap target times;
- transit-time estimation or Maps calls;
- previous-node reachability;
- next locked-booking reachability;
- random/synthetic transit cleanup;
- persistence schema or migrations;
- ranking-weight changes;
- party scoring or personalization;
- LLM behavior;
- Flutter;
- SPEC-10, SPEC-25, or SPEC-42;
- deploy or APK.

Those reachability items are A3b. Do not pre-implement them.

## Gates

```text
pytest -q tests/test_spec41_opening_hours.py \
  tests/test_spec41_hours_eligibility.py \
  tests/test_spec41_window_packing.py
pytest -q -ra
ruff check .
ruff format --check .
git diff --check
```

Commit:

```text
feat: add deterministic hours window packing
```

Push `feat/spec41-window-packing`. Report the SHA, files changed, full gate
results, exact skipped tests, named sabotage failures, final advertised
`max_days_by_region`, and any golden itinerary changes. Stop for review.
