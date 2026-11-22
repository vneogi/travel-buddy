# Genie brief: SPEC-42 unknown-time excursions (slice 1)

Read this whole file before touching anything. It is the complete job.
If something here conflicts with memory of an earlier brief, this file
wins. If something is unclear, stop and ask; do not guess and do not
widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA.

Owning spec: `docs/specs/SPEC-42-flexible-trip-span.md`, remainder
"unknown-time excursion windows". Parents: SPEC-41 named slots
(`services/day_slots.py`), SPEC-42 trip-private uncatalogued Add
(`05d917e`, PR #77), SPEC-10 slice 1 HITL reflow (PR #314) as the
review-before-skip pattern. CI is the gate. Owner Windows `pytest` and
`flutter test` are allowed; do not ask for a phone APK.

## 0. Why this exists

A traveller often knows "Prison Island on the 27th" or "Jozani forest
some afternoon" but not a clock time or a dwell. Today the trip-private
Add needs one named slot plus `typical_dwell_minutes` (15 to 240), and
refuses `occupied` if that slot already has a stop. There is no way to
say "this takes the whole day" or "this takes the morning".

Owner decisions (2026-11-22):

1. The Add sheet offers three windows instead of a clock time: Morning,
   Afternoon, Whole day. Whole day keeps dinner.
2. If the window covers stops already on that day, show a review sheet
   listing the stops that would be skipped. Nothing changes until the
   traveller confirms.

## 1. Window table (closed set)

Wire strings, ASCII only. Slots are SPEC-41 `SLOT_ORDER` names.

| `time_window` | consumed slots | label |
| --- | --- | --- |
| `morning` | `morning_tour`, `lunch` | Morning |
| `afternoon` | `afternoon_evening_tour` | Afternoon |
| `whole_day` | `morning_tour`, `lunch`, `afternoon_evening_tour` | Whole day |

`whole_day` equals `_WHOLE_DAY_CONSUMED` in `services/day_slots.py`.
Reuse that constant; do not define a second whole-day set. `morning`
includes lunch because a half-day morning excursion runs through lunch
(planning default; the owner may revise it later in an amendment).

## 2. Verified facts on `main` (re-verify in preflight; line numbers drift)

- Trip-private Add: `add_activity` with `preferences.mode ==
  "uncatalogued_add"`, routed in `agents/state_machine.py`
  (`_handle_uncatalogued_add`) to
  `services/uncatalogued_add_service.py` `apply_uncatalogued_add`.
  It reads `name`, `typical_dwell_minutes`, optional `lat`/`lng`/
  `micro_location`, `target_date`, `target_slot`, then calls
  `services/direct_add_service.py` `day_context` (returns `occupied`
  when the slot has a stop) and `place_timing`.
- Refusals carry `uncatalogued_add_refused` and a code from
  `REFUSAL_COPY`; the router turns them into a refusal with no mutation.
- `services/day_slots.py`: `SLOT_ORDER`, `_WHOLE_DAY_CONSUMED`,
  `WHOLE_DAY_VIBE_TAGS`. `services/catalog_itinerary.py`
  `_slot_floor_utc(slot, local_day, tz)` gives a slot's start floor.
- Unlocked `cancel_activity` skips in place (status skipped, same
  `node_id`). SPEC-10 slice 1 reuses that for `confirm_booking_reflow`;
  reuse it here too.
- `services/itinerary_normaliser.py` rows do not carry `slot_name` or
  `place_source`; `state_json` is the source of truth for those. A new
  optional `TripNode` field follows the same path. Preflight: confirm
  the SPEC-16 round-trip test still passes with the new field and no
  migration. If it needs a column, stop.
- Flutter: `mobile/lib/features/direct_add/direct_add_sheet.dart`
  (slot chips `direct_add_slot_<slot>`, private form). Card time label:
  find it in `mobile/lib/widgets/activity_card.dart` in preflight and
  record the line in the PR description.

## 3. Backend change

1. `TripNode` (Python `models/schemas.py`, Dart `models.dart`): add
   optional `time_window` (`None` or one of the three wire strings).
   Old clients ignore it; the Dart parser reads it.
2. `apply_uncatalogued_add`: accept `time_window` as an alternative to
   `target_slot` plus `typical_dwell_minutes`.
   - Exactly one of `target_slot` or `time_window`. Both or neither:
     refuse `invalid_slot`. A `time_window` request must not carry
     `typical_dwell_minutes` (refuse `invalid_dwell` if present).
   - Unknown `time_window`: refuse new code `invalid_window` ("Choose
     morning, afternoon, or whole day.").
   - Node: `slot_name` = first consumed slot in `SLOT_ORDER`;
     `time_window` set; `scheduled_start` = that slot's floor;
     `duration_minutes` = from that floor to the floor of the first
     slot after the last consumed slot (`whole_day` and `morning` run
     to the next slot floor; `afternoon` runs to the dinner floor).
     No reachability promise and no clock time shown; skip
     `place_timing` for window nodes.
   - Name, coords, catalog-collision and duplicate checks are unchanged.
3. Conflicts. For the target date, collect nodes on that local day whose
   `slot_name` is in the consumed set:
   - Any locked node or booking in the window (by slot or by time
     overlap with the window): refuse new code `locked_conflict`
     ("A booking is already in that window."). No mutation.
   - Flexible pending nodes in the consumed slots, and no
     `confirm_skip_node_ids` in the request: refuse new code
     `needs_review` and include `excursion_review: {time_window,
     skip_node_ids}` (closed shape, ids in itinerary order). No
     mutation.
   - Request carries `confirm_skip_node_ids`: recompute; if the set
     differs from the current conflict set, refuse new code `stale`
     ("This day changed. Review again."). If equal, skip those nodes
     in place (cancel semantics), insert the window node, then
     `reschedule_and_validate`. One persisted write.
   - No conflicts: insert directly (no review).
4. Dinner is never consumed. A dinner stop on that day stays pending.
5. Logs: no venue names in new log lines.
6. `excursion_review` is a new optional field on `TripEventResponse`
   (Dart `TripEventResult`), null unless the code is `needs_review`.

## 4. Flutter change

1. Private form in `direct_add_sheet.dart`: a "No fixed time" choice
   that replaces the slot chips and dwell field with three window chips
   (keys `direct_add_window_morning`, `direct_add_window_afternoon`,
   `direct_add_window_whole_day`; labels from section 1).
2. Save sends `time_window` and no `target_slot` or dwell.
3. On `needs_review`: show a review sheet (key
   `excursion_review_sheet`) titled "Make room for this", listing the
   would-skip stop names from the current itinerary by id. Confirm
   (`excursion_review_confirm`) resends the same request plus
   `confirm_skip_node_ids`, then closes both sheets. Not now
   (`excursion_review_dismiss`) sends nothing and keeps the Add sheet.
4. On `stale`: show the refusal copy and keep the Add sheet open.
5. Card: a node with `time_window` shows the window label instead of a
   clock time. Every other card is unchanged.
6. Clear any saving spinner before awaiting the review sheet (lesson
   from PR #314: a spinner left running blocks `pumpAndSettle`).

## 5. Tests (must fail on main)

Backend (`tests/test_spec42_unknown_time_excursions.py`), all through
`POST /api/v1/trip/event`:

1. `whole_day` on an empty day: one node, `slot_name` `morning_tour`,
   `time_window` `whole_day`, duration runs to the dinner floor.
2. `afternoon` on an empty day: `slot_name` `afternoon_evening_tour`.
3. `morning` on a day with a pending lunch stop: `needs_review` with
   that lunch id; no node added; lunch still pending.
4. Confirm with the matching `confirm_skip_node_ids`: lunch skipped in
   place (same id), excursion added, one write.
5. `whole_day` over morning, lunch and afternoon stops plus a dinner
   stop: review lists three ids; after confirm, dinner is still pending.
6. Confirm with a stale id set: `stale`, no mutation.
7. A locked booking inside the window: `locked_conflict`, no mutation.
8. Both `target_slot` and `time_window`: `invalid_slot`.
9. Unknown window `evening`: `invalid_window`.
10. `time_window` with `typical_dwell_minutes`: `invalid_dwell`.
11. Existing slot-plus-dwell Add (no `time_window`) behaves exactly as
    before, including `occupied`.
12. Round trip: GET the trip after test 1; `time_window` survives.

Flutter (`mobile/test/spec42_unknown_time_excursions_test.dart`):

13. Choosing "No fixed time" then Whole day sends `time_window:
    whole_day` and no `target_slot` or dwell.
14. A fake `needs_review` response opens `excursion_review_sheet`;
    Confirm sends exactly one more event carrying the same ids.
15. Not now sends no second event.
16. A node with `time_window: afternoon` renders "Afternoon" and no
    clock time.

Existing tests: do not change expected values. If a closed key-set test
on `TripNode` or `TripEventResponse` needs the new optional field, that
is a setup change; list it. Stop if more than four existing tests need
expected-value edits.

R17: PR branch stays at two commits (backend, then Flutter). Push also:

- `feat/spec42-unknown-time-excursions-r17a`: from the tip, the confirm
  path inserts the node but skips nothing. Tests untouched. Expected
  failures: 4, 5.
- `feat/spec42-unknown-time-excursions-r17b`: from the tip, `morning`
  consumes only `morning_tour` (drop lunch). Tests untouched. Expected
  failures: 3, 4.

The planning agent opens each as a draft PR, reads the failing test
names, closes them unmerged and deletes the branches.

## 6. Explicitly out

- Catalog whole-day venues (the `WHOLE_DAY_VIBE_TAGS` packer path stays
  as it is)
- An "Evening" or "Sometime this day" window
- Multi-day excursions
- Editing or moving a window node (Move refuses it as today, or treat it
  as its `slot_name`; preflight reports which, no change)
- `pack_day`, new catalog rows, opening hours for trip-private stops
- Booking reflow logic (SPEC-10 slice 1 is on main; do not touch it)
- Migrations, new tables, APK, Cloud Run, new dependencies

## 7. Stop rules

- Stop if `time_window` needs a database column or migration.
- Stop if confirm cannot reuse unlocked cancel skip semantics.
- Stop if the window cannot be expressed with existing slot floors.
- Stop if more than four existing tests need expected-value edits.
- Stop if Move or swap would silently reschedule a window node into a
  clock slot; report how they treat it.

## 8. Gates

- ASCII only in added comments and strings (R14).
- No hard-coded test counts in docs (R16).
- `grep -rn '\\$' mobile/lib` after any Dart write (R1): only the two
  known price strings in `upgrade_screen.dart`.
- `ruff check` and `ruff format --check` clean.
- `flutter analyze --no-fatal-infos`: no new errors or warnings.
- Jobs: `pytest`, `lint`, `flutter`, `android-compile`,
  `postgres-proof`, `docker-build`, `test` green. `deploy`/`build`
  skipped.

## 9. PR

Branch `feat/spec42-unknown-time-excursions` from the base SHA you were
sent. Two commits: (1) backend plus tests, (2) Flutter plus tests. Do
not merge. Push the branch and the two `-r17a` / `-r17b` heads. Send the
planning agent the PR description (no `gh` on Genie compute); the
planning agent opens the PRs.

The PR description must include: the preflight answers (round-trip
test, card time line, Move and swap treatment of a window node), a
test-to-production table, R17 expected failures, any existing test
touched, and "no APK in this slice".

## Amendment 1 (planning agent, 2026-11-22, after Genie's preflight)

Preflight facts (base `bb81250`):

- The `time_window` field round-trips in `state_json` on both backends with no
  column, so that stop rule does not trigger.
- Card time label (`mobile/lib/widgets/activity_card.dart`, about lines
  229-239): line 233 shows a clock time only for locked or unslotted nodes;
  line 239 shows `_slotLabel(slotName)`. A window node would show "Morning" for
  `whole_day`, so the card needs a `time_window` branch ahead of line 239.
- Move and swap do not know about windows. Move reschedules a window node into
  a clock slot (an 8-hour node moved to the afternoon runs through dinner).
  Swap replaces it in place with a 45-minute catalog stop and drops
  `time_window`, leaving the day half empty.

Decision (owner delegated; option A): refuse both, in the backend and in the
sheet.

1. Backend. A node with `time_window` set is refused by Move and by swap, with
   new code `window_node` and copy "This excursion covers a whole window.
   Remove it and add it again to change it." No mutation. Apply it in:
   - `services/move_service.py` `apply_move`, before any timing check;
   - the swap event path and the swap candidates read in
     `routers/trip_router.py`, following the existing refusal shape for those
     two routes (report the shape you used in the PR description).
2. Cancel stays allowed. `cancel_activity` on a window node skips it in place
   like any unlocked stop.
3. Flutter. Hide Move and Swap on a card whose node has `time_window`. Keep
   Cancel or skip. Extend the existing movable check (`nodeIsMovable`) rather
   than adding a second one.
4. Card label (section 4 item 5, confirmed): add a `time_window` branch ahead of
   line 239 using the window table labels.
5. Added tests. Backend (`tests/test_spec42_unknown_time_excursions.py`), all
   through `POST /api/v1/trip/event` or the swap candidates route:
   17. Move of a window node: refused `window_node`, no mutation. Fails on main.
   18. Swap event on a window node: refused `window_node`, no mutation. Fails
       on main.
   19. Swap candidates read for a window node: refused with the existing shape
       and code `window_node`. Fails on main.
   20. `cancel_activity` on a window node: skipped in place, same `node_id`.
   21. Move and swap of a trip-private node without `time_window`: behaviour
       unchanged from main.
   Flutter (`mobile/test/spec42_unknown_time_excursions_test.dart`):
   22. A card with `time_window` shows no Move or Swap action and still shows
       Cancel or skip. Use the existing action keys or text; report which.
6. R17 gains a third branch: `feat/spec42-unknown-time-excursions-r17c`, from the
   tip, removes the `apply_move` refusal. Expected failures: 17 only. The two
   existing branches keep their expected failures (`-r17a`: 4, 5; `-r17b`: 3, 4).
7. Section 6 item "Editing or moving a window node" is replaced by this
   amendment: Move and swap are refused, not left as they are. Section 7's
   Move and swap stop rule is satisfied by decision item 1; report anything that
   would still reschedule a window node.
8. Known gap, not this slice: cancelling an excursion later does not restore the
   stops it skipped. The traveller re-adds them with Add. Record it in the PR
   description.
