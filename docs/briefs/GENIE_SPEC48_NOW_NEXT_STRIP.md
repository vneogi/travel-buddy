# Genie brief: SPEC-48 slice 1, NOW / UP NEXT strip on the itinerary

Read this whole file before touching anything. It is the complete job.
If something here is unclear, stop and ask; do not guess and do not
widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA.

Owning spec: `docs/specs/SPEC-48-glanceable-timeline.md` (slice 1 only).
Parent: SPEC-45 (itinerary information architecture; the per-card NOW
badge is SPEC-45 R3 and stays as is). Flutter-only. No backend, no
SQLite schema change, no migration, no Cloud Run deploy, no network
call, no connectors (slice 2 waits for a trusted duration source).

## 0. Context

Owner device pause runs from 2026-11-16 night for about four days. CI is
the gate. The phone check waits until the owner returns.

Verified on `main` (re-verify in preflight):

1. `mobile/lib/features/itinerary/current_window.dart` has
   `nodeIsCurrentWindow(node, now)` (false for completed/skipped; true
   when `scheduledStart <= now < scheduledStart + durationMinutes`).
2. `mobile/lib/widgets/activity_card.dart` already shows a small `NOW`
   badge in the time rail when `nodeIsCurrentWindow` is true. This slice
   does NOT change `ActivityCard`.
3. `mobile/lib/core/destination_tz.dart` has `toDestinationLocal(utc,
   geoRegion)` and `formatDestinationTime(utc, geoRegion)`. Zanzibar and
   Nungwi are UTC+3.
4. `ItineraryScreen.build` (`itinerary_screen.dart`) body is a `Column`
   whose first child is `OfflineStatusRow(tripId: tripId)` (SPEC-56),
   followed by the progress bar, heads-up banner, schedule warnings,
   alerts, then the `Expanded` timeline. Schedule warnings and alerts
   scroll to a card with
   `context.go('/trip/$tripId?focus=${Uri.encodeQueryComponent(nodeId)}')`.
5. `state.nodes` is the full node list, from the network or from the
   saved copy when offline (`state.showingSaved`).
6. Home's "Now / Up next" card is driven by the backend
   (`featured_trip.actionable_stop`). Do not touch Home or the backend.
   Home may still show a hotel as "Now" during a stay; that is a known
   difference and out of scope here.

## 1. Goal

At the top of the itinerary, a compact strip shows what is happening now
and what is next, so the traveller does not have to scroll to find it.
Works from the saved itinerary offline. Tapping a row scrolls the
timeline to that card.

### Selection rules (pure function)

New file `mobile/lib/features/itinerary/now_next_strip.dart`:

```dart
typedef GlanceStops = ({TripNode? now, TripNode? next});
GlanceStops glanceStops(List<TripNode> nodes, DateTime nowUtc);
```

- Ignore nodes whose status is `completed` or `skipped`.
- Do not assume `nodes` is sorted; order by `scheduledStart`, ties by
  original list order.
- `now`: the earliest-starting node where `nodeIsCurrentWindow(node,
  nowUtc)` is true, EXCLUDING hotel bookings (`nodeKind == 'booking' &&
  bookingType == 'hotel'`), because a hotel window spans the whole stay.
- `next`: the earliest-starting node with `scheduledStart` strictly
  after `nowUtc`, that is not `now`. Hotel bookings ARE allowed here
  (check-in is a useful "next").
- Both may be null. No look-ahead limit (before the trip, `next` is the
  first stop).

### Time labels (pure functions, same file)

- `String glanceNowTime(TripNode node)` returns `until HH:MM`, end time
  (`scheduledStart + durationMinutes`) in destination-local via
  `formatDestinationTime(end, node.geoRegion)`.
- `String glanceNextTime(TripNode node, DateTime nowUtc)` returns
  `HH:MM` when the node's destination-local date equals the
  destination-local date of `nowUtc` (both converted with
  `node.geoRegion`); otherwise `Www D Mmm, HH:MM`, for example
  `Mon 28 Dec, 10:00`. Add a small private weekday/month table in this
  file (do not import the private helpers from `activity_card.dart`).

### Clock

```dart
final glanceClockProvider =
    Provider<DateTime Function()>((ref) => () => DateTime.now().toUtc());
```

Tests override it. The strip reads it on every build.

### Widget

`NowNextStrip` (`ConsumerStatefulWidget`), constructor
`NowNextStrip({super.key, required List<TripNode> nodes, required
ValueChanged<String> onFocusNode})`.

- Computes `glanceStops(nodes, clock())` in `build`.
- Renders nothing (`SizedBox.shrink()`) when both are null.
- Otherwise a `Column` keyed `Key('glance_strip')` with up to two rows:
  - NOW row, key `Key('glance_now_row')`: a small badge with text `NOW`
    (same look as the card badge: `AppColors.accent` background, white
    w700 caption), then the venue name and `glanceNowTime`.
  - UP NEXT row, key `Key('glance_next_row')`: badge text `UP NEXT`
    (muted outline or `AppColors.primaryLight` background; existing
    tokens only), then the venue name and `glanceNextTime`.
- Name and time in ONE `Text.rich` per row (name span in
  `AppTypography.label`, time span muted), `maxLines: 2`,
  `overflow: TextOverflow.ellipsis`. This matters: existing tests use
  `find.text(venueName)` with `findsOneWidget` on the itinerary, and a
  plain `Text(venueName)` in the strip would double those matches.
- Each row is an `InkWell` with min height 44dp, `onTap` calls
  `onFocusNode(node.nodeId)`. Wrap each row in `Semantics(button: true,
  label: ...)` with label `Now: <venueName>, until HH:MM` or
  `Up next: <venueName>, <glanceNextTime>`; exclude child semantics so
  the reader says it once.
- Refresh: a `Timer.periodic(const Duration(minutes: 1), (_) =>
  setState(() {}))` started in `initState` and cancelled in `dispose`,
  plus `WidgetsBindingObserver` that calls `setState` on
  `AppLifecycleState.resumed` (same observer pattern as
  `OfflineStatusRow` in `offline_readiness.dart`). Remove the observer
  and cancel the timer in `dispose`.
- Compact: horizontal padding `AppSpacing.base`, vertical
  `AppSpacing.xs`; no card shadow. Total height with both rows must stay
  around 100dp at normal text scale so the timeline stays visible.

### Wire-up

In `itinerary_screen.dart`, insert directly after
`OfflineStatusRow(tripId: tripId),`:

```dart
NowNextStrip(
  nodes: state.nodes,
  onFocusNode: (nodeId) => context.go(
    '/trip/$tripId?focus=${Uri.encodeQueryComponent(nodeId)}',
  ),
),
```

Nothing else in `itinerary_screen.dart` changes. Known limit (accept,
do not fix): tapping the same row twice after scrolling away does not
re-scroll, because the timeline skips an already-focused id.

## 2. Preflight

1. `git fetch origin`. Work from the base SHA in the message that sent
   this brief.
2. Confirm section 0 items 1 to 5. If any differs, stop and report.
3. Confirm `origin/feat/spec48-now-next-strip` does not exist, and that
   `glanceStops` / `NowNextStrip` / `glance_strip` do not appear under
   `mobile/lib`.
4. Branch: `feat/spec48-now-next-strip`.

## 3. Read before editing

- `docs/specs/SPEC-48-glanceable-timeline.md`
- `docs/ENGINEERING_RULES.md` R14, R16, R17
- `mobile/lib/features/itinerary/current_window.dart`
- `mobile/lib/core/destination_tz.dart`
- `mobile/lib/features/itinerary/offline_readiness.dart` (observer
  pattern, provider style)
- `mobile/lib/features/itinerary/itinerary_screen.dart` (build body)
- `mobile/lib/widgets/activity_card.dart` (badge look only)
- `mobile/test/spec56_offline_readiness_test.dart` (in-memory DB,
  offline itinerary harness, teardown order)

## 4. Files you may touch

- `mobile/lib/features/itinerary/now_next_strip.dart` (new)
- `mobile/lib/features/itinerary/itinerary_screen.dart`: the import and
  the one inserted widget from section 1. Nothing else.
- `mobile/test/spec48_now_next_test.dart` (new)

Nothing else. No `ActivityCard` change, no Home change, no router
change, no notifier change, no docs, no backend, no `pubspec`.

## 5. Implementation notes

- All times in UTC internally; convert only for display.
- No `DateTime.now()` inside `glanceStops` or the label functions; the
  widget passes `clock()`.
- Text must wrap or ellipsize; no horizontal overflow at 360dp wide and
  2.0 text scale with a 60-character venue name.
- Do not add a new color or text style; existing tokens only.

## 6. Tests

`mobile/test/spec48_now_next_test.dart`, exact names. Use
`DateTime.utc(...)` fixtures in December 2026 with
`geoRegion: 'zanzibar_tanzania'`.

Pure (`test`):

1. `picks the in-window stop as now`
2. `skipped and completed stops are never now or next`
3. `hotel stay is never now but check-in can be up next`
4. `next is the earliest stop after now from unsorted input`
5. `overlapping windows pick the earliest start as now`
6. `after the last stop both are null`
7. `labels are destination-local` (node 2026-12-27 07:00Z, 60 min,
   now 2026-12-27 07:30Z: `glanceNowTime` is `until 11:00`; a node at
   2026-12-27 12:00Z gives `glanceNextTime` `15:00`; a node at
   2026-12-28 07:00Z gives `Mon 28 Dec, 10:00`)

Widget (`testWidgets`; pump `NowNextStrip` in a `ProviderScope` with
`glanceClockProvider` overridden, inside `MaterialApp`/`Scaffold`):

8. `strip shows NOW and UP NEXT rows with names and times` (find by
   key and `find.textContaining`)
9. `strip is hidden when there is no now and no next`
10. `tapping a row reports that node id`
11. `strip moves on when the clock passes the current stop end` (mutable
    clock variable; advance it past the end; `tester.pump(const
    Duration(minutes: 1))`; NOW row gone or showing the next stop)
12. `no overflow at 360dp and 2.0 text scale with a long name`
13. `rows are 44dp buttons with Now and Up next semantics labels`

Integration (`testWidgets`, reuse the spec56 offline itinerary harness
pattern: in-memory `OfflineDatabase`, cached trip, network load fails):

14. `itinerary shows the strip from the saved copy when offline` (clock
    overridden to inside a cached node's window; `glance_now_row` found)

Teardown: same order as `spec46_what_now_test.dart` /
`spec56_offline_readiness_test.dart` (close listeners while mounted,
then dispose the container, then close the DB). The periodic timer must
be cancelled by `dispose`; a pending-timer failure means it was not.

## 7. R17

Run each, confirm the named test fails, then restore and confirm green:

A. Remove the hotel exclusion from `now`: test 3 fails.
B. Drop the completed/skipped filter: test 2 fails.
C. Remove the periodic timer: test 11 fails.
D. Format with `toLocal()` instead of destination time: test 7 fails
   (CI runs in UTC).

## 8. Stop rules

Stop and ask if:

- you need any file outside section 4;
- an existing test needs an assertion changed;
- you want to change `ActivityCard`, Home, the notifier, the router, or
  the backend;
- you want travel time, distance, or any estimate in the strip;
- you want a network call or a new cache read.

## 9. Gates

```
cd mobile && flutter analyze && flutter test
git diff --check
```

`flutter analyze` 0 issues (infos as today), `flutter test` all passed.
ASCII only in any text you add. Do not add `SPEC-NN` references except
to numbers with a file under `docs/specs/`.

If you have no Flutter SDK, say so and rely on CI. Do not install
Flutter without the owner's approval.

## 10. Delivery

One commit on `feat/spec48-now-next-strip`:
`feat: SPEC-48 NOW and UP NEXT strip on the itinerary`.
Push and verify the remote SHA. Do not merge. No `gh`. No APK build or
Cloud Run deploy.

## 11. Report

1. Base SHA.
2. Branch and remote SHA.
3. `flutter analyze` / `flutter test` last lines (or "no Flutter, CI only").
4. `git diff --check` result.
5. Files touched, with +/- counts.
6. R17 A to D results (or "not observed, CI only").
7. Confirmation that `ActivityCard`, Home, notifier, router and backend
   are unchanged.
8. Anything you were unsure about.

## 12. Owner device check (after merge; waits until phone returns)

1. Open the Tanzania trip before it starts: strip shows only `UP NEXT`
   with the first stop and `Sat 26 Dec, HH:MM` style time (Zanzibar
   time).
2. Tap the row: timeline scrolls to that card.
3. Airplane mode, reopen the trip from the saved copy: strip still shows.
4. Largest system font: strip wraps or ellipsizes, timeline still
   visible below it.
5. On the trip (in Zanzibar): during a stop, `NOW ... until HH:MM` plus
   `UP NEXT`; hotel never shows as NOW.
