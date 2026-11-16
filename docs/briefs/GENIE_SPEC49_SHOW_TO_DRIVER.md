# Genie brief: SPEC-49 slice 1, Show-to-driver mode

Read this whole file before touching anything. It is the complete job.
If something here is unclear, stop and ask; do not guess and do not
widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA.

Owning spec: `docs/specs/SPEC-49-driver-handoff-and-tanzania-language.md`.
Parents: SPEC-12 (Driver Card), SPEC-13 (language order; F2 already on
main). This slice is Flutter-only. No backend, no SQLite schema change,
no migration, no Cloud Run deploy, no landmark data seeding.

## 0. Context

Owner device pause starts after 2026-11-16 night for about four days.
CI is the gate. Phone check of this slice waits until the owner returns.

Verified on `main` (re-verify in preflight):

1. `DriverCardScreen` in
   `mobile/lib/features/driver_card/driver_card_screen.dart` loads only
   from `db.getCachedPlace(nodeId, identityScope: ...)`. Zero network
   calls. Route: `/trip/:tripId/node/:nodeId/driver` in
   `app_router.dart`. Opened from the activity-card overflow menu
   (`value: 'driver'`).
2. The screen shows: AppBar with Back and title "Driver Card"; local
   name via `FactView` (confirm/dismiss when tier is ask); landmark
   section; English `venueName` as `AppTypography.h1`; "Open in Maps";
   lat/lng; offline and food disclaimer captions.
3. `AppTypography.display` and `AppTypography.localScript` exist for
   large arm's-length reading. `AppColors` has no brightness/orientation
   helpers; do not add `SystemChrome` or wakelock.
4. Tanzania `sw` then `en` priority is already on main (F2). This slice
   does not change language order. Landmarks and Slice 2 (in-app
   shortcut) are out of scope.

## 1. Goal

One tap turns the existing Driver Card into a hand-to-driver view: big
destination text, verified landmark only if already present, everything
else hidden. One clearly visible tap exits. Normal orientation, no
brightness override, still 100% from cache.

While Show-to-driver is ON, show only:

- The destination name the driver should read: prefer the resolved local
  name when `_currentTier` is not `refuse` and `_resolvedValue` is
  non-null; otherwise the English `venueName`. Style:
  `AppTypography.display` (and `localScript` when a local name is shown).
- Landmark text, only when `_buildLandmarkSection` already has a
  resolved value today. Label it `Landmark`. If there is no landmark,
  show nothing in its place (do not invent text, do not show "Local
  landmark not available" as a claim).
- One full-width exit control, key `Key('show_to_driver_exit')`, label
  exact: `Done -- return to card`. Min height 48dp.

While Show-to-driver is ON, hide: AppBar title/actions still need a way
back -- prefer hiding the normal AppBar entirely and relying on the exit
button (system back must also exit the mode, not leave the route, when
mode is on). Hide FactView confirm/dismiss, "Open in Maps", coordinates,
and both disclaimer captions.

Entry control on the normal card (mode OFF), key
`Key('show_to_driver_enter')`, label exact: `Show to driver`. Place it
near the top of the card body (after the name section is fine). Min
height 44dp. Disabled or absent when `_data == null` (nothing cached).

Rules:

- Mode starts OFF every time the screen is opened (do not persist).
- System back / AppBar back while mode is ON: set mode OFF, stay on the
  screen. While mode is OFF: normal pop.
- Route pop, dispose, or navigating away: mode is gone (no global flag).
- No `SystemChrome.setPreferredOrientations`, no brightness, no
  wakelock. Intercept system back with `PopScope` (canPop: false while
  mode is on; onPopInvokedWithResult turns mode off). The repo does not
  already use PopScope; adding it only on this screen is fine.
- Still zero network calls. Do not change cache reads, signals
  (`emitDriverCardShown` / `emitNameConfirmed`), or provenance tiers.

## 2. Preflight

1. `git fetch origin`. Work from the base SHA in the message that sent
   this brief.
2. Confirm section 0 items 1 to 3. If any differs, stop and report.
3. Confirm `origin/feat/spec49-show-to-driver` does not exist, and that
   `show_to_driver` / `ShowToDriver` do not already appear under
   `mobile/lib`.
4. Branch: `feat/spec49-show-to-driver`.

## 3. Read before editing

- `docs/specs/SPEC-49-driver-handoff-and-tanzania-language.md`,
  `docs/specs/SPEC-12-show-driver-cards.md`
- `docs/ENGINEERING_RULES.md` R14, R16, R17
- `mobile/lib/features/driver_card/driver_card_screen.dart` (whole file)
- `mobile/lib/features/driver_card/driver_card_helpers.dart`
- `mobile/lib/theme/typography.dart` (`display`, `localScript`)
- Existing driver-card / SPEC-12 tests under `mobile/test/` (names may
  vary; find with `rg DriverCard`)

## 4. Files you may touch

- `mobile/lib/features/driver_card/driver_card_screen.dart`: add the
  mode flag, enter/exit controls, conditional build. Nothing that
  changes cache load, signals, maps launch, or confirm/reject logic
  beyond hiding those widgets while mode is on.
- `mobile/test/spec49_show_to_driver_test.dart` (new).

Nothing else. No router change, no activity_card change, no helpers
change unless a tiny pure function is clearly needed and reported, no
docs, no backend, no `pubspec`.

## 5. Implementation notes

- Keep a `bool _showToDriver = false` on `_DriverCardScreenState`.
- Extract the "hand-off" body into a private method or clear `if`
  branches so the normal card path stays readable.
- High contrast: use existing `AppColors.card` / ink tokens only; do
  not invent a new palette.
- Text must wrap; no ellipsis that hides the destination at 360dp or
  2.0 text scale.
- Semantics: enter and exit are buttons with their labels.

## 6. Tests

`mobile/test/spec49_show_to_driver_test.dart`, exact names. Seed
`cache_place` with a real in-memory `OfflineDatabase` (same FFI pattern
as SPEC-56 / SPEC-12 tests). Pump `DriverCardScreen` with overrides for
`offlineDatabaseProvider`, `identityCacheScopeProvider`, and a
no-op/mock `signalServiceProvider` as existing tests do.

1. `enter control visible when place is cached`
2. `enter control absent when place is not cached`
3. `tapping Show to driver hides maps confirm and disclaimers`
4. `show-to-driver shows destination name at display size` (find the
   name text; assert the exit control is present)
5. `landmark shown only when cached landmark exists` (two cases: with
   and without)
6. `Done exit returns to the normal card` (maps / enter control visible
   again; exit gone)
7. `system back while in mode exits mode not the route` (use
   `tester.binding.handlePopRoute` or the project's existing back
   pattern; screen still showing Driver Card; mode off)
8. `opening the screen always starts with mode off`
9. `works offline from cache only` (no tripRepo / no Dio; prove
   `getCachedPlace` was used and sendEvent/getTrip were not)
10. `no overflow at 360dp and 2.0 text scale` in both mode on and off
11. `enter and exit meet 44dp / 48dp min heights and button semantics`

## 7. R17

Run each, confirm the named test fails, then restore and confirm green:

A. Remove the enter button: test 1 fails.
B. Leave "Open in Maps" visible while mode is on: test 3 fails.
C. Make system back pop the route while mode is on: test 7 fails.
D. Persist mode across a fresh pump of the screen (e.g. a static flag):
   test 8 fails.

## 8. Stop rules

Stop and ask if:

- you need any file outside section 4;
- an existing test needs an assertion changed;
- you want brightness, rotation, wakelock, OS tile, lock screen, or a
  new route;
- you want to seed or invent landmark / Swahili strings;
- Provenance display for the large name would require showing a
  confirm/dismiss control in hand-off mode (do not; hand-off shows the
  name text only).

## 9. Gates

```
cd mobile && flutter analyze && flutter test
git diff --check
```

`flutter analyze` 0 issues (infos as today), `flutter test` all passed.
ASCII only. Do not add `SPEC-NN` references except to numbers with a
file under `docs/specs/`.

If you have no Flutter SDK, say so and rely on CI. Do not install
Flutter without the owner's approval. Teardown: close harness listeners
while the widget is still mounted, then dispose (see
`spec46_what_now_test.dart`).

## 10. Delivery

One commit on `feat/spec49-show-to-driver`:
`feat: SPEC-49 Show-to-driver mode on the Driver Card`.
Push and verify the remote SHA. Do not merge. No `gh`. No APK build or
Cloud Run deploy.

## 11. Report

1. Base SHA.
2. Branch and remote SHA.
3. `flutter analyze` / `flutter test` last lines (or "no Flutter, CI only").
4. `git diff --check` result.
5. Files touched, with +/- counts.
6. R17 A to D results (or "not observed, CI only").
7. Confirmation that cache load, signals, language order, router and
   backend are unchanged.
8. Anything you were unsure about.

## 12. Owner device check (after merge; waits until phone returns)

1. Online, open a Zanzibar stop overflow menu -> Driver card. Tap
   `Show to driver`. Confirm huge name, no Maps button, clear `Done`
   exit. Exit returns to the normal card.
2. Airplane mode, reopen the same Driver card from cache. Show-to-driver
   still works.
3. While in mode, use system back: mode exits, you stay on the card.
4. Largest system font: name wraps, nothing clipped.
