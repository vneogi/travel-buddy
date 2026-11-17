# Genie brief: SPEC-52 slice 1, existing-trip date markers verification

Read this whole file before touching anything. It is the complete job.
If something here is unclear, stop and ask; do not guess and do not
widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA.

Owning spec: `docs/specs/SPEC-52-existing-trip-date-markers.md`, slice 1
(verification checklist). Parents: SPEC-40 (guided create, date step),
SPEC-36 (corridor date form). Flutter-only. No backend, no
`TripSummary` change, no migration, no new network call, no new
package, no change to the create command.

Slice 1 is a checklist against main. Change code only where a gap is
found. This brief names the gaps already found by the planning agent.

## 0. Context

F3 landed on main (`1cb9318`, PR #238): an overlap marker under the day
number in the existing-trip range picker, a non-blocking review note on
the create-trip review step, and the same picker on the corridor date
form. Markers come from `occupiedDaysFromTrips(home.trips)`. Those trips
are the home snapshot, which is also cached in `cache_trip_list` for
offline use.

Verified on the base SHA by the planning agent (re-verify in preflight):

1. `mobile/lib/features/create_trip/existing_trip_dates.dart`:
   `occupiedDaysFromTrips` skips a trip with a null bound, swaps reversed
   bounds, and converts with `toDestinationLocal` before taking the
   date-only day. It does not widen `TripSummary`.
2. `mobile/lib/widgets/existing_trip_date_range_picker.dart`: occupied
   days get a 4dp dot keyed `marker-<iso>` inside the day cell keyed
   `day-<iso>`. The picker has NO `Semantics` label today, so a screen
   reader cannot tell an occupied day from a free one. This is a gap
   against SPEC-52 acceptance ("markers ... have accessible semantics").
3. `mobile/lib/features/home/home_controller.dart`: on network failure
   the home snapshot is rebuilt from `cache_trip_list` with
   `fromCache: true`. So cached summaries do feed markers. No test
   proves this path. That is a test gap.
4. Existing tests that MUST stay green unchanged:
   `mobile/test/features/create_trip/existing_trip_dates_test.dart`
   (6 tests) and `mobile/test/widgets/existing_trip_date_range_picker_test.dart`
   (4 tests). Do not change their assertions.

## 1. Goal

Close the two gaps above and prove each SPEC-52 acceptance line with a
named test. Do not add UI beyond the accessible label.

## 2. Preflight

1. `git fetch origin`. Work from the base SHA in the message that sent
   this brief.
2. Confirm section 0 items 1 to 4. If any differs, stop and report.
3. Confirm `origin/feat/spec52-date-marker-verify` does not exist.
4. Branch: `feat/spec52-date-marker-verify`.

## 3. Read before editing

- `docs/specs/SPEC-52-existing-trip-date-markers.md` (whole file)
- `docs/briefs/GENIE_F3_EXISTING_TRIP_DATE_MARKERS.md` (the F3 rules,
  including the 2026-11-15 activity-span amendment)
- `docs/ENGINEERING_RULES.md` R14, R16, R17
- `mobile/lib/features/create_trip/existing_trip_dates.dart`
- `mobile/lib/widgets/existing_trip_date_range_picker.dart` (whole file)
- `mobile/lib/data/models.dart`: `TripSummary` and `HomeSnapshot`
  (`fromJson`, the `fromCache` and `cachedAt` parameters, and the JSON
  keys `TripSummary.fromJson` parses)
- `mobile/lib/features/home/home_controller.dart` (cache fallback)
- The two existing F3 test files above

## 4. Files you may touch

- `mobile/lib/widgets/existing_trip_date_range_picker.dart`: the
  accessible label on occupied day cells only (section 5.1).
- `mobile/test/features/create_trip/existing_trip_dates_test.dart`:
  ADD tests only (section 6, group A).
- `mobile/test/widgets/existing_trip_date_range_picker_test.dart`: ADD
  tests only (section 6, group B).
- `mobile/test/features/create_trip/spec52_cached_markers_test.dart`
  (new; section 6, group C).

Nothing else. No `TripSummary`, no `_summarize_trip`, no backend, no
`create_trip_screen.dart`, no `corridor_date_form.dart`, no
`home_controller.dart`, no router, no docs, no `pubspec`.

## 5. The change

### 5.1 Accessible label (the one code change)

In `_dayCell`, when `occupied` is true, wrap the day cell in a
`Semantics` whose label is the day plus the covered state, for example
`10 December 2026, covered by another trip`. Build the day text from
the existing month and weekday helpers in the file, or from
`${day.day} ${_monthNames[day.month - 1]} ${day.year}`. Do not add a
package. Free days keep their current semantics (no label change).

Keep the existing `Key('day-<iso>')` and `Key('marker-<iso>')` finders
working. The marker dot stays visible. The overlap is still selectable.
Do not disable any day.

### 5.2 Nothing else changes in code

If preflight or the tests show another gap, stop and report it. Do not
fix it in this slice unless it is a one-line semantics or key fix inside
the picker file.

## 6. Tests

Use the exact names below. Each one proves one line of the SPEC-52
acceptance checklist.

### Group A: `existing_trip_dates_test.dart` (pure, add only)

1. `multiple_overlapping_trips_mark_each_day_once`: two trips covering
   Dec 10 to 12 and Dec 11 to 14 (Luang Prabang region) give exactly
   Dec 10 to 14 with set size 5.
2. `local_midnight_end_counts_the_local_day`: a Luang Prabang trip whose
   `endsAt` is `DateTime.utc(2026, 12, 12, 16, 59)` (23:59 local, Dec 12)
   includes Dec 12. A trip whose `endsAt` is `DateTime.utc(2026, 12, 12, 17)`
   (00:00 local, Dec 13) includes Dec 13.
3. `local_midnight_start_counts_the_local_day_tanzania`: a Zanzibar trip
   whose `startsAt` is `DateTime.utc(2026, 12, 26, 21)` (00:00 local,
   Dec 27) does NOT include Dec 26 and DOES include Dec 27.
4. `single_day_trip_marks_one_day`: start and end on the same local day
   give exactly that day.

### Group B: `existing_trip_date_range_picker_test.dart` (widget, add only)

5. `occupied_day_has_accessible_label`: the semantics label of
   `Key('day-2026-12-10')` contains `covered by another trip`. The label
   of `Key('day-2026-12-12')` (free) does not contain it. Use
   `tester.getSemantics` or `find.bySemanticsLabel`, and wrap with
   `tester.ensureSemantics()` and dispose the handle.
6. `occupied_day_with_time_of_day_still_marks_the_date`: pass
   `DateTime(2026, 12, 10, 15, 30)` in `occupiedDays` and expect
   `Key('marker-2026-12-10')` to be found. This is the test that fails
   if the picker stops normalising to date-only.
7. `overlapping_day_remains_selectable_and_range_returns`: tap Dec 9 then
   Dec 11 (both occupied-adjacent, Dec 10 and 11 occupied), tap confirm,
   and the returned range is Dec 9 to Dec 11.

### Group C: `spec52_cached_markers_test.dart` (new)

8. `cached_home_snapshot_drives_markers`: build a `HomeSnapshot` through
   `HomeSnapshot.fromJson(json, fromCache: true, cachedAt: <utc>)` with
   one trip in the JSON shape `TripSummary.fromJson` already parses
   (read `models.dart` for the keys). Assert
   `occupiedDaysFromTrips(snapshot.trips)` equals the expected days, and
   that `snapshot.fromCache` is true.
9. `cached_snapshot_markers_render_in_picker`: pump
   `showExistingTripDateRangePicker` with those cached days and expect
   `Key('marker-<iso>')` on the expected day.
10. `cached_empty_trip_list_shows_no_markers`: a cached snapshot with an
    empty `trips` list and a trip with a null `endsAt` gives an empty
    set and no marker finders.

No test may open a real socket. No test may call a repository.

## 7. R17

Run each, confirm the named test fails, then restore and confirm green.
Dart R17 is observed on the owner's Windows run. Genie does not have
the Flutter SDK, so these are CI and owner-run only:

A. Remove the `Semantics` label from occupied cells: test 5 fails.
B. Use the UTC calendar day instead of `toDestinationLocal` in
   `occupiedDaysFromTrips`: test 2 fails.
C. Stop normalising occupied days to date-only in
   `existing_trip_date_range_picker.dart` (the `occupiedDays:` mapping):
   test 6 fails.

## 8. Stop rules

Stop and ask if:

- you need any file outside section 4;
- an existing assertion must change to make a new test pass;
- you want to widen `TripSummary` with create-form dates or change
  `_summarize_trip`. That is the open owner decision (section 9), not
  this slice;
- you want a trip name in the overlap note. `TripSummary` has no name
  field, and that needs its own decision;
- you want a new package, network call, cache read or migration.

## 9. Explicitly out of scope (owner decision, not Genie's)

SPEC-52 "Remainder" also asks whether the trip summary should show the
activity span or the create-form dates. The F3 amendment (2026-11-15)
already chose the activity span for the markers. Showing create-form
dates means adding fields to `TripSummary` and the server projection,
which the F3 brief put in a later SPEC-26 projection slice. Do not start
that. The planning agent will raise it with the owner.

## 10. Gates

```
cd mobile && flutter analyze && flutter test
git diff --check
```

`flutter analyze` 0 issues (infos as today), `flutter test` all passed.
ASCII only in any text you add. Do not add `SPEC-NN` references except
to numbers with a file under `docs/specs/`.

If you have no Flutter SDK, say so and rely on CI. Do not install
Flutter without the owner's approval.

## 11. Delivery

One commit on `feat/spec52-date-marker-verify`:
`feat: SPEC-52 date marker verification (accessible label, boundary and cache tests)`.
Push and verify the remote SHA. Do not open a PR. Do not merge. No `gh`.
No APK build or Cloud Run deploy.

## 12. Report

1. Base SHA.
2. Branch and remote SHA.
3. `flutter analyze` / `flutter test` last lines (or "no Flutter, CI only").
4. `git diff --check` result.
5. Files touched, with +/- counts.
6. The SPEC-52 acceptance checklist as a table: each acceptance line
   and the test name(s) that prove it. Mark any line with no test as
   a gap.
7. R17 A to C results (or "not observed, CI and owner run only").
8. Confirmation that `TripSummary`, the backend, the create command,
   `home_controller.dart`, the router and docs are unchanged.
9. Anything you were unsure about.

## 13. Owner device check (after merge; waits until phone returns)

1. Create a trip whose date range overlaps an existing one. Day cells
   with a dot read as "covered by another trip" in TalkBack or
   VoiceOver. The range can still be chosen and created.
2. Turn on airplane mode, open create-trip dates again. Markers still
   show from the cached home list.
3. Corridor date form: the same markers appear for each city range.
