# Genie brief: SPEC-42 plain stops on non-empty days (backend)

Read this whole file before touching anything. It is the complete job.
If something here conflicts with memory of an earlier brief, this file
wins. If something is unclear, stop and ask; do not guess and do not
widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA.

Owning spec: `docs/specs/SPEC-42-flexible-trip-span.md`, section
"Amendment 2026-11-24: plain stops on non-empty days". Read it first. Its
rules 1 to 7 are binding.

## 0. Scope in one paragraph

A trip-private plain stop (no coordinates) is refused today on any day that
already has stops, because the neighbour walk cannot be measured. The owner
decided that plain stops may land on busy days with no travel check. This
slice makes that change on the server, and makes sure the change cannot make
any walking call site raise. Backend only.

## 1. Gate and tooling

- Backend only. No Flutter change, no APK, no hosted deploy.
- No schema change, migration, new endpoint, new field or dependency. If you
  need one, stop (section 7).
- Gate is CI (`pytest`, `lint`, `postgres-proof`, `docker-build`).
- Rules: R14 (ASCII only in new files and docs), R16 (no hard-coded test
  counts in docs). Never print tokens or credentials.

## 2. Verified facts on `main` (re-verify in preflight; line numbers drift)

- `services/uncatalogued_add_service.py` `apply_uncatalogued_add`: a plain
  prefs has no lat or lng, so `place_timing(..., lat=None, lng=None)` runs.
- `services/direct_add_service.py` `place_timing`: the neighbour checks call
  `_walk`, which returns None when any coordinate is missing, and a None
  walk refuses `reachability`. The next-lock check calls `fits_next_lock`
  with a None point, which also refuses.
- `services/transit.py` `walking_minutes` raises `ValueError` on any None
  coordinate. Callers must guard.
- `services/scheduler.py` lines about 132 and 143 already guard with
  `_has_coords`. A plain node gets zero transit. Do not change the scheduler.
- Call sites to audit (starting list, not complete): `services/move_service.py`
  about 293 (guarded by `_finite`, so it silently skips the walk: a fail-open
  to be fixed for catalog legs) and about 313; `agents/state_machine.py`
  about 186, 206 (guarded, fails closed) and 231; `services/catalog_itinerary.py`
  about 350; `services/booking_constraints.py` about 117, 303 and 488;
  `services/ask_service.py` about 1108, 1307, 1511 and 1671.

## 3. Preflight (do first; report before coding)

Report answers in your first message. Stop on any section 7 rule.

1. Confirm section 2's facts on current `main` and list the exact line of
   each call site.
2. For each call site in section 2, say whether a None coordinate can reach
   it on a busy day, and whether it currently raises, refuses, skips or
   passes. Use a table: site, reaches None (yes or no), current behaviour,
   planned behaviour.
3. Find the existing tests that assert `reachability` for a plain stop or for
   a stop next to a coordinate-less stop. List them.
4. Check `_apply_window` (the `time_window` path). Confirm it is separate and
   say whether a plain window add shares `place_timing`.
5. Check how `move_service` decides "movable" and whether a moved plain node
   reuses the catalog-leg rules.

## 4. Build

### 4.1 Plain placement (rule 1 to 3 of the amendment)

In the plain path only (no lat and no lng on the posted prefs; `venue_id`
null), add a plain-placement branch to `place_timing` or call a sibling
helper with the same contract:

- start = later of the slot floor and the previous stop's end (no walk term);
- `_slot_accepts_start` must still hold; no hours check (unchanged);
- time overlap with any existing stop still refuses `reachability`;
- for a locked stop after the plain stop: require plain end <= lock start,
  with no walk and no `fits_next_lock` call that needs coordinates;
- collision, duplicate, name and dwell rules are unchanged.

Coordinates-present adds keep the exact current behaviour.

### 4.2 Fail closed on unknown legs (rule 4 and 5)

- Any catalog candidate or any node with coordinates whose walk leg touches
  a coordinate-less stop is refused `reachability` (no exception, no pass).
- `move_service`: moving a catalog node whose adjacent leg touches a
  coordinate-less stop is refused `reachability`. Today it silently skips the
  walk. This changes behaviour only where a coordinate is missing, so state
  that in the PR. Moving a plain node follows section 4.1.
- Ask, What Now and swap candidate builders: a candidate whose leg touches a
  None point is omitted, not offered and not raised.
- Keep the scheduler unchanged. Its existing guards are the reference.

### 4.3 No raise (rule 5)

Every call site listed in preflight 2 must either never receive None on the
new paths or guard before calling. Add a parametrised test that invokes each
guarded entry point with a coordinate-less neighbour and asserts no exception
escapes.

## 5. Existing tests (the only permitted edit)

Exactly one existing expectation changes, and it is authorised here:

- `tests/test_spec42_uncatalogued_add.py::test_previous_neighbour_missing_coords_refuses_reachability`.
  It adds a plain stop (no coordinates) on Oct 12 dinner beside the `aft`
  stop. Under this amendment it places at the dinner floor (17:00 local).
  Rename it to `test_plain_stop_on_busy_day_places_in_slot_without_travel_check`
  and assert `r.ok` with `r.added.scheduled_start == local(2026, 10, 12, 17)`
  and `r.added.venue_id is None`.

No other existing test may change. If any other existing test fails, stop and
report it with the exact assertion. Do not edit it.

## 6. New tests

New file `tests/test_spec42_plain_busy_day.py`. Cover at least:

1. A plain stop on a busy day returns ok, has no coordinates, null
   `venue_id`, `place_source` trip_private, and starts at max(slot floor,
   previous end).
2. A plain stop whose time overlaps an existing stop is refused
   `reachability`.
3. A plain stop before a locked booking is ok when its end is no later than
   the lock's start, and refused `reachability` when it would overlap it.
4. A catalog stop with coordinates added next to a coordinate-less stop is
   refused `reachability` with no exception.
5. A catalog stop added after a plain stop is refused `reachability` with no
   exception.
6. Moving a catalog node next to a plain stop is refused `reachability`; moving
   a plain node follows rule 1 to 3. No exception in either case.
7. Swap, What Now and Ask candidate builders on a busy day with a plain stop
   return no candidate whose leg touches the plain stop and do not raise.
8. The scheduler on a day with a plain stop does not raise; the plain node has
   zero transit; catalog nodes after it are still scheduled.
9. HTTP: a plain add on a busy day returns one node and one reroute
   consumed; a refusal writes nothing and consumes no quota.
10. Parametrised no-raise test over every guarded entry point from preflight 2.
11. A `time_window` plain add behaves as before (preflight 4 confirms).

Also confirm `tests/test_spec58_import_plan.py` still passes unchanged. Test 9
places its plain stop on its own day, so it should not change.

## 7. Stop rules (write a question, do not widen scope)

Stop and report, quoting the preflight line, if:

- a plain stop needs a new field, a schema change or a new endpoint to be
  identified;
- a fix needs a change to the scheduler;
- a walking call site can only be made safe by changing a rule for
  coordinates-present stops;
- any existing test other than section 5's must change;
- the `time_window` path must change to pass a test;
- you need a new dependency or a migration.

## 8. Pull request and R17

- Branch: `feat/spec42-plain-busy-day` from current `origin/main`.
- Title: `feat(spec42): plain stops on non-empty days (backend)`.
- PR body: preflight answers 1 to 5, the call-site table, the list of existing
  tests touched (section 5's one test only), and a line stating there is no
  Flutter, schema, dependency or deploy change.
- Push three R17 sabotage branches, one commit each from the feature head,
  and state the expected failing tests:
  - `-r17a`: remove the previous-end floor from plain placement, so a plain
    stop starts at the slot floor even when it would overlap (expect test 2).
  - `-r17b`: let a catalog stop beside a plain stop pass (fail open) (expect
    tests 4 and 5).
  - `-r17c`: let `move_service` call `walking_minutes` with a None point
    (expect test 6 and the no-raise test 10).
  Branch names: `feat/spec42-plain-busy-day-r17a`, `-r17b`, `-r17c`.
- Do not merge and do not open PRs; the planning agent opens them and reads CI.
  If a sabotage fails tests other than the ones named, say so.

## 9. Non-goals

- Travel estimates for plain stops, or any guessed walk time.
- Flutter labels, map launch for plain stops, or the SPEC-58 Flutter slice.
- Changing `time_window` plain adds.
- Changing coordinates-present behaviour, scheduler behaviour or booking rules.
- More than four stops a day, or whole-day excursions.
- Any new field, table, endpoint or dependency.

## 10. Report format

End with: PR-ready branch and head SHA; preflight answers 1 to 5; the
call-site table; the test-to-production table; the three R17 branch heads and
their expected failing tests; any stop rule hit.

## Amendment 1 (2026-11-25, after Genie's preflight; wins where it differs)

Genie's preflight stop is accepted, and its call-site table and answers 1 to 5
are accepted with the corrections it gave (three walk legs in
`place_timing`; `ask_service` 1671 is an unused import).

### A1.1 What Now keeps its labelled unknown-walk candidates (option A)

`What Now` is advisory. It keeps offering candidates whose walk is unknown,
labelled `walking_time` in `unknown_fields`, and never claims "fits" or
"short walk" for them. That is the existing, tested behaviour
(`test_spec46_what_now.py::test_no_fits_available_window_without_coords`).
It is not a pass: nothing is written and no feasibility claim is made.

- Do NOT change `test_spec46_what_now.py`. Do NOT change What Now to omit
  unknown-walk candidates.
- Rule 4 in the spec ("refused, never a pass") applies to writes and to
  Add, Move and Swap. For What Now, the required behaviour is: label the walk
  unknown, never claim it fits, never raise.
- Swap and Ask candidate paths keep their existing omit or fail-closed
  behaviour (`state_machine.py` 186, 206, 231; `ask_service.py` 1111, 1307).
- Section 4.2's bullet "Ask, What Now and swap candidate builders ... omitted"
  is amended accordingly: omit for swap and Ask; label-unknown for What Now.

Add a test for the plain-origin case: What Now with a plain stop as origin
returns candidates labelled `walking_time` unknown, claims no fit, and does
not raise. Name it `test_what_now_plain_origin_labels_unknown_walk`.

### A1.2 Move refusal codes

For a catalog Move next to a plain stop, refuse with the existing
`neighbour_unreachable` code. Do not add a new code. Test 6 asserts that code.
A plain node that cannot be placed refuses `next_lock_unreachable` if a lock
is involved, as today.

### A1.3 Flight cutoff stays

A plain stop before a flight still respects the existing 150-minute flight
cutoff (`booking_constraints.py` 117 path), which needs no coordinates. Rule 2
applies to other locked stops. Test 3 covers the flight case explicitly:
refused if the plain end is inside the cutoff, ok otherwise.

### A1.4 Scope unchanged

The one authorised existing-test edit in section 5 stands. No other existing
test changes. A failure in any other existing test is still a stop.
