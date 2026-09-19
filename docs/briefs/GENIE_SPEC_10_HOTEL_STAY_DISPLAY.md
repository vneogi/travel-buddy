# Genie Brief: SPEC-10 -- dual hotel timestamps and lat/lng

Start a new branch from the reviewed slice-1 head (or `origin/main` only
if slice 1 is already merged). Do not reinvent date-cap work.

```text
feat/spec10-hotel-stay-display
```

Do not merge. Do not deploy. Do not build an APK.
Do not start from dirty local `feat/spec41-reachability`.
Do not implement named slots, `pack_day` booking occupancy, SPEC-42
Add/Move, place-detail, paste corpus, or a `trip_stay` table.

Read first:

- `docs/briefs/GENIE_REMAINDERS_SEQUENCE.md`
- `docs/specs/SPEC-10-booking-anchors.md` (Remainder: stay interval
  semantics)
- `docs/AWAITING_VERIFICATION.md` (Sep 18 hotel 01:02; Sep 19 laptop
  18:02 pass; missing lat/lng hotel-return warning)
- `docs/ENGINEERING_RULES.md`
- `agents/state_machine.py` (`ADD_BOOKING` / `EDIT_BOOKING`)
- `services/booking_constraints.py` (`violates_hotel_return`)
- `mobile/lib/features/booking/add_booking_sheet.dart`
- `mobile/lib/widgets/activity_card.dart`
- `tests/test_spec10_booking_local_time.py`

Do not edit this brief.

Wait for planning to say slice 1 is accepted before starting, unless
this brief is handed with an explicit base SHA.

## Why this slice exists

The add-booking sheet already has Check-in and Check-out. The itinerary
card still shows one `scheduled_start`. Checkout is only
`scheduled_start + duration_minutes` on the wire. Travellers cannot see
the interval they entered.

`add_booking_sheet.dart` does not send `lat` / `lng`.
`violates_hotel_return` returns True when hotel coords are missing, so
Champa Lao-style stays warn "cannot return to the hotel in time" even
when walking would have been fine. That guard must stay conservative
when coords are unknown. The fix is to persist real hotel coordinates,
not to treat missing as reachable.

Naive wall times are already destination-local on main (`933c705`).
Do not reopen that parser.

## Goal

After this slice:

1. Hotel cards show destination-local check-in and check-out. Coverage
   appears on each local date of the stay with one stable `node_id`.
   Flights/trains keep a single exact time.
2. Checkout remains derived from `scheduled_start + duration_minutes`
   unless you add optional explicit `check_out` in preferences that
   round-trips through the same destination-local parser as check-in.
   No new Postgres table.
3. Add/edit hotel accepts `lat` and `lng` when the client sends them.
   Persist on the booking node.
4. Client sends coords when they can be determined without an LLM:
   optional lat/lng fields, and/or copy from a catalog venue in the
   same `geo_region` whose name matches the hotel title (deterministic
   exact or documented normalization, with HITL still owning save).
   Do not geocode via a generative model. Do not add a new maps vendor
   in this slice.
5. `violates_hotel_return` still returns True when coords are missing.
   With coords, walking time is used as today.
6. Editing check-in or check-out recomputes duration, covered dates,
   and hotel morning-origin / evening-return inputs already on main.

## Required proofs

- hotel node with check-in 18:02 local 2 Oct and check-out 15:00 local
  3 Oct renders both times, not a single stamp
- Flutter itinerary/hotel card test for dual timestamps
- add_booking with lat/lng persists and swap hotel-return uses them
- add_booking without lat/lng still saves; hotel-return stays
  ineligible (True), itinerary is not mutated by the warning
- catalog name-match, if implemented, copies that venue's lat/lng and
  never a different venue's
- booking local-time tests still pass
- `grep -rn '\\$' mobile/lib` R1

## Explicitly out

- Named slots / pack_day remaining occupancy (brief 3)
- Date caps (brief 1)
- Weakening missing-coord to False
- LLM or new geocoding provider
- `trip_stay` schema, SPEC-16 columns
- Deploy, APK

## Done when

Touched pytest and Flutter tests are green. Do not merge.
