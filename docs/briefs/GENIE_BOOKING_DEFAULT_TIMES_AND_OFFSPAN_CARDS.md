# Genie brief: booking defaults (date and times) and cards for dates outside the trip span

Read this whole file before touching anything. It is the complete job.
If something here conflicts with your memory of an earlier brief, this file
wins. If something here is unclear, stop and ask; do not guess and do not
widen scope.

Start only when the planning agent (or owner) sends this brief with a real
base SHA.

Owning specs: `docs/specs/SPEC-10-booking-anchors.md` ("Decision: default
hotel times") and `docs/specs/SPEC-42-flexible-trip-span.md` ("Decision:
nodes outside the span"). Both decisions are owner decisions from the
2026-11-21 phone test and are already written into those specs. Scope is
Flutter only (`mobile/`). No backend change, no migration, no hosted deploy.
CI is the gate. Do not install Flutter on Genie compute without owner
approval.

## 0. Context: what the owner saw on the phone

1. Add Booking, hotel: check-in and check-out showed 02:02 and 02:09. The
   owner confirmed these were not chosen: the sheet starts from the phone
   clock, and it was about 2 AM. The owner wants a fixed 12:00 check-in and
   11:00 check-out and no clock picker for hotels.
2. A flight booked for Thu 24 Dec, the day before the trip's first day (Fri
   25 Dec), appeared in the UP NEXT strip but no card appeared in the
   timeline.
3. The Add Booking calendar opened on today's month (November) with
   tomorrow selected. The owner wants it to open on the trip's month with the
   trip's first day already selected; the traveller can pick any other day.

Three small fixes. One PR, two commits: commit 1 is Part A (the booking sheet:
default date and default times), commit 2 is Part B (cards outside the
span).

### Verified facts on `main` (re-verify in preflight; line numbers drift)

Part A, `mobile/lib/features/booking/add_booking_sheet.dart`:

- `initState` sets `_scheduledStart` to `widget.initialScheduledDate ??
  DateTime.now().add(const Duration(hours: 24))`. That carries the current
  clock time, including seconds, into the booking.
- `_pickDateTime` (non-hotel), `_pickCheckinDate` and `_pickCheckoutDate`
  each open `showDatePicker` then `showTimePicker`. The time picker starts
  from `_scheduledStart` (or the check-out value).
- Fallbacks when the time picker is dismissed: check-in 15:00, check-out
  12:00. These conflict with the owner decision.
- A new hotel gets `_checkoutDate = _scheduledStart + 24 hours`, both in
  `initState` and in the type `ChoiceChip` handler.
- `initialScheduledDate` is documented as a testing override.
  `mobile/test/spec_g0_booking_city_test.dart` passes
  `DateTime(2026, 10, 6, 15, 0)` through it.
- The calendar opens on `initialDate: _scheduledStart` in `_pickDateTime` and
  `_pickCheckinDate`, with `firstDate: DateTime.now()` (or the existing value
  in edit mode) and `lastDate: DateTime.now() + 365 days`. If a trip's first
  day is earlier than today, `initialDate` earlier than `firstDate` makes
  Flutter's date picker assert, so the bounds must be widened (rule 11).
- The trip's first date is available through
  `itineraryControllerProvider(widget.tripId)`: `ItineraryState.creationContext`
  (`CreationContext.startDateLocal`, a `String?` date) for single-city trips,
  `ItineraryState.segments` (`TripSegment.startsOn`, a date string) for
  corridor trips, and `ItineraryState.nodes` (each with `scheduledStart` and
  `geoRegion`). `core/destination_tz.dart` has `toDestinationLocal`.
- `scheduled_start` is sent as `_scheduledStart.toIso8601String()`. A naive
  ISO string is destination-local wall time (SPEC-10, `933c705`). Do not
  change that convention.

Part B, `mobile/lib/features/itinerary/date_scope.dart`:

- `spanAwareDayGroups` builds `byKey` from
  `groupNodesByCalendarDateWithHotelStays(nodes)`, then walks only from
  `startLocal` to `endLocal` and emits `byKey[key] ?? empty group`. Any key
  outside that walk is never emitted, so the node is silently dropped.
- `spanAwareCorridorGroups` calls `spanAwareDayGroups` per segment with the
  segment dates, so a node that matches the segment region but is dated
  outside the segment dates is dropped the same way.
- `resolveDayGroups` (single-city path) also calls `spanAwareDayGroups`.
- The UP NEXT strip (`now_next_strip.dart`) reads the raw node list, which is
  why the flight showed there.

## 1. Part A: booking default date and times

Rules (all in `add_booking_sheet.dart`; the parser is not touched):

1. Hotel check-in is the chosen date at 12:00; hotel check-out is the chosen
   date at 11:00. No `showTimePicker` is opened for a hotel. Tapping the
   Check-in or Check-out tile opens the date picker only.
2. A new hotel (not edit mode, no `initialScheduledDate`) starts with check-in
   at 12:00 on the default date and check-out at 11:00 on the next day.
   Switching the type chip to Hotel applies the same pair. Switching away from
   Hotel clears the check-out as today.
3. The hotel tiles show the fixed time with the date, for example "Fri 25 Dec,
   12:00" and "Tue 29 Dec, 11:00", so the traveller can see the assumption. Use
   the sheet's existing date formatting helper; add the time as plain text. No
   new fonts, colours or icons.
4. Edit mode: an existing hotel keeps its stored times until the traveller
   picks a new date for that endpoint. The picked date then gets 12:00
   (check-in) or 11:00 (check-out).
5. Pasted confirmations that carry explicit times keep those times; the
   defaults apply to manual entry only. Do not change `booking_parser.dart`.
6. Non-hotel bookings (flight, train, tour, other types the sheet offers) keep
   the date picker followed by the time picker, because the time matters for
   the day. The time picker's `initialTime` is the current value of
   `_scheduledStart`. A new non-hotel booking with no `initialScheduledDate`
   starts at 12:00 (seconds and milliseconds zero) on the default date, not at
   the current clock time. If the user dismisses the time picker, keep the
   current value (do not invent 15:00).
7. When `initialScheduledDate` is supplied, use it exactly as given for the
   start. Do not normalise its time. (Existing tests and callers depend on
   this.) Defaults apply when it is null, or when the traveller picks a date.
8. Hotel validation is unchanged: check-out must be after check-in. With the
   fixed times, a same-day check-out is rejected (11:00 is before 12:00).
9. Hotel and non-hotel pickers keep their existing `lastDate` and
   `firstDate` behaviour except where rule 11 widens them.
10. Default date (owner decision): a new booking (not edit mode, no
    `initialScheduledDate`) starts on the trip's first day, not tomorrow, and
    the calendar opens on that day's month with that day selected. The traveller
    can pick any other day. The trip's first day is, in this order:
    (a) `creationContext.startDateLocal`, parsed as a calendar date;
    (b) the earliest `TripSegment.startsOn` over all segments (not just the
    first listed);
    (c) the calendar date of the earliest node's `scheduledStart` converted with
    `toDestinationLocal(node.scheduledStart, node.geoRegion)`;
    (d) none, in which case use tomorrow as today. Put this in a small pure
    function (for example `tripFirstLocalDate`) in `date_scope.dart` so it can
    be unit-tested; it returns a date-only `DateTime?` and does no I/O. Read the
    state with `ref.read` in `initState`. The existing
    `_recomputeCityDefault` call after the first frame stays; on a corridor trip
    it now picks the first segment's city for that day.
11. Picker bounds: `firstDate` is the earlier of today (date only) and
    `initialDate` (date only); `lastDate` is the later of today plus 365 days
    and `initialDate` plus 365 days. This keeps an in-progress or past trip from
    tripping Flutter's `initialDate >= firstDate` assertion. Edit mode keeps its
    existing bounds logic with the same widening. The check-out picker keeps
    `firstDate: _scheduledStart` and its existing `lastDate`.
12. The default date never changes the time rules above: non-hotel starts at
    12:00, hotel check-in 12:00, hotel check-out 11:00 the next day.

## 2. Part B: cards for dates outside the span

Change `spanAwareDayGroups` in `date_scope.dart`:

1. Keep the current walk from `startLocal` to `endLocal` inclusive, with an
   empty group for each date that has no node. Unchanged.
2. Collect the populated groups whose date key is before the start date or
   after the end date.
3. Return: pre-span populated groups in ascending date order, then the span
   groups, then post-span populated groups in ascending date order.
4. Do not create empty groups for dates outside the span. A booking ten days
   before the span adds one extra group, not ten.
5. A multi-night hotel already appears on every covered date through
   `groupNodesByCalendarDateWithHotelStays`; nothing else changes for hotels.
6. `spanAwareCorridorGroups` and `resolveDayGroups` need no logic change if
   they only call `spanAwareDayGroups`. Verify that. Do not change the corridor
   `dateRange` label or `_effectiveSegmentEndDate`.
7. Do not change the UP NEXT strip, `groupNodesByCalendarDate`, the trip span
   values, or server data.
8. The timeline renders a header and card for the extra groups using the same
   code path as other dates. Check `itinerary_screen.dart` for anything that
   filters by span after grouping; if you find one, stop and report before
   changing it.

## 3. Tests (named, all in `mobile/test/`)

New file `mobile/test/booking_default_times_and_offspan_test.dart`. Reuse the
helpers and mocking patterns in `spec_g0_booking_city_test.dart` (sheet),
`spec42_uncap_trip_span_test.dart` (grouping) and `spec31_widget_test.dart`
(timeline). Each test below must fail on current `main` for the reason named.

Part A, sheet:

1. `new hotel saves 12:00 check-in and 11:00 check-out on the next day`:
   hotel type, no override, enter a name, save with no picks. Saved
   `scheduled_start` is 12:00:00.000, and `duration_minutes` is 1380.
   Fails on `main` because the start carries the clock time.
2. `hotel check-in picker opens no time picker`: tap Check-in, choose a date,
   expect no `TimePickerDialog` at any point, and the saved start is that date
   at 12:00. Fails on `main` because a time picker opens.
3. `hotel check-out picker opens no time picker`: same for check-out at 11:00.
4. `hotel tiles show the fixed times`: the Check-in tile text contains `12:00`
   and the Check-out tile contains `11:00`.
5. `editing a hotel keeps stored times until a date is picked`: edit a node
   with check-in 15:00 and check-out 10:00; save without picks and expect
   15:00 and 10:00; then pick a new check-in date and expect 12:00.
6. `new flight starts at 12:00 not the clock`: flight type, no override, save
   with no picks. Saved start has hour 12, minute 0, second 0, millisecond 0.
   Fails on `main` because seconds and milliseconds are non-zero.
7. `flight keeps date and time pickers`: tap Date & Time, expect the time
   picker to open after the date picker.
8. `initialScheduledDate is used exactly as given`: hotel and flight with
   `DateTime(2026, 10, 6, 15, 0)` keep 15:00 on save.
9. `dismissing the flight time picker keeps the current time`.
10. Existing tests (`spec_g0_booking_city_test.dart`,
    `provider_paste_widget_test.dart`) stay green. If a failure shows a real
    conflict, stop and report; do not weaken the assertion.

Part B, grouping and timeline:

11. `node before the span start gets its own earlier group`: flight on Dec 24
    19:06, activity on Dec 25, span Dec 25 to Dec 27. Expect four groups in
    the order Dec 24, 25, 26, 27, and the first group holds the flight.
12. `node after the span end gets its own later group`.
13. `no empty dates are invented outside the span`: flight on Dec 20, span
    Dec 25 to Dec 27, expect four groups (Dec 20, 25, 26, 27), not eight.
14. `nodes inside the span behave as before`: the existing three
    `spanAwareDayGroups` tests stay unchanged and green.
15. `corridor segment includes a matching node dated before its start`
    (`spanAwareCorridorGroups`).
16. `hotel stay that starts before the span shows on each covered date`.
17. `timeline renders a card for a booking the day before the trip`: widget
    test on `ItineraryScreen` with a trip whose span starts Dec 25 and a
    flight on Dec 24; expect a header for 24 December and the flight card.
    Fails on `main` because no card renders.

Part A, default date and calendar month:

18. `tripFirstLocalDate prefers the creation context start date`.
19. `tripFirstLocalDate uses the earliest segment start, not the first listed`:
    segments listed out of date order.
20. `tripFirstLocalDate falls back to the earliest node in destination-local
    time`: a node whose UTC instant is on one date and whose Zanzibar-local
    date is the next date; expect the local date.
21. `tripFirstLocalDate returns null for a trip with no dates or nodes`.
22. `add booking calendar opens on the trip's first day`: trip starts 25 Dec
    2026, flight type, tap Date & Time; the `DatePickerDialog` widget's
    `initialDate` is 25 Dec 2026 (not today). Fails on `main`.
23. `hotel check-in calendar opens on the first day and check-out on the next
    day`: `initialDate` of the two `DatePickerDialog`s is 25 Dec and 26 Dec.
24. `calendar does not assert when the trip started in the past`: trip first
    day in 2020; the picker opens with no exception and `initialDate` is that
    day. This test passes on current `main` (no default date yet), so it guards
    rule 11 only: in the R17 sabotage commit, remove the bound widening and
    show this test fails.
25. `picking a different day overrides the default and keeps the time rule`.
26. `no trip dates falls back to tomorrow at 12:00`: assert the saved start's
    date is after today's date and the time is 12:00:00.000.

R17 proof (a guard that cannot fail is not a guard): after CI is green, push
one temporary commit that reverts only the production hunks (not the tests),
show that the tests named above fail in the `flutter` job, then revert that
commit so the branch ends with the real change. List test -> production line
in the PR description.

## 4. Stop rules

- Stop if the fix needs a server, schema or API change.
- Stop if any existing test needs its expected value changed (not its setup).
  Report the test and the old and new values.
- Stop if more than 6 existing tests need edits.
- Stop if `itinerary_screen.dart` filters nodes by span after grouping (see
  Part B rule 8).
- Stop if the trip's first day cannot be read from `ItineraryState` as
  described (field names or types differ). Report what you found.
- Stop if making the calendar open on the trip's month needs a change outside
  `add_booking_sheet.dart`, `date_scope.dart` and the tests.
- Do not touch `booking_parser.dart`, the Python backend, migrations, SPEC
  files, or any `docs/` file. The planning agent updates docs after merge.
- Do not add dependencies.
- Do not log booking data. Do not add any network call.

## 5. Gates

- `flutter analyze --no-fatal-infos`: no new errors or warnings (infos allowed
  as today).
- Full `flutter test` green in CI. The `flutter`, `android-compile`, `pytest`,
  `lint`, `postgres-proof` and `docker-build` jobs are green. `pytest` and the
  Python jobs are expected to be unchanged.
- ASCII only in any text you add to code comments and strings (R14).
- No hard-coded test counts in any text (R16).

## 6. PR

Branch `feat/booking-default-times-offspan-cards` from the base SHA you were
sent. One PR, two commits. Do not merge. In the PR description list: the
parts (A: default date and times, B: cards outside the span), the test -> production-line table, the R17 evidence, and any existing
test you had to touch. The owner re-checks both issues on the phone with the
next field APK built after this merges.
