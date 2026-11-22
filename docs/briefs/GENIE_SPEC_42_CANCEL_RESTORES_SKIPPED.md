# Genie brief: SPEC-42 cancelling an excursion restores the stops it skipped

Read this whole file before touching anything. It is the complete job.
If something here conflicts with memory of an earlier brief, this file
wins. If something is unclear, stop and ask; do not guess and do not
widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA.

Owning spec: `docs/specs/SPEC-42-flexible-trip-span.md`, remainder
"cancel restores skipped stops" (the known gap recorded in the
unknown-time excursion slice 1 brief, item 8). Parent: the window
apply path in `services/uncatalogued_add_service.py` (`_apply_window`,
PR #326, `df5c10c`).

This slice is backend only. No Flutter change, no SQLite schema change,
no migration, no new dependency, no APK, no hosted deploy. It is gated by
`pytest` and CI. Owner Windows `pytest` is allowed.

## 0. Owner decisions (2026-11-22)

1. When a traveller cancels an excursion (a node with `time_window`), the
   stops that excursion skipped come back automatically, as PENDING, at
   their original `node_id`. The reply says so, for example
   "Canceled Prison Island. Brought back 2 stops: A, B."
2. If something now occupies a restored stop's time (for example a booking
   added after the excursion), that one stop stays SKIPPED. The reply
   names it: "Left skipped because it now clashes: C." The other stops are
   still restored.

## 1. Verified facts on `main` (re-verify in preflight; line numbers drift)

- `TripNode` is in `models/schemas.py` (about line 67). It already has
  `status: NodeStatus`, `slot_name`, `time_window` (about line 100) and
  `place_source`. The whole node persists in `state_json` (no column per
  field), so a new optional field needs no migration. Re-verify this in
  the persistence code before writing.
- `NodeStatus` is `PENDING`, `ACTIVE`, `COMPLETED`, `SKIPPED`
  (`models/schemas.py` about line 30).
- The window apply path is `_apply_window` in
  `services/uncatalogued_add_service.py` (about line 189). When the
  traveller confirms a review, it skips the conflicting flexible stops with
  `status = SKIPPED` (about line 277), builds the window node, then calls
  `reschedule_and_validate`. The conflicting stops are the `conflicts` list
  built about line 237: PENDING or ACTIVE, unlocked, not bookings, in the
  consumed slots. It does not tag which excursion skipped them. That is
  the gap.
- Booking reflow (`services/booking_reflow.py`, `apply_booking_reflow`,
  about line 217) also skips flexible stops in place. Those skips are not
  excursion skips and must never be restored by a cancel. Do not tag them.
- Cancel for a non-window node is in `agents/state_machine.py`, the direct
  status-flip branch under "SPEC-29 D4" (about line 920). It sets
  `SKIPPED` on an unlocked node, then calls `reschedule_and_validate`.
  Locked nodes are refused.
- The cancel reply is built in `_node_generate_response` (about line 1111).
  It is deterministic and currently returns "Canceled <venue>." Reuse that
  method for the restore notice.
- Cancel is allowed on window nodes. Move and swap refuse them with
  `window_node` (SPEC-42 slice 1; `services/move_service.py` and
  `routers/trip_router.py`). Keep that refusal unchanged.
- `reschedule_and_validate` (`services/scheduler.py` about line 76) returns
  `ScheduleResult` with `nodes`, `warnings` and `has_hard_conflict`.
- `TripEventResponse.message` (`models/schemas.py` about line 353) carries
  the reply text. `schedule_warnings` shows in the itinerary as "schedule
  issues", so do not put the restore notice there.

## 2. Change

1. Add an optional tag to `TripNode`:
   `skipped_by_window_id: Optional[str] = None`. Set only by `_apply_window`,
   and only on the conflicting stops it skips in place, to the window
   node's `node_id`. Booking reflow and unlocked cancel do not set it.
   The tag is cleared when the stop is restored.
2. Cancel of a node with `time_window` (in the apply branch of the state
   machine, before the generic cancel path, or as a branch inside it):
   a. Set the cancelled window node to SKIPPED as today.
   b. Candidates: nodes with `status == SKIPPED` and
      `skipped_by_window_id == <cancelled node_id>`. Nothing else is a
      candidate.
   c. For each candidate, in `scheduled_start` order, restore it to
      PENDING and clear the tag, then run `reschedule_and_validate` with
      the restored nodes as `mutated_node_ids`. A candidate is kept
      SKIPPED, with its tag kept, if restoring it would clash. A clash is
      any of:
      - its `slot_name` is used by a locked node or a non-hotel booking on
        that day;
      - its time span overlaps a locked node or non-hotel booking on that
        day;
      - its time span overlaps a non-skipped window node on that day;
      - the reschedule returns `has_hard_conflict` with it restored.
      If a candidate clashes, undo its restore before trying the next one.
   d. Reply: set `state["response"]` to "Canceled <window name>." plus
      " Brought back N stops: <names>." when N is 1 or more, plus
      " Left skipped because it now clashes: <names>." when any clashed.
      Use the venue names. Do not list `node_id`s.
   e. Legacy excursions (added before this change, no tag) cancel exactly
      as today: no restore, no error, reply "Canceled <window name>.".
      Do not guess which stops an old excursion skipped.
3. Persistence: the tag must survive a save and reload from `state_json`,
   so a cancel in a later request still restores. Add a test for this.

## 3. Tests (must fail on main unless noted)

Backend (`tests/test_spec42_cancel_restores_skipped.py`), all through
`POST /api/v1/trip/event` (`event_type` `cancel_activity` for the cancel,
`add_activity` with `mode` `uncatalogued_add` and `time_window` for the
excursion) or through the state machine where the route can't set it up:

1. Morning excursion over two flexible morning stops, reviewed and
   confirmed (`confirm_skip_node_ids`). Cancel the excursion: both stops
   are PENDING again, with the same `node_id`s, and the reply names both.
   Fails on main.
2. A stop skipped before the excursion by an unlocked cancel of its own is
   not restored when the excursion is cancelled. Passes on main; it guards
   the behaviour.
3. A stop skipped by booking reflow (`CONFIRM_BOOKING_REFLOW`) is not
   restored. Passes on main; it guards the behaviour.
4. Clash: after the excursion, a locked booking is placed in one skipped
   stop's slot (set up in the trip fixture where the route cannot create
   it, and say so in the PR). Cancel: the other stop comes back, the
   clashing one stays SKIPPED with its tag, and the reply names it. Fails
   on main.
5. Legacy excursion (no tag, built by writing the node without the field):
   cancel gives "Canceled <name>." with no restore and no error. Passes on
   main.
6. Round trip: after the excursion is confirmed, save and reload the trip
   (a new request reads it back from `state_json`), then cancel. The stops
   come back. Fails on main.
7. Cancel of a non-window node is unchanged: one status flip, reschedule,
   reply "Canceled <name>.". Passes on main.
8. A window node whose skipped stop has since been completed is not
   changed: the COMPLETED stop stays COMPLETED. Passes on main.
9. Move and swap of a window node still return `window_node`. Passes on
   main.

Existing tests: do not change expected values. If an existing test
asserts the old cancel reply text for a window node, stop and report it.
Stop if more than three existing tests need edits.

R17 (branches from the tip, each pushed as its own head):
- `feat/spec42-cancel-restores-skipped-r17a`: the clash check is removed,
  so every candidate is restored. Expected failures: test 4 only.
- `feat/spec42-cancel-restores-skipped-r17b`: the ownership filter is
  removed, so any SKIPPED stop on that day is a candidate. Expected
  failures: tests 2 and 3.

The planning agent opens each as a draft PR, reads the failing names,
closes them unmerged and deletes the branches.

## 4. Explicitly out

- Flutter changes (the itinerary already shows the restored status from
  the returned nodes)
- Restoring stops for excursions added before this slice (no tag exists)
- Restoring stops skipped by booking reflow
- Undo of an excursion add after it is confirmed (that is a cancel)
- Changing the review-before-skip flow or the `needs_review` payload
- Changing move or swap refusals
- Migration, new dependency, APK, hosted deploy

## 5. Stop rules

- Stop if `TripNode` persistence is not a JSON blob, so the tag would need
  a column or migration.
- Stop if the cancel path cannot tell a window node from an ordinary one
  without a schema change.
- Stop if the restore notice cannot go into `state["response"]` without a
  response-shape change.
- Stop if the only clean fix would change the review payload or the
  `window_node` refusal.
- Stop if more than three existing tests need edits.

## 6. Gates

- ASCII only in added code, comments and strings (R14).
- No hard-coded test counts in docs (R16).
- Full `pytest` green, `lint` green, `postgres-proof` green.
- Jobs: `pytest`, `lint`, `postgres-proof`, `docker-build`, `test` green.
  `flutter` and `android-compile` run but this slice touches no Flutter.
  `deploy` and `build` skipped.

## 7. PR

Branch `feat/spec42-cancel-restores-skipped` from the base SHA you were
sent. Do not merge. Push the branch and the two `-r17a` / `-r17b` heads.
Send the planning agent the PR description; the planning agent opens the
PRs.

The PR description must include: the preflight answers (the persistence
shape, the cancel branch you used, the reply field), a test-to-production
table, R17 expected failures, every existing test touched, the known
limit that excursions added before this slice are not restored, and "no
APK and no hosted deploy in this slice". Say that the phone check needs a
hosted deploy later.
