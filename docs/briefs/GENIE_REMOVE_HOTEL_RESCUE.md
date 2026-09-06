# Genie Brief -- Retire the Hotel Rescue Shortcut

> Status: HISTORICAL, COMPLETED. The shortcut is removed while the offline
> cache and hotel driver-card action remain. Do not execute this brief again.

Canonical decisions:

- `docs/specs/SPEC-04-offline-vault.md`
- `docs/specs/SPEC-31-date-scoped-itinerary.md`
- Sep 4 Windows finding in `docs/AWAITING_VERIFICATION.md`
- Rules in `docs/ENGINEERING_RULES.md`, especially R1, R2, R8, R10, R16, R17

## Goal

Remove the dedicated Hotel Rescue AppBar shortcut and its duplicate selection
flow. The owner judged it useless during the Sep 4 Windows review. A hotel
booking already has the standard driver-card action, which opens the same
offline cached card without a second concept.

This is a deletion slice. Do not redesign Hotel Rescue, add a replacement
shortcut, or expand the full Offline Vault.

## Product invariants

Retain all of these:

1. `ItineraryController` writes successful trip loads to `cache_trip` and
   falls back to that cache on network failure.
2. Trip loads and booking saves continue to pre-cache `cache_place`.
3. Hotel bookings remain locked booking nodes.
4. The `Icons.directions_car_outlined` action on a hotel booking still opens
   `DriverCardScreen`.
5. Driver cards remain offline-capable, including local-script fields, map
   fallback, and cached fair-fare data.
6. Date headers and multi-night booking duration remain unchanged.

Remove all of these:

1. The `Icons.shield_outlined` Hotel Rescue action in the itinerary AppBar.
2. `openHotelRescue`, `HotelRescueSheet`, and `findHotelNode`.
3. `isHotelLikeNode` and `selectRescueStay`; they have no remaining production
   caller after the shortcut is removed.
4. Rescue-only tests and the obsolete laptop 6C/sabotage instructions.

## Files

### 1. `mobile/lib/features/itinerary/itinerary_screen.dart`

- Remove the import of `../rescue/hotel_rescue_sheet.dart`.
- Remove only the Hotel Rescue `IconButton` from `AppBar.actions`.
- Keep Add Booking, reroute status, alerts, timeline actions, and all other
  AppBar behavior unchanged.

### 2. Delete `mobile/lib/features/rescue/hotel_rescue_sheet.dart`

No compatibility wrapper or dead redirect. There is no public route for this
sheet.

### 3. `mobile/lib/features/itinerary/date_scope.dart`

- Keep `ItineraryDayGroup` and `groupNodesByCalendarDate` unchanged.
- Delete `isHotelLikeNode` and `selectRescueStay`.
- Do not change date extraction, ordering, timezone behavior, or input
  mutation behavior.

### 4. Tests

Delete `mobile/test/features/rescue/hotel_rescue_test.dart`, but first move its
`TripState toJson and fromJson roundtrip cleanly` test into
`mobile/test/models_test.dart`. Add `dart:convert` there if needed. That
serialization guard belongs to the cache contract and must not disappear with
the rescue UI.

In `mobile/test/features/itinerary/date_scope_test.dart`, remove only the
`isHotelLikeNode` and `selectRescueStay` groups. Keep every calendar grouping
test.

In `mobile/test/spec31_widget_test.dart`, add:

1. `itinerary has no Hotel Rescue shortcut`
   - Pump an itinerary.
   - Assert `find.byIcon(Icons.shield_outlined)` finds nothing.
   - Assert `find.byTooltip('Hotel Rescue')` finds nothing.
2. `hotel booking keeps its driver card action`
   - Pump one hotel booking node.
   - Assert `find.byIcon(Icons.directions_car_outlined)` finds one widget.

These tests protect both halves of the decision: the duplicate path is gone,
and the useful offline path remains.

### 5. Runbook and living docs

- Remove the Hotel Rescue matcher sabotage step from
  `docs/briefs/LAPTOP_VERIFY.md`.
- Do not leave 6C listed as pending verification.
- After the code is removed, update `docs/PROJECT_STATUS.md` from
  `REMOVAL DECIDED` to `REMOVED` and record the PR.

Do not rewrite historical briefs. Add a one-line superseded banner to
`docs/briefs/GENIE_SPEC_04_HOTEL_RESCUE.md` pointing here.

## Explicit non-goals

- No backend, schema, migration, API, signal, or scheduler changes.
- No multi-night booking work; it remains a separate product slice.
- No multi-city work.
- No `cache_vault`, passes, emergency grid, phrase pack, or global Vault route.
- No removal of `cache_trip`, `cache_place`, serialization, or offline fallback.
- No removal of the generic `AddBookingSheet.initialBookingType` parameter;
  it is booking input behavior, not a visible rescue feature.
- No profile or ErrorView overflow cleanup in this PR.

## Sabotage proofs

1. Re-add the Hotel Rescue AppBar `IconButton`.
   - `itinerary has no Hotel Rescue shortcut` must fail by name.
2. Remove the driver-card action from hotel booking cards.
   - `hotel booking keeps its driver card action` must fail by name.
3. Delete `TripState.toJson` or omit booking fields from the round trip.
   - `TripState toJson and fromJson roundtrip cleanly` must fail by name.

Restore each sabotage and rerun the named test. A red suite caused by another
test does not count as proof under R17.

## Proof checklist

From `mobile/`:

```text
dart format lib test
flutter analyze --no-fatal-infos
flutter test
```

From repository root:

```text
rg "openHotelRescue|HotelRescueSheet|findHotelNode|selectRescueStay|isHotelLikeNode" mobile
```

Expected: no matches.

Also run:

```text
rg "hotel_rescue_sheet" mobile
grep -rn '\\$' mobile/lib
pytest -q -ra
ruff check .
ruff format --check .
```

The first two searches must return no rescue import/reference and no escaped
Dart interpolation. Report passed and skipped tests with reasons.

## PR

- Branch: `refactor/remove-hotel-rescue`
- Title: `refactor(mobile): retire duplicate Hotel Rescue shortcut`
- Body: product decision, deleted paths, retained offline invariants, full test
  evidence, and the three named sabotage proofs.
