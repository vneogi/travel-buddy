# Genie brief: SPEC-50 slice 1, inspectable swap comparison

Read this whole file before touching anything. It is the complete job.
If something here is unclear, stop and ask; do not guess and do not
widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA.

Owning spec: `docs/specs/SPEC-50-swap-comparison.md` (slice 1 only).
Parents: SPEC-07 (swap sheet), SPEC-17 (sponsored disclosure, which stays
visible), SPEC-45 B4 (typed refusal copy). Flutter-only. No backend, no
SQLite schema change, no migration, no Cloud Run deploy, no network call
beyond the existing `swapCandidates` read, no change to the confirm
command.

## 0. Context

Owner device pause runs from 2026-11-16 night for about four days. CI is
the gate. The phone check waits until the owner returns.

Verified on `main` (re-verify in preflight):

1. `SwapSheet` in `mobile/lib/features/swap_sheet/swap_sheet.dart` loads
   candidates once via `tripRepoProvider.swapCandidates(...)` and shows a
   vibe `FilterChip` row, a list of `ListTile`s, and footer actions
   `Cancel` (pops null) and `Confirm swap` (pops the selected
   `VenueSearchResult`). Title text is `Swap to...`.
2. Selection is by tapping a row (`_selectedVenue`); the selected row has
   a `Icons.check_circle` trailing icon with semanticLabel `Selected`.
3. `VenueSearchResult` (`mobile/lib/data/models.dart`) has `venueId`,
   `name`, `description`, `microLocation`, `vibeTags`, `distanceKm`,
   `isSponsored`, `sponsoredBoostApplied`. The swap response only fills
   `venueId`, `name`, `microLocation`, `vibeTags` (the backend sends
   `category`, `lat`, `lng`, `slot_name` too, which the client ignores).
   `distance_km` is NOT in the swap response, so it is null on this path.
4. The swap response has NO score, reason, hours, price or accessibility
   fields. Its candidates have already passed the server's opening-hours
   and reachability checks for the target slot
   (`routers/trip_router.py` `swap_candidates`). That is the only evidence
   the client may state, and only as the fixed copy in section 1.
5. `ItineraryScreen._swap` (`mobile/lib/features/itinerary/itinerary_screen.dart`)
   builds `SwapSheet(tripId:, targetNodeId:, tripState:)` with the target
   `TripNode node` in scope. Swap is hidden on locked and completed
   cards, and the backend returns 409 for locked targets.
6. Existing tests that MUST stay green unchanged:
   `mobile/test/spec07_swap_sheet_test.dart`,
   `mobile/test/spec45_swap_confirm_test.dart` (expects `Swap to...`,
   `Confirm swap`, one `Cafe Sinouk` before tap, one `Icons.check_circle`
   after tap), `mobile/test/spec17_sponsored_disclosure_test.dart`
   (expects exactly one `Sponsored` label and one
   `Paid placement influenced this ranking.` when a boosted venue is
   listed), and `mobile/test/spec_g0_swap_slot_test.dart`.

## 1. Goal

Before confirming a swap, the trip captain can compare the current stop
with one candidate. Browsing never changes the itinerary. Only fields the
server already sent are shown.

### What is shown (slice 1, fixed)

When the user has selected a candidate AND `currentNode` was passed AND
`currentNode.isLocked` is false, show a comparison panel above the list
(inside the sheet, below the vibe chips, above the list):

- Key `Key('swap_comparison')`, wrapped in `Semantics(container: true,
  label: 'Comparison: current stop and option')`.
- Row "Now": one `Text.rich`: label `Now` in `AppTypography.caption`
  muted, then the stop name and `  HH:MM to HH:MM` in destination-local
  time (`formatDestinationTime` from `mobile/lib/core/destination_tz.dart`,
  end = `scheduledStart + durationMinutes`).
- Row "Option": one `Text.rich`: label `Option` muted, then the
  candidate `name`. Do NOT render the candidate name as its own Text
  widget (existing tests use exact `find.text` on venue names).
- Row "Area": `microLocation` when non-empty, else `Area: not available`.
- Row "Vibes": `vibeTags` joined with `, ` (take 4), else
  `Vibes: not available`.
- Row "Checks": fixed copy exactly:
  `Passed the server's opening-hours and reachability checks for this slot.`
  Use this row only for candidates in the list (always true here). No
  other wording for checks.
- Row "Ranking" ONLY when `sponsoredBoostApplied` is true: copy exactly
  `Sponsored option: paid placement can affect its position.` (not the
  list's exact `Sponsored` label, so exact-text tests stay single-match).
- Nothing else. Do NOT show distance, price, accessibility, a score, a
  rank number, a "better" or "recommended" claim, travel time, or
  "fits before your booking". Those need a documented source first
  (SPEC-50 "Later dimensions").

### Next option

- Inside the panel, a `TextButton` keyed `Key('swap_next_option')`,
  label exact `Next option`, min height 44dp.
- It selects the next candidate AFTER the selected one in the current
  visible list (`_visibleVenues`, so vibe filters apply). It does not wrap.
- Disabled (`onPressed: null`) when there is no next visible candidate,
  or when the selected candidate is not in the visible list.
- Pressing it only sets `_selectedVenue`. It calls no repository method,
  no notifier, no event, no signal.

### Confirm and Cancel

- `Confirm swap` and `Cancel` keep their exact labels and behaviour: Confirm
  pops the currently selected `VenueSearchResult`; Cancel pops null.
- Browsing (select, Next option, vibe filters) never mutates anything.
- The comparison adds no check icon and no `Selected` semantics; the
  existing row trailing icon is the only selection indicator.

### Locked and missing context

- `SwapSheet` gets a NEW optional constructor parameter
  `TripNode? currentNode` (default null). Existing callers that do not
  pass it see no comparison panel at all.
- If `currentNode` is non-null and `currentNode.isLocked` is true, no
  comparison panel is built (the card already hides swap for locked stops;
  this is the defensive guard).

## 2. Preflight

1. `git fetch origin`. Work from the base SHA in the message that sent
   this brief.
2. Confirm section 0 items 1 to 6. If any differs, stop and report.
3. Confirm `origin/feat/spec50-swap-comparison` does not exist, and that
   `swap_comparison` / `SwapComparison` do not already appear under
   `mobile/lib`.
4. Run `rg -n "SwapSheet\(" mobile/lib` and list every call site in your
   report. Only `itinerary_screen.dart` `_swap` should pass a node. If
   another call site exists, stop and ask (do not change it).
5. Branch: `feat/spec50-swap-comparison`.

## 3. Read before editing

- `docs/specs/SPEC-50-swap-comparison.md`, `docs/specs/SPEC-07-*.md`,
  `docs/specs/SPEC-17-*.md` (sponsored disclosure)
- `docs/ENGINEERING_RULES.md` R14, R16, R17
- `mobile/lib/features/swap_sheet/swap_sheet.dart` (whole file)
- `mobile/lib/data/models.dart` (`VenueSearchResult`, around line 923)
- `mobile/lib/core/destination_tz.dart` (`formatDestinationTime`)
- `mobile/lib/features/itinerary/itinerary_screen.dart` (`_swap`, around
  line 78; only the `SwapSheet(` construction)
- `mobile/test/spec45_swap_confirm_test.dart` (fake repo pattern,
  `_FakeTripRepo`), `mobile/test/spec07_swap_sheet_test.dart`

## 4. Files you may touch

- `mobile/lib/features/swap_sheet/swap_sheet.dart`: the optional
  `currentNode` parameter, the comparison panel, Next option, and the
  visible-list helper it needs.
- `mobile/lib/features/swap_sheet/swap_comparison.dart` (new, optional): a
  pure helper `swapComparisonRows(...)` and/or the panel widget. If you
  put the panel in its own file, keep it under `swap_sheet/`.
- `mobile/lib/features/itinerary/itinerary_screen.dart`: ONLY adding
  `currentNode: node,` to the existing `SwapSheet(` call in `_swap`.
- `mobile/test/spec50_swap_comparison_test.dart` (new).

Nothing else. No backend, no repository change, no models change, no
router, no notifier, no docs, no `pubspec`, no ActivityCard change.

## 5. Implementation notes

- Pure helpers take values, not `DateTime.now()`. The panel needs no clock.
- Keep the list's `ListView` and its `scrollController` exactly as they are.
- Use existing tokens only (`AppColors.card`, `AppColors.muted`,
  `AppColors.divider`, `AppSpacing.*`, `AppTypography.*`). No new palette.
- Text wraps or ellipsizes; no horizontal overflow at 360dp wide and 2.0
  text scale with a 60-character candidate name and a 60-character stop
  name.
- Comparison panel height at normal text scale: about 160dp or less, so
  the candidate list stays usable.

## 6. Tests

`mobile/test/spec50_swap_comparison_test.dart`, exact names. Use a fake
repository like `spec45_swap_confirm_test.dart` (`_FakeTripRepo`) and
`ProviderScope` / `MaterialApp` / `Scaffold` as there. Open the sheet from
a button so the result can be read back.

1. `comparison hidden until a candidate is selected`
2. `selecting shows now and option rows with names and area`
3. `missing area and vibes show not available, not blank`
4. `no score, rank, better or recommended wording anywhere in the sheet`
5. `sponsored option adds the ranking note and keeps exactly one Sponsored label`
6. `Next option moves to the next visible candidate and stops at the end`
7. `Next option is disabled when the selected candidate is filtered out`
8. `locked current stop never shows the comparison`
9. `no comparison when currentNode is not passed`
10. `Confirm swap pops the currently shown option; Cancel pops null`
11. `browsing does not call the repository again` (count calls on the fake
    repo: exactly one `swapCandidates` call while browsing)
12. `no overflow at 360dp and 2.0 text scale with long names`
13. `Next option and Confirm meet 44dp min height and button semantics`

Use `tester.view` sizing as in `spec56_offline_readiness_test.dart` for
test 12. Test data uses placeholder names (no invented local-language
strings).

## 7. R17

Run each, confirm the named test fails, then restore and confirm green:

A. Remove the `currentNode.isLocked` guard: test 8 fails.
B. Make Next option wrap to the first candidate at the end: test 6 fails.
C. Add the word "better" to the Checks row: test 4 fails.
D. Show the comparison even when `currentNode` is null: test 9 fails.

## 8. Stop rules

Stop and ask if:

- you need any file outside section 4;
- an existing test needs an assertion changed (for example a duplicate
  `Sponsored` or venue-name match you cannot avoid with the copy above);
- you want distance, price, accessibility, a score, a rank, travel time
  or any reason text beyond the fixed copy;
- you want a new network call, a new cache read, or a backend change;
- another `SwapSheet(` call site needs a node.

## 9. Gates

```
cd mobile && flutter analyze && flutter test
git diff --check
```

`flutter analyze` 0 issues (infos as today), `flutter test` all passed.
ASCII only in any text you add. Do not add `SPEC-NN` references except to
numbers with a file under `docs/specs/`.

If you have no Flutter SDK, say so and rely on CI. Do not install Flutter
without the owner's approval.

## 10. Delivery

One commit on `feat/spec50-swap-comparison`:
`feat: SPEC-50 inspectable swap comparison`.
Push and verify the remote SHA. Do not merge. No `gh`. No APK build or
Cloud Run deploy.

## 11. Report

1. Base SHA.
2. Branch and remote SHA.
3. `flutter analyze` / `flutter test` last lines (or "no Flutter, CI only").
4. `git diff --check` result.
5. Files touched, with +/- counts.
6. The `SwapSheet(` call-site list from preflight item 4.
7. R17 A to D results (or "not observed, CI only").
8. Confirmation that the confirm command, repository, backend, models,
   router, notifier and ActivityCard are unchanged.
9. Anything you were unsure about.

## 12. Owner device check (after merge; waits until phone returns)

1. Open a Zanzibar stop (unlocked) -> Swap. Tap an option. Panel shows
   Now and Option rows. Tap Next option; it moves to the next candidate.
2. Confirm swap applies as before; Cancel changes nothing.
3. A locked booking shows no Swap action (unchanged).
4. Largest system font: panel wraps; list still scrolls.
5. A sponsored option (if present) shows the ranking note once.
