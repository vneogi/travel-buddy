# Genie brief: F3 -- existing-trip markers on the create-trip date picker

> Amendment 2026-11-15: activity-span markers only (node min/max on
> `TripSummary`), destination-local date-only via `toDestinationLocal`.
> If you started from an older copy of this brief, re-fetch `origin/main`
> and re-read this file before writing more code.


Read this whole file before touching anything. It is the complete job.
If something here conflicts with your memory of an earlier brief, this
file wins. If something here is unclear, stop and ask; do not guess and
do not widen scope.

## 0. Context in one paragraph

Owner device finding F3 (2026-11-14, `docs/UX_BACKLOG.md`): when creating
a second trip, the date picker shows no trace of the first. Wanted:
calendar-invite style markers on days already covered by another trip;
the markers never block creating an overlapping trip. Stock
`showDateRangePicker` cannot decorate individual days, so this slice
adds a small custom range calendar and wires it into guided create
(SPEC-40) and the corridor date form (SPEC-36). Data comes from the
local trips list already on `HomeSnapshot` / the offline trip-list
cache -- no new endpoint.

Important data fact (do not "fix" in this slice): `TripSummary.startsAt`
and `endsAt` are the min/max of scheduled node times from
`_summarize_trip` in `routers/trip_router.py`, not the traveller's
chosen create dates. Sparse generation only fills a starter set of
days, so a longer trip can under-mark empty days. Product decision for
F3: mark the **activity span** the list already exposes. Honest and
offline. Widening `TripSummary` with create-date fields is a later
remainder (SPEC-26 projection), not this slice.

## 1. Goal and the properties that matter

1. On the create-trip dates step, the picker shows a month grid. Days
   covered by any existing trip (from the home trips list) carry a
   small marker under the day number. Selecting a range that overlaps
   those days is allowed.
2. The corridor date form uses the same picker for each city range.
3. The create-trip review step shows a non-blocking note when the
   chosen range overlaps an existing trip (for example
   `Overlaps with an existing trip on <dates>`). The Create button
   stays enabled.
4. Date comparison is destination-local date-only: for each trip,
   convert `startsAt` / `endsAt` with the existing
   `toDestinationLocal(utc, trip.geoRegion)` helper, then take
   `DateUtils.dateOnly`. Do not use raw UTC calendar days (an evening
   node can cross local midnight).
5. Trips with a null `startsAt` or null `endsAt` contribute no markers
   (including empty-node trips). That is expected under the activity-
   span decision above; do not invent dates.
6. No new Flutter packages. Material only. No backend, catalog, or
   CI changes. Do not widen `TripSummary` or edit `_summarize_trip`.

## 2. Preflight (do this first, stop if any check fails)

1. `git fetch origin`. Work from the `origin/main` SHA in the message
   that sent you this brief. If main has moved past it, continue from
   the newer main only if every file in step 2 is still present and
   F2 (`languagePriority` Tanzania rule) is on that main; otherwise
   stop.
2. Confirm these exist: this brief,
   `mobile/lib/features/create_trip/create_trip_screen.dart`,
   `mobile/lib/widgets/corridor_date_form.dart`,
   `mobile/lib/data/models.dart` (`TripSummary`),
   `mobile/lib/features/home/home_controller.dart`,
   `docs/UX_BACKLOG.md` (F3 section), `docs/ENGINEERING_RULES.md`.
3. Confirm `mobile/lib/features/create_trip/existing_trip_dates.dart`,
   `mobile/lib/widgets/existing_trip_date_range_picker.dart`,
   `mobile/test/features/create_trip/existing_trip_dates_test.dart`,
   `mobile/test/widgets/existing_trip_date_range_picker_test.dart`,
   and `origin/feat/f3-existing-trip-date-markers` do not exist.
4. Confirm create-trip still injects dates via
   `DateRangePickerBuilder` / `showDateRangePicker`, and
   `CorridorDateForm` still calls `showDateRangePicker` directly.
5. Branch from that main: `feat/f3-existing-trip-date-markers`.

## 3. Read before editing (read only)

- `docs/ENGINEERING_RULES.md` R14, R16, R17.
- `docs/UX_BACKLOG.md` F3 section (direction and constraints).
- `create_trip_screen.dart`: `DateRangePickerBuilder`, `_DatesStep`,
  `_ReviewStep`, how `HomeSnapshot` is loaded.
- `corridor_date_form.dart`: `_pickRange`.
- `TripSummary` in `models.dart`.
- Existing create-trip / corridor tests under `mobile/test/` for
  patterns (fake home snapshot, `datePickerBuilder` injection).

## 4. Files you may touch

- `mobile/lib/features/create_trip/existing_trip_dates.dart` (new)
- `mobile/lib/widgets/existing_trip_date_range_picker.dart` (new)
- `mobile/lib/features/create_trip/create_trip_screen.dart`
- `mobile/lib/widgets/corridor_date_form.dart`
- `mobile/test/features/create_trip/existing_trip_dates_test.dart` (new)
- `mobile/test/widgets/existing_trip_date_range_picker_test.dart` (new)
- `mobile/test/features/create_trip/create_trip_overlap_note_test.dart`
  (new; only if the review-note proof does not fit cleanly elsewhere)

Nothing else. Do NOT change: backend, catalogs, `pubspec.yaml`,
existing tests except by adding new files, home screen layout beyond
passing trips into the form if required, SPEC docs, briefs.

Do not implement F1 (fold corridor into create). Do not block overlaps.

## 5. The change

ASCII only. Keep the calendar visually quiet: one composition, no card
chrome, no floating badges. Marker = a small filled circle under the
day number (about 4 logical pixels). Selected range uses the theme
primary the same way Material range selection usually does.

### 5.1 Pure helpers: `existing_trip_dates.dart`

Public API (exact names):

    /// Inclusive date-only days covered by [trips].
    Set<DateTime> occupiedDaysFromTrips(Iterable<TripSummary> trips)

    /// True when [range] shares any date-only day with [occupied].
    bool rangeOverlapsOccupied(DateTimeRange range, Set<DateTime> occupied)

    /// Short, non-blocking review copy. Empty string when no overlap.
    String overlapReviewNote(DateTimeRange range, Set<DateTime> occupied)

Rules for `occupiedDaysFromTrips`:

- Skip a trip when `startsAt` or `endsAt` is null.
- For each kept trip, convert both bounds with
  `toDestinationLocal(..., trip.geoRegion)`, then `DateUtils.dateOnly`.
- Walk every calendar day from local start through local end inclusive
  (swap if reversed). Store days as `DateUtils.dateOnly` values.
- Document in the helper file comment that these are activity-span days
  from the list projection, not create-form dates.

`overlapReviewNote` when overlapping: a single sentence starting with
`Overlaps with an existing trip` and including a compact date span of
the overlap (use `yyyy-mm-dd` style, ASCII only). When not overlapping:
`''`.

### 5.2 Widget: `existing_trip_date_range_picker.dart`

    Future<DateTimeRange?> showExistingTripDateRangePicker({
      required BuildContext context,
      required DateTime firstDate,
      required DateTime lastDate,
      DateTimeRange? initialDateRange,
      Set<DateTime> occupiedDays = const {},
    })

Behaviour:

- Presents a modal bottom sheet (or dialog) with a month title, previous
  / next month controls, a 7-column day grid (Mon-Sun or the locale
  default -- pick one and keep it stable in tests by fixing the locale
  to `en_US` in the test binding).
- First tap sets the tentative start; second tap on a later-or-equal day
  completes the range and enables a Confirm button. Tapping an earlier
  day resets the start. A Cancel control dismisses with null.
- Occupied days always show the marker. They remain tappable.
- Days outside `[firstDate, lastDate]` are not selectable (dimmed).
  Occupied markers do not dim them further for overlap reasons.
- Confirm returns a `DateTimeRange` with date-only start and end.

Keep the widget under ~250 lines. No animation library. Prefer
`showModalBottomSheet` so it matches the corridor form sheet feel.

### 5.3 Wire create-trip

- When building `_DatesStep`, pass the occupied set derived from
  `home.trips` (the same `HomeSnapshot` the wizard already has).
- Default picker (when `datePickerBuilder` is null) must call
  `showExistingTripDateRangePicker` with that occupied set, not stock
  `showDateRangePicker`.
- Keep `datePickerBuilder` for tests: if provided, still use it (tests
  that inject a fake picker stay green).
- On `_ReviewStep`, if `_dateRange` overlaps the occupied set, show the
  `overlapReviewNote` text under the date line. Style: bodySmall /
  secondary colour. Never disable Create because of overlap.

### 5.4 Wire corridor date form

- Add an optional `List<TripSummary> existingTrips` (default empty) to
  `CorridorDateForm`.
- Home's `_showCorridorDateForm` passes `snapshot.trips`.
- `_pickRange` uses `showExistingTripDateRangePicker` with the occupied
  set from those trips. Corridor segment-to-segment overlap rules
  stay exactly as they are today (still enforced by `_validate`).

## 6. Tests

### 6.1 `existing_trip_dates_test.dart` (pure Dart, no pump)

Exact names:

1. `occupiedDaysFromTrips_includes_every_inclusive_day`
2. `occupiedDaysFromTrips_skips_trips_missing_a_bound`
3. `occupiedDaysFromTrips_swaps_reversed_bounds`
4. `rangeOverlapsOccupied_true_on_shared_day_false_otherwise`
5. `overlapReviewNote_empty_when_clear_and_non_empty_when_overlap`

### 6.2 `existing_trip_date_range_picker_test.dart` (widget)

Exact names:

1. `occupied_day_shows_a_marker`
2. `occupied_day_is_still_selectable`
3. `confirming_a_range_that_covers_an_occupied_day_returns_the_range`
4. `cancel_returns_null`

Use `Key`s on day cells (`Key('day-YYYY-MM-DD')`) and on Confirm /
Cancel so tests are stable. Fix the clock with a known `firstDate` /
visible month so the grid is deterministic.

### 6.3 Review note (create trip)

One widget test that pumps `CreateTripScreen` (or the review step) with
a home snapshot containing one existing trip and a pre-set overlapping
`_dateRange` via the public test seams you already have / a small
`@visibleForTesting` setter if required. Assert the overlap note is
on screen and the Create control is enabled. If the screen has no clean
seam without a large rewrite, put the proof in a tiny harness that
builds only `_ReviewStep` -- but prefer not to make `_ReviewStep`
public; a `@visibleForTesting` constructor or package-private export
is fine. Stop and report rather than ripping the wizard apart.

### 6.4 Existing suites

Do not edit existing tests. They must stay green. The create-trip path
that injects `datePickerBuilder` must still bypass the new UI.

## 7. R17 sabotage (required)

A. Make `occupiedDaysFromTrips` always return `{}`. Under that sabotage
   `occupiedDaysFromTrips_includes_every_inclusive_day` and
   `occupied_day_shows_a_marker` must fail. Restore.
B. Make `rangeOverlapsOccupied` always return false. Under that
   sabotage `rangeOverlapsOccupied_true_on_shared_day_false_otherwise`
   must fail. Restore.

Throwaway in-memory plugins or temp copies are fine when in-place edits
are blocked. No repo file may keep the sabotage. Report hashes of the
helper file before A and after the last restore.

Dart tests cannot run on your machine (no Flutter SDK). Say so; the
owner runs them on Windows. You still write them.

## 8. Stop rules

Stop and report instead of improvising if:

- any preflight check fails;
- you need a new package, a backend change, or a file outside section 4;
- you are about to disable overlapping days or block Create on overlap;
- you are about to invent create dates, edit `_summarize_trip`, or widen
  `TripSummary`;
- you are about to implement F1 or edit SPEC files;
- an existing test fails for a reason related to this change and the
  fix would require editing that existing test -- stop and report.

## 9. Gates

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

ruff 0.16.3. Expected: zero pytest failures. Confirm touched Dart /
Python files are ASCII. Do not run Flutter (no SDK).

## 10. Out of scope

- Widening `TripSummary` / `_summarize_trip` with create-date fields
  (remainder after F3; needed for true booking-span markers on sparse
  multi-week trips)
- F1 single create entry / folding the corridor card into create
- Swahili catalog data (F2 data pass)
- Blocking overlaps, colour legends, multi-trip labels per day
- iOS / web polish beyond Material defaults
- Deploy, APK, any other backend change

## 11. Delivery

1. Commit on `feat/f3-existing-trip-date-markers` with:
   `F3: mark existing trips on the create-trip date picker`.
2. Push. Verify SHA via `git ls-remote origin feat/f3-existing-trip-date-markers`.
3. Do not merge. No `gh`. Reviewer opens the PR.

## 12. Report (exactly these fields)

1. Base `origin/main` SHA.
2. Branch name and pushed SHA (remote-verified).
3. `pytest` last line; every failing test (expected: none).
4. ruff / format / diff-check (ruff version).
5. Files touched with diff line counts.
6. How create-trip and corridor obtain the occupied set (one sentence each).
7. R17 A/B failures by name; hash confirmation.
8. Confirmation no package, backend, or existing test file has a diff.
9. Exact Flutter commands the owner should run on Windows.
10. Anything unsure or not done.
