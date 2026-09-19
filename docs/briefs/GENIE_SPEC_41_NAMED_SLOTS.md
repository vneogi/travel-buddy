# Genie Brief: SPEC-41 -- named day slots and remaining travel-day occupancy

Start a new branch from the reviewed slice-2 head (or later main).

```text
feat/spec41-named-slots
```

Do not merge. Do not deploy. Do not build an APK.
Do not start from dirty local `feat/spec41-reachability`.
Do not implement SPEC-42 Add/Move, place-detail, paste, Ask, or
SPEC-43/44.

Read first:

- `docs/briefs/GENIE_REMAINDERS_SEQUENCE.md`
- `docs/specs/SPEC-41-hours-aware-scheduling.md` (Slot-shaped days;
  Travel days consume slots before packing)
- `docs/specs/SPEC-10-booking-anchors.md` (Remainder: pack_day flight
  and hotel constraints)
- `docs/VISION.md` section 18 engine impact (named slots)
- `services/catalog_itinerary.py` (`pack_day`)
- `services/scheduler.py`
- `mobile/lib/widgets/activity_card.dart` (`_formatTime`)
- `docs/ENGINEERING_RULES.md`

Do not edit this brief.

Wait for planning to accept slices 1 and 2 unless handed an explicit
base SHA.

## Why this slice exists

Flexible cards show walking-arithmetic clock times (10:52). Earliest-fit
`pack_day` can finish four city stops by lunch or ignore a 15:00 arrival.
SPEC-41 requires named slots. SPEC-10 deferred `pack_day` booking wiring
until those remaining slots exist. This slice is that wiring.

Locked bookings keep exact local times (already destination-local).

## Goal

Default full in-city day occupies these slots, in order:

```text
morning_tour
lunch
afternoon_evening_tour
dinner
```

Breakfast is not a default generated slot.

Keep exact instants internally for hours, walking, and validation.
Render flexible stops as the slot name. Render locked flights, trains,
and hotel check-in/out as exact destination-local times.

Occupancy:

- typical sight: `morning_tour` or `afternoon_evening_tour`
- restaurant: `lunch` or `dinner`
- whole-day excursion: morning and afternoon (lunch on site); dinner
  may still generate; never four city stops around it

Travel days: compute remaining slots from the locked booking plus
existing flight/hotel buffers on main, then pack only what remains.

Conservative defaults (HITL intent to restore a slot is out of this
slice; leave the lighter set):

- early-evening arrival: `dinner` only
- mid-afternoon arrival plus hotel check-in: evening plus dinner
- morning departure: no morning tour; hotel-near only if a slot remains
- checkout day: remaining morning, if any, near hotel
- insufficient remaining slots: open time, no filler

`pack_day` must take those remaining slots. Create/corridor may no
longer pack four earliest-fit city stops on an arrival or departure
day when bookings exist on the trip. If create-time has no bookings
yet, pack a normal slot-shaped full day; adding a booking later does
not silently reflow until HITL (existing mutation contract). Document
that create-then-book still needs a later HITL reflow proposal if you
cannot do booking-aware create in this slice -- but swap/validate and
any pack that already sees bookings must consume remaining slots.

LLM never assigns slots or venues.

## Required proofs

- a feasible mixed-window catalog fills morning, lunch,
  afternoon/evening, dinner rather than four morning stops
- whole-day excursion occupies morning+afternoon and leaves dinner
- early-evening arrival packs dinner only
- mid-afternoon arrival plus hotel check-in packs at most evening plus
  dinner
- Flutter flexible card shows slot name, not walking-derived HH:MM
- Flutter locked hotel/flight still shows exact local time
- existing SPEC-41 hours/reachability tests still pass
- swap still never calls LLM (configured-env guard)
- `grep -rn '\\$' mobile/lib` R1

## Explicitly out

- Traveller intent UI to restore extra remaining slots after arrival
- Empty-day Add/Move (SPEC-42 remainder)
- Place-detail cards
- Deploy, APK
- Changing missing hotel coords to reachable

## Done when

Touched pytest and Flutter tests are green. Do not merge.
