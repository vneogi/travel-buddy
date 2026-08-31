# Genie Brief -- SPEC-31 Date-Scoped Itinerary and Stay Rescue

> Status: READY TO IMPLEMENT.
> Base on `origin/main` at or after `83c825f`.
> Read `docs/specs/SPEC-31-date-scoped-itinerary.md` first.
> One client-only PR. Do not mix booking edit/delete into this branch.

## Goal

1. Render the existing itinerary as one timeline with calendar-date section
   headers.
2. Make Hotel Rescue choose the active or most useful adjacent stay rather than
   the first hotel-like node.

No backend, migration, wire, scheduler, persistence, or dependency change.

## Required implementation

### 1. Pure helper

Create `mobile/lib/features/itinerary/date_scope.dart`.

Add an immutable day-group value and pure functions equivalent to:

```text
ItineraryDayGroup(date, nodes)
groupNodesByCalendarDate(List<TripNode>)
isHotelLikeNode(TripNode)
selectRescueStay(List<TripNode>, DateTime now)
```

Date key:

```text
DateTime(
  node.scheduledStart.year,
  node.scheduledStart.month,
  node.scheduledStart.day,
)
```

Do not call `toLocal()` or `toUtc()` before taking those fields.

Grouping is a sequential fold over the server-provided order. Do not sort or
mutate the input. Preserve node order within every group.

Stay occupancy is `[start, end)`, where
`end = scheduledStart + durationMinutes`.

Selection precedence:

1. active stay, choosing latest start if active stays overlap,
2. earliest future stay,
3. most recently ended elapsed stay,
4. null.

Hotel-like means `bookingType == 'hotel'` or the existing case-insensitive
hotel/resort/hostel/villa/guesthouse name fallback.

### 2. Date headers in the timeline

Update `mobile/lib/features/itinerary/itinerary_screen.dart`.

- Change AppBar title from `Your Day` to `Your Trip`.
- Group `state.nodes` through the new helper.
- Render one normal `ListView` containing a date header followed by the group's
  existing ActivityCards.
- A header must include weekday, day, and month. Include year so a New Year trip
  is unambiguous.
- Use Flutter/intl formatting already available; add no package.
- Preserve the existing ActivityCard construction, AnimatedSwitcher, and full
  key expression, including loved and node-outcome state.
- Preserve `nextNode` as the next node in the original full itinerary, including
  across a date boundary. Do not reinterpret it as the next node in one group.

Prefer a flattened list of header/row view items or an indexed builder over
nested non-scrollable lists. Do not introduce nested scrolling or a sticky
header dependency.

### 3. Date-aware Hotel Rescue

Update `mobile/lib/features/rescue/hotel_rescue_sheet.dart`.

- Replace `findHotelNode` first-match behavior with `selectRescueStay`.
- Inject `now` into the pure selection path for tests.
- Production `openHotelRescue` supplies `DateTime.now()` once.
- Keep driver-card navigation and the no-hotel empty sheet unchanged.
- Keep keyword fallback.

If compatibility requires retaining `findHotelNode`, make it a thin wrapper
whose behavior is explicitly date-aware and accepts `now`. Do not leave a
first-match production path.

## Files expected

- new `mobile/lib/features/itinerary/date_scope.dart`
- `mobile/lib/features/itinerary/itinerary_screen.dart`
- `mobile/lib/features/rescue/hotel_rescue_sheet.dart`
- focused pure and widget tests

Do not touch Python, SQL, pubspec, generated platform folders, localization
output, SPEC-30 outcome persistence, or booking mutation code.

## Required tests

### Pure date grouping

- one calendar date -> one group,
- multiple dates -> one group per contiguous date,
- input and within-day order unchanged,
- input list not mutated,
- Dec 31 and Jan 1 remain separate,
- an offset-bearing `DateTime` is grouped from its represented fields without a
  local/UTC conversion.

### Pure stay selection

- active stay beats elapsed and future,
- overlapping active stays choose latest start,
- no active stay chooses earliest future,
- no active/future chooses latest-ended elapsed,
- a 46-hour hotel is active on the second day,
- booking type hotel and every current name fallback are recognized,
- no hotel returns null,
- list order does not affect the selected stay.

### Widget and integration

- AppBar says `Your Trip`,
- two dates show two headers and all cards,
- date header includes year,
- ActivityCard key/state wiring survives: love and node outcome update only the
  intended node,
- the final node of one date still receives the first node of the next date as
  `nextNode`,
- timeline and Hotel Rescue do not overflow at 800x600.

Extend `mobile/test/features/rescue/hotel_rescue_test.dart` rather than replacing
its existing empty-state and fallback coverage.

## Sabotage proofs

Break each temporarily, name the failing test, then restore. Do not commit
sabotage.

1. Convert `scheduledStart` with `toUtc()` before grouping: offset-date test
   fails.
2. Sort nodes in the grouping helper: input-order test fails.
3. Revert rescue to first hotel: shuffled two-hotel selection test fails.
4. Treat hotel end as inclusive: exact-checkout-boundary test fails.
5. Reset `nextNode` at each date boundary: cross-date next-node test fails.
6. Remove the SPEC-30 outcome part of the card key: outcome wiring test fails.

## Verification

From `mobile/`:

```text
dart format --output=none --set-exit-if-changed <changed Dart files only>
flutter analyze --no-fatal-infos
flutter test
```

From repository root:

```text
pytest -q -ra
git diff --check
```

Do not run repository-wide `dart format`; it creates unrelated churn under the
current SDK.

## Completion report

Return:

- branch and SHA,
- exact files changed,
- date and occupancy rules as implemented,
- focused and full test results,
- all sabotage proofs,
- explicit confirmation that Python, SQL, API shape, `day_index`, and
  `trip_stay` were untouched.

Do not open a PR until review is requested.
