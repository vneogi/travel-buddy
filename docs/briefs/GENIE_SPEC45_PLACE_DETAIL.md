# Genie brief: SPEC-45 operational place details (Flutter)

Read this whole file before touching anything. It is the complete job.
If something here conflicts with memory of an earlier brief, this file
wins. If something is unclear, stop and ask; do not guess and do not
widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA.

Owning spec: `docs/specs/SPEC-45-on-trip-visible-surface.md`, remainder
"operational place detail" (section 10). Card tap already opens
`ActivityDetailScreen` (`mobile/lib/features/activity_detail/activity_detail_screen.dart`,
wired from `itinerary_screen.dart` about line 984). This slice fills that
screen with sourced fields already on `TripNode`. It does not add a
route, a backend field, a catalog lookup, or a transfer card (SPEC-55
is parked until after Tanzania).

This slice is Flutter only. No backend change, no SQLite schema change,
no migration, no new dependency, no APK, no hosted deploy. The gate is
CI and owner Windows `flutter test`. Do not install Flutter without
owner approval.

## 0. Owner decisions (2026-11-23)

1. Use only fields already on the itinerary node. Do not add category,
   typical catalog dwell, or an Open/Closed computation from structured
   hours. Those need a backend change and are a later brief.
2. Transfer and arrival cards are out. SPEC-55 owns them and is parked.

## 1. Verified facts on `main` (re-verify in preflight; line numbers drift)

- Card body tap already calls `onTapDetails` (`activity_card.dart` about
  line 167). Tests: `mobile/test/spec45_friction_test.dart` "Card tap
  opens details" and `spec45_bottom_inset_test.dart`.
- `ActivityDetailScreen` today: AppBar title = `venueName`; a 200px
  placeholder hero; friendly neighbourhood via
  `friendlyMicroLocation(node.microLocation)` (omit if null; never the
  slug); `Hours: <openingHours>` if present; all vibe chips; Swap and
  Cancel for unlocked nodes; Move when `onMove` is set and the node is
  movable; "Locked reservation" for bookings. No Driver card, no Open in
  Maps, no Love, no slot or window, no dwell, no maps launch.
- `TripNode` (`mobile/lib/data/models.dart` about line 35) already has:
  `venueName`, `venueId`, `microLocation`, `openingHours`, `vibeTags`,
  `lat`/`lng`, `durationMinutes`, `slotName`, `timeWindow`, `geoRegion`,
  `nearestLandmark`, `namesLocal`, `nodeKind`, `bookingType`,
  `isLocked`, `status`. It does not have category, typical catalog
  dwell, or `openingHoursStructured`. Do not add them.
- Neighbourhood labels: `mobile/lib/features/itinerary/micro_location_label.dart`
  (`friendlyMicroLocation`). Reuse it. Tests already assert
  `nam_phou_fountain` never appears.
- Driver card from the overflow: `context.push('/trip/$tripId/card/${node.venueId ?? node.venueName}')`
  (`activity_card.dart` about line 586). Reuse that exact path. The
  details screen is pushed as a `MaterialPageRoute`, so it has a
  `BuildContext` with the same GoRouter; preflight must confirm
  `GoRouterState.of(context).pathParameters['tripId']` is still set
  there. If it is not, stop and report; do not invent a tripId.
- Open in Maps on the driver card: `launchUrl` in
  `mobile/lib/features/driver_card/driver_card_screen.dart` about line
  328. Preflight: extract or reuse the maps-URL helper if one exists;
  if not, copy the same `launchUrl` call (coords when both lat and lng
  are set, else a search on `venueName`). Do not add a package.
- Love on the itinerary: overflow calls `onTapLoved` then the screen
  calls `emitUserLoved` (not awaited) and `markLoved`. Pass the same
  `onLoved` callback into the details screen. Do not enqueue a signal
  from the details screen itself.
- Slot display names already exist for cards (look for the window /
  slot label helper used on `ActivityCard`). Reuse; do not invent a
  second map.
- Existing tests of `ActivityDetailScreen`:
  `spec45_friction_test.dart` (friendly micro_location),
  `spec42_move_test.dart` (Move on detail),
  `spec45_bottom_inset_test.dart` (card tap opens the screen). Do not
  change their expected values.

## 2. Change

Fill `ActivityDetailScreen` (same class, same file, same constructor
plus the extra callbacks below). Keep it a `StatelessWidget` if
possible; a `StatefulWidget` is allowed only for the Love visual.

Layout, top to bottom, after the AppBar:

1. Keep the 200px placeholder hero. Do not load a photo.
2. Neighbourhood: the existing friendly label, omitted when null.
3. Slot or window: if `timeWindow` is set, the window label already
   used on cards (`Morning` / `Afternoon` / `Whole day`); else if
   `slotName` is set, the existing slot display name. Omit when both
   are null (bookings). Never show the raw slug.
4. Dwell: `durationMinutes` as "N min". Always shown.
5. Hours: keep `Hours: <openingHours>` when present; omit when null.
   Do not compute open/closed.
6. Landmark: `nearestLandmark` when non-empty; omit otherwise. Do not
   invent one from `namesLocal`.
7. Vibe chips: keep showing all of them.
8. Actions, a wrap of labelled buttons (not a four-icon row), each at
   least 44dp:
   - **Open in Maps** (key `detail_open_maps`): shown when lat and lng
     are both set, or when `venueName` is non-empty. Calls the maps
     helper. Always enabled.
   - **Driver card** (key `detail_driver_card`): `context.push` to the
     same path the overflow uses. Always shown.
   - **Swap** (key `detail_swap`): unlocked, not completed, not
     skipped, `onSwap != null`. Same callback as today (pop then
     swap).
   - **Skip / Cancel** (key `detail_cancel`): unlocked, not completed,
     not skipped, `onCancel != null`. Same callback as today.
   - **Move** (key `detail_move`, replacing `move_detail_<id>` if you
     keep one key: report which): same visibility as today.
   - **Love** (key `detail_love`): `onLoved != null`, not completed,
     not skipped. Shows filled/unfilled from an `isLoved` constructor
     argument (default false). The callback is the parent's; the
     details screen does not call `SignalService`.
9. Bookings: keep "Locked reservation". Hide Swap, Skip, Move, Love.
   Keep Open in Maps and Driver card.

Constructor additions (all optional, so existing tests that construct
the screen with only `node` still compile): `onLoved`, `isLoved`,
`tripId` only if GoRouter cannot see it (otherwise omit this argument
and read it from the route; prefer reading it).

Do not change `ActivityCard`, the overflow, itinerary layout, Ask, or
Home.

## 3. Tests (must fail on main unless noted)

Flutter (`mobile/test/spec45_place_detail_test.dart`). Pump
`ActivityDetailScreen` directly unless a test needs the itinerary
harness (test 8). Keys as above.

1. A catalog activity with neighbourhood, hours, slot, dwell, landmark
   and vibes shows each sourced field, and does not show
   `nam_phou_fountain` or `[BOOKING:`. Fails on main (slot, dwell,
   landmark missing today).
2. Missing neighbourhood, hours and landmark: those rows are absent,
   not "unknown" or a slug. Passes on main if already true; still
   write it as a guard.
3. A window node (`timeWindow: 'morning'`) shows the window label, not
   a clock time. Fails on main.
4. Open in Maps is present; tapping it is wired (assert the button
   exists and `onPressed` is non-null; do not actually launch a URL).
   Fails on main.
5. Driver card is present; tapping it calls `GoRouter` with
   `/trip/<tripId>/card/<venueId or venueName>`. Use a test router
   or a fake. Fails on main.
6. Love is present when `onLoved` is passed; tapping it invokes
   `onLoved` once and does not enqueue a signal (no `SignalService` in
   this widget). Fails on main.
7. A locked booking shows "Locked reservation", Open in Maps and
   Driver card, and does not show Swap, Skip, Move or Love. Fails on
   main (Open in Maps / Driver card missing).
8. From the itinerary, tapping a card still opens this screen (existing
   behaviour; write it here so a regression fails this file). Passes
   on main.
9. Existing `spec45_friction_test` and `spec42_move_test` still pass
   without expected-value edits. If the Move key rename would break
   `spec42_move_test`, keep the old key `move_detail_<id>` as well as
   `detail_move`, or keep the old key only and report it.

Existing tests: do not change expected values. Stop if more than three
need edits.

R17 (branches from the tip, each pushed as its own head):
- `feat/spec45-place-detail-r17a`: Open in Maps and Driver card are
  omitted. Expected failures: tests 4, 5 and 7.
- `feat/spec45-place-detail-r17b`: the slot/window row is omitted.
  Expected failures: tests 1 and 3.
- `feat/spec45-place-detail-r17c`: Love is omitted. Expected failures:
  test 6.

The planning agent opens each as a draft PR, reads the failing names,
closes them unmerged and deletes the branches.

## 4. Explicitly out

- Transfer / arrival cards (SPEC-55, parked)
- Category, typical catalog dwell, Open/Closed, walking time,
  "why this stop", last-checked / provenance, photos
- A new GoRoute; keep the existing `MaterialPageRoute` push
- Backend fields, catalog lookups, GPS, map tiles
- Changing `ActivityCard` overflow, Ask, Home, or Driver Card internals
- FLAG_SECURE, consent, APK, hosted deploy, new dependency

## 5. Stop rules

- Stop if `GoRouterState.of(context)` has no `tripId` on the details
  screen, so Driver card cannot reuse the overflow path. Report it;
  do not invent a tripId and do not add a route in this slice without
  asking.
- Stop if Open in Maps would need a new package.
- Stop if a sourced field listed in section 2 is not on `TripNode` when
  you re-read it (do not fetch it from elsewhere).
- Stop if more than three existing tests need expected-value edits.
- Stop if filling the screen would require changing `ActivityCard`.

## 6. Gates

- ASCII only in added code, comments and strings (R14).
- No hard-coded test counts in docs (R16).
- `grep -rn '\\$' mobile/lib` after any Dart write (R1): only the two
  known price strings in `upgrade_screen.dart`.
- `flutter analyze --no-fatal-infos`: no new errors or warnings.
- Jobs: `flutter`, `android-compile`, `pytest`, `lint`,
  `postgres-proof`, `docker-build`, `test` green. `deploy` and `build`
  skipped.

## 7. PR

Branch `feat/spec45-place-detail` from the base SHA you were sent. Do
not merge. Push the branch and the three `-r17a` / `-r17b` / `-r17c`
heads. Send the planning agent the PR description; the planning agent
opens the PRs.

The PR description must include: the preflight answers (GoRouter
tripId on the details screen, the maps helper you reused or copied,
the slot/window label helper, every existing `ActivityDetailScreen`
test), a test-to-production table, R17 expected failures, every
existing test touched, and "no APK and no hosted deploy in this
slice". Say that the Flutter half has no local SDK if that is still
true; CI is then its first compile.
