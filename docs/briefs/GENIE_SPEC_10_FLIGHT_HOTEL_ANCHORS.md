# Genie Brief: SPEC-10 remainder -- preceding-evening flight and daily hotel anchor

Start a new branch from `origin/main` (must include SPEC-41 A3b `436c1c5`
and SPEC-10 provider-aware paste `fc6926b`):

```text
feat/spec10-flight-hotel-anchors
```

Do not merge. Do not deploy. Do not build an APK.
Do not touch `feat/spec25-grounded-ask`.
Do not continue from local dirty `feat/spec41-reachability` work.

Read first:

- `docs/specs/SPEC-10-booking-anchors.md` (Scheduler behaviours 1-2; Tests;
  Acceptance: "Flight constrains the preceding evening; hotel acts as a
  daily anchor")
- `docs/ENGINEERING_RULES.md`
- `docs/WAYS_OF_WORKING.md`
- `services/scheduler.py` (`_is_background_anchor`, `reschedule_and_validate`)
- `services/catalog_itinerary.py` (`pack_day`, `_fits_next_lock`)
- `services/transit.py` (`walking_minutes`)
- `agents/state_machine.py` (swap prev/next hotel skip; add/edit/delete booking)
- `tests/test_scheduler.py`
- `tests/test_booking_anchors.py`
- `tests/test_spec41_reachability.py`

Do not edit this brief.

## Why this slice exists

Locked bookings already do not move. Hotels already do not occupy dwell on
the activity timeline (SPEC-41 A3b). Same-local-day non-hotel locks already
make a candidate ineligible when walking cannot reach the lock.

That is not SPEC-10 scheduler items 1 and 2.

`_fits_next_lock` returns true when the lock is on a different destination-local
calendar date. A 07:00 flight tomorrow does not constrain tonight. The first
activity of a hotel-covered day still packs as if it had no origin: no walk
from the hotel in the morning, no walk back in the evening.

The product line this unlocks is "early flight tomorrow, take a cab back"
and "best food near your hotel".

## Goal

After this slice:

- a locked flight truncates the preceding evening with a named pre-flight
  buffer (07:00 local -> nothing after 04:30 local that night/morning);
- a hotel booking is the geographic origin for morning departure and the
  geographic destination for evening return on each local day it covers;
- hotels remain background calendar anchors (dwell still does not push the
  activity timeline);
- flights, trains, and tours still occupy the timeline;
- walking minutes stay deterministic (`walking_minutes`); never random,
  never `datetime.now()`, never Maps, never LLM;
- user-facing copy never quotes synthetic transit minutes.

## Explicitly out

- Provider-aware paste, Agoda adapters, golden corpus (already on main).
- Edit/delete booking events (already on main).
- `trip_stay`, check-in/check-out columns, multi-night UI, `day_index`.
- SPEC-39 PDF/OCR/email-provider ingestion and server-side document consent.
- Tour flex-buffer constants (30-45 min). Same-day tour locks stay on A3b
  walking. Do not reintroduce a 30-minute packing buffer.
- SPEC-25 Ask, SPEC-43, LangGraph, Flutter paste/parser changes.
- Weakening corridor exact-timestamp tests except where this slice's
  hotel/flight rules are the cause, and then only with a named invariant.

## 1. Named constants

Put them next to the scheduler/packing helpers (one module, imported by
`scheduler.py` and `catalog_itinerary.py`). Do not scatter magic numbers.

```text
PRE_FLIGHT_BUFFER_MINUTES = 150
HOTEL_RETURN_LOCAL_HOUR = 21
```

150 minutes is the spec example: 07:00 flight => 04:30 cutoff.
21:00 destination-local is the evening-return wall for hotel days.

Do not invent driving/taxi/metro. Intra-day feasibility is walking.

## 2. Preceding-evening flight

Applies only to `node_kind == "booking"` and `booking_type == "flight"`.
Destination-local timezone is `destination_tz(geo_region)` (SPEC-37). Naive
UTC fallback only when TZ is missing, same as the scheduler today.

Cutoff:

```text
cutoff = flight.scheduled_start - timedelta(minutes=PRE_FLIGHT_BUFFER_MINUTES)
```

An unlocked activity A (skip SKIPPED; skip hotel background anchors) that
starts before the flight is ineligible / must be truncated when:

```text
A.scheduled_start + duration(A) > cutoff
```

or, when both A and the flight have coordinates:

```text
A.scheduled_start + duration(A) + walking_minutes(A, flight) > flight.scheduled_start
```

Use the stricter of the two when coords exist. Missing flight or activity
coords: still enforce the buffer cutoff; do not assume zero walking.

Cross-midnight is required. A flight at 07:00 local on date D constrains
activities on local date D-1 whose end exceeds cutoff (cutoff lives on D
at 04:30). A3b same-day-only lock checks are not enough.

`pack_day` / swap search / swap apply / `reschedule_and_validate` must share
this predicate.

- Packing: omit a candidate that would violate the cutoff for the next
  locked flight (including next morning).
- Swap: omit and refuse apply for the same reason.
- Scheduler: do not move the flight. Pull an unlocked activity earlier when
  that keeps order and hours; if it cannot fit before cutoff, set
  `has_hard_conflict`. Do not drop nodes silently.

Hard-conflict copy: existing warning style. ASCII. No walking-minute
figures in user-visible strings.

Keep: a same-day afternoon flight still occupies the timeline and still
uses A3b walking to the lock. This slice adds the previous-evening /
pre-buffer wall; it does not replace same-day reachability.

## 3. Hotel as daily geographic anchor

Hotel bookings stay `_is_background_anchor`: they do not push later
activities by dwell (Mad Monkey 2760-minute proof in `tests/test_scheduler.py`
must remain green).

A hotel covers every destination-local date in

```text
[check_in_local_date, (check_in + duration_minutes)_local_date)
```

Checkout date is not a covered night. Check-in date is covered from
`scheduled_start` onward that local day.

On a covered local day D, with hotel H that has coordinates:

1. Morning departure. The first unlocked activity of D treats H as origin.
   Earliest start is
   `max(planned_or_day_cursor, origin_instant + walking_minutes(H, C))`
   where `origin_instant` is:
   - check-in instant on the check-in local day;
   - destination-local day-pack start (existing 09:00 cursor) on later
     covered mornings.
   Do not use the previous local day's last venue as walking origin for
   that first stop. Cross-day remains not a walking transfer (A3b).
2. Evening return. The last unlocked activity of D must satisfy
   `end(C) + walking_minutes(C, H) <= local D at HOTEL_RETURN_LOCAL_HOUR`.
   Missing hotel or activity coords: candidate/activity is ineligible for
   that last slot rather than assuming zero walking.

Hotels are still not the next locked reachability *target* for A3b flight
math. They are origin/destination geometry for the activity day.

If several hotels cover D, use the one whose stay interval contains D;
if two overlap, prefer the later check-in, then `node_id` (deterministic).

`pack_day` needs an optional day-origin hotel (coords + origin instant) and
must apply the evening-return check to the last packed stop. Create/corridor
today pack with no bookings; wire the optional argument so add/edit booking
reschedule and any remaining-day pack share it. Swap first-of-day / last-of-day
must use the same hotel origin/return rules.

Do not create extra hotel timeline nodes per day. One locked hotel node
remains.

## 4. Privacy

`confirmation_code` still never appears in logs, signals, warnings, or model
prompts. Add a captured-log assertion around add_booking / reschedule, not
only `PAYLOAD_SHAPES`. Raw paste and passenger names stay out.

No new signal. No new migration unless you truly add a column (you should
not).

## 5. Flutter

Backend-first. Do not change the paste parser or AddBookingSheet.

If itinerary already surfaces `has_hard_conflict` / scheduler warnings, keep
that path. Do not add a new booking UI. If you must touch Dart, R1
(`grep -rn '\\$' mobile/lib`) before commit. Mark Flutter UNVERIFIED if
the SDK is absent; skip `dart format` / `flutter analyze` / `flutter test`
in that case and say so.

## 6. Required tests

New file: `tests/test_spec10_flight_hotel_anchors.py`.

Flight:

- 07:00 local flight => cutoff is 04:30 local; an activity ending after
  04:30 is hard-conflict or omitted.
- A 22:00 previous-evening dinner that ends before cutoff remains.
- Next-morning flight constrains `pack_day` on the previous local date
  (sabotage: same-day-only `_fits_next_lock` must fail this test).
- Swap omits a late candidate that overruns cutoff; apply refuses it.
- Flight node `scheduled_start` never moves.
- Missing flight coords still enforce the 150-minute buffer.

Hotel:

- First activity of a covered morning is shifted by `walking_minutes(hotel,
  activity)`, not by hotel dwell and not by the previous day's last venue.
- Last activity that cannot walk back by 21:00 local is omitted or
  hard-conflict.
- A hotel that does not cover that local date does not apply.
- `test_hotel_booking_does_not_push_later_activity` (2760 min) still passes.
- `test_hotel_checkin_anchors_transit_origin` still passes.
- Hotel is not treated as next locked flight target.

Privacy:

- captured logs for add_booking/reschedule contain no confirmation_code.

API / state machine (not helper-only):

- add a 07:00 flight to a trip that already has a late evening activity;
  response has `has_hard_conflict` or the evening node is pulled before
  cutoff; flight unmoved; no LLM.
- add a hotel, then swap the first next-morning activity; search/apply use
  hotel origin walking.

Do not weaken A3b reachability proofs or locked-overrun proofs.

## 7. Gates

```text
pytest -q
ruff check .
git diff --check
```

If Dart changed: R1 grep, then Flutter gates or UNVERIFIED.

ASCII in `.py` comments/docstrings (R14). LLM never mutates without HITL.
Do not quote walking minutes in user-facing strings.

## Done when

- SPEC-10 acceptance "Flight constrains the preceding evening; hotel acts
  as a daily anchor" is true in production paths, not comments.
- Named constants exist and tests fail if they are removed.
- A3b hotel background-anchor and walking determinism remain.
- Commit on `feat/spec10-flight-hotel-anchors`, pushed. No merge.
