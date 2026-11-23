# Genie brief: SPEC-42 refuse a booking inside an active excursion window

Read this whole file before touching anything. It is the complete job.
If something here conflicts with memory of an earlier brief, this file
wins. If something is unclear, stop and ask; do not guess and do not
widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA.

Owning spec: `docs/specs/SPEC-42-flexible-trip-span.md`, follow-up
"booking accepted over an active excursion" (recorded in
`docs/UX_BACKLOG.md` after PR #343). Parents: SPEC-42 unknown-time
windows (PR #326, `df5c10c`), cancel restores skipped stops (PR #343,
`081626a`), SPEC-10 booking anchors.

This slice is backend only. No Flutter change, no SQLite schema change,
no migration, no new dependency, no APK, no hosted deploy. It is gated by
`pytest` and CI. Owner Windows `pytest` is allowed.

## 0. Owner decision (2026-11-23)

A non-hotel booking whose time overlaps an active excursion window is
refused, with a clear message telling the traveller to cancel the
excursion first. This mirrors the existing rule the other way round: an
excursion already refuses to be added over a booking (`locked_conflict`
in `_apply_window`). Hotels are exempt on both sides.

## 1. Verified facts on `main` (re-verify in preflight; line numbers drift)

- Add booking: `agents/state_machine.py`, branch
  `if event_type == EventType.ADD_BOOKING.value:` (about line 690). It
  resolves the region, parses `scheduled_start` with `_parse_wall_time`,
  builds a locked `TripNode` (`node_kind="booking"`, `booking_type` from
  prefs, default `"flight"`, `duration_minutes` default 90), inserts it,
  reschedules and builds the reflow proposal. Its one refusal today
  (unknown city) sets `state["booking_refused"] = True` and puts the
  message in `state["schedule_warnings"]`, then returns before mutating.
- Edit booking: the `EDIT_BOOKING` branch (about line 763). Phase 1
  validates (city, time parse) and refuses the same way with no
  mutation. Phase 2 mutates the node in place (title, type, duration,
  time, coords). Any new check must run in phase 1, before the in-place
  mutation, using the values the edit would produce.
- The refusal reaches the client through `routers/trip_router.py`
  (about line 803): a 422 with `{"error": "booking_refused", "message":
  ...}`, nothing persisted. The reply text comes from
  `_node_generate_response` taking the first `schedule_warnings` entry.
- Booking mutations take no reroute quota (router comment
  "SPEC-10: Booking mutations (no quota, no LLM)", about line 558).
  Confirm in preflight that add booking also takes none.
- Flutter `mobile/lib/core/api_client.dart` (about line 70) surfaces every
  typed 422 `detail.message`. Confirm in preflight that the add and edit
  booking sheets show that message; if they do not, stop.
- An excursion window node has `time_window` set (`models/schemas.py`).
  It is active when its `status` is PENDING or ACTIVE. Its span is
  `scheduled_start` to `scheduled_start + duration_minutes` (UTC).
- `_apply_window` (`services/uncatalogued_add_service.py`) exempts hotels
  (`_is_hotel`: `node_kind == "booking"` and `booking_type == "hotel"`).

## 2. Change

1. One shared helper (for example in `services/uncatalogued_add_service.py`
   next to `_is_hotel`, or a small new module) that, given the trip's
   nodes, a candidate booking span, its `booking_type`, and an optional
   node id to ignore, returns the first active window node it overlaps,
   or None. Overlap is strict: a booking ending exactly at the window's
   start, or starting exactly at its end, does not overlap. Hotels never
   overlap.
2. Add booking: after the start time and type are known and before the
   node is inserted, call the helper. On a hit: `booking_refused`, no
   mutation, message:
   "This overlaps <excursion name> (<window label>, <local date>).
   Cancel the excursion first, then add the booking."
   Use the window labels already in `_WINDOW_LABELS` and the booking's
   destination-local date.
3. Edit booking: in phase 1, only when the edit changes
   `scheduled_start`, `duration_minutes` or `booking_type`, compute the
   span and type the edit would produce and call the helper (ignoring the
   booking's own node id). On a hit: `booking_refused` with the same
   message, and the node is not changed at all (not even fields like the
   title in the same edit). Edits that change none of those three fields
   are never refused by this rule, so a booking that already overlaps
   (created before this slice) can still have its notes or title fixed.
4. Do not change cancel-restore, the window add path, move/swap
   refusals, booking reflow, or delete booking.

## 3. Tests (must fail on main unless noted)

Backend (`tests/test_spec42_booking_over_window.py`), through
`POST /api/v1/trip/event`. Create excursions through the real add flow
(`add_activity`, `mode` `uncatalogued_add`, `time_window`, review then
`confirm_skip_node_ids` where stops exist):

1. A tour booking inside an active morning window: 422
   `booking_refused`, message names the excursion and says to cancel it
   first; the stored trip and its version are unchanged. Fails on main.
2. A flight booking inside an active window: refused the same way. Fails
   on main.
3. A hotel booking inside an active window: accepted. Passes on main.
4. A tour booking inside a cancelled (SKIPPED) window: accepted. Passes on
   main.
5. Boundaries: a booking ending exactly at the window start, and another
   starting exactly at the window end, are both accepted. Passes on main.
6. Edit a booking's time into an active window: refused; the booking's
   time, duration and title are unchanged even though the same edit also
   changed the title. Fails on main.
7. Edit a booking's duration so it runs into an active window: refused.
   Fails on main.
8. Edit only the notes of a booking that already overlaps a window
   (set up in the stored trip, as a pre-slice booking): accepted. Passes
   on main.
9. The refusal takes no reroute quota (compare remaining before and
   after). Passes on main if add booking already takes none; report.

Existing tests that must change setup:
`tests/test_spec42_cancel_restores_skipped.py`,
`test_clashing_stop_stays_skipped_and_is_named` and
`test_reply_wording_one_restored_two_clashed` add locked bookings over an
active excursion through `add_booking`. After this slice that is refused.
Change only their setup: place those bookings directly in the stored trip
(as a pre-slice booking would be), keep every assertion and expected value.
Say so in the PR description. Stop if any other existing test needs edits,
or if those two need an expected-value change.

R17 (branches from the tip, each pushed as its own head):
- `feat/spec42-booking-over-window-r17a`: the hotel exemption is removed.
  Expected failures: test 3.
- `feat/spec42-booking-over-window-r17b`: the edit check is removed.
  Expected failures: tests 6 and 7.
- `feat/spec42-booking-over-window-r17c`: the active-status filter is
  removed (a cancelled window still refuses). Expected failures: test 4.

The planning agent opens each as a draft PR, reads the failing names,
closes them unmerged and deletes the branches.

## 4. Explicitly out

- Flutter changes
- Warning or review flows (the owner chose refuse)
- Refusing or reshaping bookings that already overlap (pre-slice data)
- Any change to how an excursion treats bookings
- Paste or import paths other than `add_booking` / `edit_booking`, unless
  preflight finds they bypass these branches (then stop and report)
- Migration, new dependency, APK, hosted deploy

## 5. Stop rules

- Stop if any path creates or edits a booking node without going through
  the `ADD_BOOKING` or `EDIT_BOOKING` branches; list it.
- Stop if the booking sheets do not show a 422 `detail.message`.
- Stop if the edit check cannot run before the in-place mutation without
  restructuring phase 2.
- Stop if any existing test other than the two named above needs edits,
  or if those two need an expected-value change.

## 6. Gates

- ASCII only in added code, comments and strings (R14).
- No hard-coded test counts in docs (R16).
- Full `pytest` green, `ruff check` and `ruff format --check` clean.
- Jobs: `pytest`, `lint`, `postgres-proof`, `docker-build`, `test` green.
  `flutter` and `android-compile` run but this slice touches no Flutter.
  `deploy` and `build` skipped.

## 7. PR

Branch `feat/spec42-booking-over-window` from the base SHA you were sent.
Do not merge. Push the branch and the three `-r17a` / `-r17b` / `-r17c`
heads. Send the planning agent the PR description; the planning agent
opens the PRs.

The PR description must include: the preflight answers (every booking
create/edit path found, the quota answer, how the sheets show the
message), a test-to-production table, R17 expected failures, the two
existing tests whose setup changed and why, and "no APK and no hosted
deploy in this slice". Say that the phone check needs a hosted deploy
later.

## Amendment 1 (2026-11-23, after Genie preflight)

Genie's preflight found that the booking sheet hides the server's refusal
text. Facts re-verified on main: `mobile/lib/features/booking/add_booking_sheet.dart`
`_save` (about line 355) replaces every failed save with the fixed
"Could not save this booking. Check your connection and try again."
`ItineraryNotifier.applyEvent` (about line 207) already turns a 422 into a
`ValidationException` and puts its message in the controller banner, which
renders behind the modal sheet. Without a fix the traveller would never see
"Cancel the excursion first". The owner approved option A.

1. This slice is no longer backend only. One small Flutter change is in
   scope: when a save fails with a server validation message, the sheet shows
   that message in place of the fixed copy. Every other failure keeps the
   exact current copy.
   - Existing sheet tests that assert the fixed copy must pass without any
     expected-value change. Network and unknown failures must therefore keep
     the fixed copy. Only a `ValidationException` message may replace it.
     Because `applyEvent` reduces all failures to one banner string, do not
     compare banner strings against known generic text. Use the least
     invasive typed signal you can find (for example a small field on the
     controller state set only for `ValidationException`, or the exception
     itself) and report what you used.
   - Clear the controller banner after the sheet reads the message, so the
     same text does not also show behind the sheet.
   - Files in scope: `add_booking_sheet.dart`, the notifier or its state
     only if needed for the typed signal, and one new Flutter test file.
     No other Flutter file.
2. Test 8 clarification (from the preflight): the sheet sends every field on
   every edit. "The edit changes time, duration or type" means the new value
   differs from the node's current value, not that the key is present. A
   notes-only or title-only edit that resends the same time, duration and type
   is never refused by this rule, even for a booking that already overlaps.
3. Added tests. Flutter (`mobile/test/spec42_booking_over_window_test.dart`):
   10. A refused save (fake repository throws `ValidationException` with the
       refusal text) shows that text in the sheet and the sheet stays open.
       Fails on main.
   11. A `NetworkException` and an unknown error still show the fixed copy,
       unchanged. Passes on main.
   Backend test 8 is tightened to resend identical time, duration and type
   with a new note and title (accepted), plus a second case that resends the
   same fields but a different type into a window (refused).
4. R17 gains a fourth branch:
   `feat/spec42-booking-over-window-r17d`, from the tip, removes the sheet's
   use of the server message. Expected failures: test 10 only. The other
   three branches keep their expected failures.
5. Gates: add `flutter analyze --no-fatal-infos` with no new errors or
   warnings, and the R1 check (`grep -rn '\\$' mobile/lib` shows only the two
   known price strings in `upgrade_screen.dart`). There is no Flutter SDK on
   Genie compute, so CI's `flutter` job is the first compile of the Flutter
   half. Do not install Flutter without owner approval.
6. Stop rules added:
   - Stop if the typed signal needs more than the notifier, its state and the
     sheet.
   - Stop if any existing Flutter test needs an expected-value change.
7. Section 0 "backend only", the scope line at the top, and section 4's
   "Flutter changes" are replaced by this amendment: one Flutter change, no
   APK request (CI and owner Windows `flutter test` are the gate), no hosted
   deploy.
