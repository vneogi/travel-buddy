# Genie brief: SPEC-10 create-then-book HITL reflow (slice 1)

Read this whole file before touching anything. It is the complete job.
If something here conflicts with memory of an earlier brief, this file
wins. If something is unclear, stop and ask; do not guess and do not
widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA. Base on that SHA is `origin/main` at or after `102ba95`
(docs PR #312).

Owning spec: `docs/specs/SPEC-10-booking-anchors.md`, remainder
"stay interval semantics and post-arrival intent", slice 1 (HITL
reflow). CI is the gate. Owner Windows `pytest` and `flutter test` are
allowed; do not ask for a phone APK.

## 0. Why this exists

Create already packs a full named-slot day. The traveller then adds a
booking. Today `add_booking` / `edit_booking` persist the locked node
and run `reschedule_and_validate` (time pushes and warnings). They do
not thin the day's flexible stops to the remaining SPEC-41 slots, and
they never ask. A 18:00 arrival on a four-stop day still shows four
stops.

SPEC-10: bookings define what is possible, not what the traveller wants
immediately afterward. Remaining slots are computed first. Intent may
only choose among those slots. The conservative default is the lighter
set. Affected flexible nodes are one reviewed reflow and persist only
after HITL. Dismiss leaves the itinerary as it was after the booking
save (flexible nodes unchanged).

`services/day_slots.py` `compute_remaining_slots` already has the
conservative table. Named-slots brief left "HITL intent to restore
extra slots" out of that slice. This is that slice.

## 1. Bound: thin existing nodes, do not pack new ones

This slice does not call `pack_day`. It does not invent replacement
venues. It does not fill empty remaining slots. It only proposes
skipping (cancel-in-place) flexible nodes whose `slot_name` is outside
the remaining set for the chosen intent.

Walking time-pushes from `reschedule_and_validate` on add/edit stay as
they are today. Do not disable them.

## 2. Verified facts on `main` (re-verify in preflight; line numbers drift)

- `EventType` in `models/schemas.py` has `add_booking`, `edit_booking`,
  `delete_booking`, `move_activity`. Flutter `mobile/lib/data/models.dart`
  mirrors the wire strings. Add `confirm_booking_reflow` to both.
- `STRUCTURAL_EDIT_EVENTS` in `agents/state_machine.py` lists booking
  events. Add the new event. Apply it in `_node_apply_structural`.
- `agents/router_agent.py`: put `confirm_booking_reflow` on the LIGHT
  list with `edit_booking` / `delete_booking`. Deterministic, no LLM,
  no reroute quota.
- Add/edit booking already persist the locked node then
  `reschedule_and_validate`. Keep that. After a successful add, or an
  edit that changes `scheduled_start` or `duration_minutes`, attach a
  proposal. Do not attach one when no flexible node would be skipped.
- `TripEventResponse` (`models/schemas.py`) and Flutter
  `TripEventResult` (`mobile/lib/data/models.dart`) have no reflow
  field yet. Add optional `booking_reflow`. Extra JSON keys must not
  break old clients; old clients ignore unknown keys, but the Flutter
  parser must read the new field.
- Flexible catalog nodes carry `slot_name` (SPEC-41). Locked bookings
  keep `slot_name` null. Nodes with `is_locked`, `node_kind ==
  "booking"`, `status == skipped`, or `status == completed` are never
  in the extra list.
- `compute_remaining_slots(booking_local_hour, booking_type, has_hotel)`
  in `services/day_slots.py` is the conservative table. Reuse it. Do
  not change its existing return values.
- Flutter save is `AddBookingSheet._save` ->
  `itineraryControllerProvider.applyEvent` with
  `EventType.addBooking` / `editBooking`. On success it pops. Hook the
  sheet after a non-null `booking_reflow`.
- `POST /api/v1/trip/event` is the only route. No new route.

## 3. Intents (closed set)

Wire strings, ASCII only:

| intent | remaining slots |
| --- | --- |
| `conservative` | `compute_remaining_slots` for that local day |
| `restore_evening` | `["afternoon_evening_tour", "dinner"]` |
| `restore_morning` | conservative slots plus `"morning_tour"` if not already present |
| `keep_open` | `[]` (no flexible filler that day) |

Which intents the proposal offers:

- Arrival day (flight or train, local hour >= 14, or hotel check-in
  hour >= 14): `conservative`, `restore_evening`, `keep_open`.
- Departure / checkout morning (flight or train hour < 12, or hotel
  with hour < 12): `conservative`, `restore_morning`, `keep_open`.
- Any other booking that still has extra nodes: `conservative` and
  `keep_open` only.

Default selected intent is `conservative`. `restore_evening` is the
"show plus dinner" choice even when conservative is dinner-only.
`keep_open` is rest / pack / transfer (empty remaining time).
`restore_morning` is the hotel-near morning slot on a checkout or
early-departure day.

A local day is "affected" when the booking occupies it:
destination-local date of a flight/train/tour, or every local date a
hotel covers (check-in through the day before check-out for overnight
nights, plus check-out morning if checkout hour < 12). Reuse
`find_covering_hotel` / `_local_date_of` rather than inventing a second
coverage walker.

## 4. Proposal DTO (`booking_reflow`)

Closed shape. No extra keys. No venue names of skipped nodes in logs.

```text
booking_node_id: str
intents: list of the wire strings from section 3 (non-empty)
default_intent: "conservative"
days: list of {
  local_date: "YYYY-MM-DD"
  conservative_slots: list[str]
  extra_node_ids: list[str]   # flexible, not skipped, slot_name not in conservative
}
```

Omit `booking_reflow` (JSON null / field absent) when every day's
`extra_node_ids` is empty.

Flutter mirrors this 1:1. Do not reuse `PlanChangeProposal`.

## 5. Confirm event

`event_type=confirm_booking_reflow`

- `target_node_id` = the booking `node_id` (same as `booking_node_id`).
- `preferences.intent` = one of the four wire strings.
- Light, canned message, no LLM, no reroute quota.
- 409 if the booking is missing, not `node_kind==booking`, or already
  skipped. No mutation.
- 422 if `intent` is missing or not in the closed set. No mutation.
  Copy is short ASCII, no slot list dump.
- Apply: for each affected local day, remaining = table in section 3
  for that intent; every flexible node on that day whose `slot_name`
  is not in remaining is skipped with the same in-place skip as
  unlocked `cancel_activity` (status skipped, same `node_id`, not
  deleted, not sent to the bottom). Then `reschedule_and_validate`.
- Persist through the existing trip-state write (both backends; no new
  table; no migration).
- Response `booking_reflow` is null. `updated_nodes` is the post-skip
  itinerary.
- Idempotent: a second confirm with the same intent skips nothing
  more and returns success.

Dismiss: the client sends no event. Do not add a `reject_booking_reflow`
event.

## 6. Flutter

After `_save` gets a result with `booking_reflow` non-null, do not pop
yet. Show a sheet (new widget file under `mobile/lib/features/booking/`):

- Title: "Adjust this day"
- One-line summary: remaining slots for the default intent, using the
  existing slot labels already shown on cards (do not invent new copy
  if a label exists).
- Listed extra node titles (from `updatedNodes` by id) as "would be
  skipped".
- Intent chips / radio for the `intents` list. Default
  `conservative`. Changing intent updates the would-skip list from the
  same `days` plus the table in section 3 (client-side; no extra
  network call).
- Confirm: one `confirm_booking_reflow`, then pop both sheets.
- Not now: pop without a second event.
- Offline: same as other mutations (existing applyEvent refuse); do
  not enqueue a silent reflow.

Keys for tests: `booking_reflow_sheet`, `booking_reflow_confirm`,
`booking_reflow_dismiss`.

No APK. Widget tests only.

## 7. Tests (must fail on main except where noted)

Drive add/edit/confirm through `POST /api/v1/trip/event` (R17: not a
helper the test invented). Use a trip with named-slot flexible nodes
already on the day.

Backend (`tests/test_spec10_booking_hitl_reflow.py`):

1. Add a same-day 18:00 local flight to a day that has morning, lunch,
   afternoon, and dinner flexible nodes: booking is in `updated_nodes`
   and persisted; the four flexible nodes are still pending; proposal
   `default_intent` is `conservative`; extra ids are the three
   non-dinner nodes; `intents` includes `restore_evening` and
   `keep_open`.
2. After test 1, GET/reload trip without confirm: four flexible nodes
   still pending (dismiss = no event).
3. Confirm `conservative`: dinner remains pending; the three extra
   nodes are skipped; same `node_id`s.
4. Confirm `restore_evening` on the same 18:00 setup (fresh trip):
   afternoon and dinner pending; morning and lunch skipped.
5. Confirm `keep_open`: all four flexible nodes skipped; booking
   pending.
6. Confirm missing booking: 409, no node status change.
7. Confirm `intent=nights_out`: 422, no node status change.
8. Edit a 12:00 flight to 18:00: proposal appears; flexible nodes
   still pending until confirm.
9. Add booking that does not squeeze any slot (full remaining set):
   `booking_reflow` is null/absent.
10. Locked booking nodes and skipped nodes never appear in
    `extra_node_ids`.
11. Hotel check-in 15:00 local, one night, day already packed: extra
    list uses conservative remaining for hour 15
    (`afternoon_evening_tour`, `dinner`).
12. `confirm_booking_reflow` does not decrement reroute quota
    (compare remaining before/after).
13. Light path: configured-env guard that this event does not call an
    LLM client (same style as swap/move guards if one exists; otherwise
    assert `routing_tier_used` is `light`).
14. Second confirm `conservative` is success and does not duplicate
    skips.

Flutter (`mobile/test/spec10_booking_hitl_reflow_test.dart`):

15. After a fake add that returns `booking_reflow`, the sheet is shown
    (`booking_reflow_sheet`); Confirm sends exactly one event of type
    `confirm_booking_reflow` with `conservative`.
16. Dismiss (`booking_reflow_dismiss`) sends no second event.
17. Selecting `keep_open` then Confirm sends `intent=keep_open`.

Existing tests: do not change expected values. If an add_booking test
asserts on JSON keys with a closed set, extend the set to allow
`booking_reflow`. Setup-only changes: list them in the PR description.

R17: PR branch stays at two commits (backend, then Flutter). Push
also:

- `feat/spec10-booking-hitl-reflow-r17a`: from the PR tip, revert
  production apply of confirm (handler returns 200 without skipping);
  tests untouched. Expected: tests 3, 4, 5, 14 fail.
- `feat/spec10-booking-hitl-reflow-r17b`: from the PR tip, confirm
  always uses `conservative` remaining regardless of `intent`; tests
  untouched. Expected: tests 4, 5 and Flutter 17 fail.

Planning agent opens those as draft PRs, reads failing names, closes
unmerged, deletes the branches.

## 8. Explicitly out

- `pack_day` booking occupancy at create time
- Inventing new venues for remaining slots
- `trip_stay` table, new check-in/check-out columns, migrations
- Server-side document consent, email/PDF import, SPEC-39
- Changing `compute_remaining_slots` conservative returns
- SPEC-42 unknown-time excursions, Move, Ask-to-Add
- SPEC-25 trip-optional Ask, SPEC-43 Gap 4
- APK, Cloud Run, hosted deploy
- Logging confirmation codes, notes, or place names
- New dependencies

## 9. Stop rules

- Stop if thinning requires `pack_day` or a new catalog search.
- Stop if a migration or a new table is required.
- Stop if add/edit must stop persisting the booking until confirm
  (the booking save stays immediate).
- Stop if more than six existing tests need expected-value edits.
- Stop if `slot_name` is missing on the packed flexible nodes in the
  in-memory create path you would use for fixtures; report how those
  nodes look.
- Stop if confirm cannot reuse unlocked cancel skip semantics.

Do not edit this brief. Do not edit other `docs/` files; the planning
agent updates ledgers after merge.

## 10. Gates

- ASCII only in added comments and strings (R14).
- No hard-coded test counts (R16).
- `grep -rn '\\$' mobile/lib` after any Dart write (R1): only the two
  known price strings in `upgrade_screen.dart`.
- `pytest` green in CI; focused file plus existing SPEC-10 booking
  tests still pass.
- `flutter analyze --no-fatal-infos`: no new errors or warnings.
- Full `flutter test` green in CI.
- Jobs: `flutter`, `android-compile`, `pytest`, `lint`,
  `postgres-proof`, `docker-build` green. `deploy`/`build` skipped.

## 11. PR

Branch `feat/spec10-booking-hitl-reflow` from the base SHA you were
sent. Two commits: (1) backend DTO + apply + tests, (2) Flutter sheet
+ tests. Do not merge. Push the branch and the two `-r17a` / `-r17b`
heads. Send the planning agent the PR description (no `gh` on Genie
compute); the planning agent opens the PR.

PR description must include: test -> production-line table, R17
expected failures, any existing test touched, and "no APK in this
slice".
