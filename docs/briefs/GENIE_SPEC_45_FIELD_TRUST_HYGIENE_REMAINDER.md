# Genie Brief: SPEC-45 field trust hygiene remainder

Continue on `feat/spec45-field-trust-hygiene` from `397846d`.
Do not start a new branch from main.

Do not merge. Do not deploy. Do not APK.
Do not start Ask, What Now, Add/Move, catalog patches, or SPEC-43.

Read:

- `docs/briefs/GENIE_SPEC_45_FIELD_TRUST_HYGIENE.md` (original contract)
- `mobile/lib/features/itinerary/current_window.dart`
- `mobile/lib/features/alerts/alert_policy.dart`
- `mobile/lib/data/repositories.dart` (`SwapCandidatesResult`)
- `mobile/test/spec45_swap_confirm_test.dart`
- `mobile/test/spec_g0_swap_slot_test.dart`
- `mobile/test/spec30_widget_test.dart`
- `mobile/test/spec31_widget_test.dart`

Do not edit this brief.

## Verdict on `397846d`

Helpers for cap/coalesce, kind-specific copy, locked-node Review gate,
and swap `refusal_code` are the right shape. The PR is not done.

Flutter was not run. The `swapCandidates` return type change does not
compile against existing fakes/mocks. `nodeCanRecordOutcome` now
forbids past-day recording entirely, which violates the original brief.

## Must fix

### 1. Past-day outcomes must still be recordable

Split the predicates:

- `nodeCanRecordOutcome` -- pending, start not in the future, no
  recorded overlay. Used by the day-section card and the notifier.
- A Today-only helper (name it) -- additionally requires destination-
  local date == today OR `nodeIsCurrentWindow`.

Today's timeline / featured surface uses the Today helper so day-1
does not flood day-8. Scrolling to yesterday's section still shows
the prompt via `nodeCanRecordOutcome`.

Add a clock-injected test: yesterday elapsed node is false for Today
and true for the day-section helper.

R17: fold the today-check back into `nodeCanRecordOutcome`; the
yesterday-still-recordable test goes red. Restore.

### 2. Compile: SwapCandidatesResult at every call site

`TripRepository.swapCandidates` now returns `SwapCandidatesResult`.
Update every fake and `when(() => repo.swapCandidates(...))` that
still returns `List<VenueSearchResult>`:

- `mobile/test/spec45_swap_confirm_test.dart`
- `mobile/test/spec_g0_swap_slot_test.dart`
- `mobile/test/spec17_sponsored_disclosure_test.dart`
- `mobile/test/spec36_corridor_test.dart`
- any other hit from `git grep swapCandidates mobile/`

Keep the empty-sheet copy `No alternative venues found nearby.` when
`refusalCopy` is null so the G0 empty test stays green. When
`refusalCopy` is set and no vibe filter is active, show that copy.

### 3. Update outcome copy assertions

`spec30_widget_test.dart` and `spec31_widget_test.dart` still look for
`Did this happen?`. Point them at `Did you visit?` (activity nodes) or
the kind-specific string the fixture actually uses.

### 4. Wire Checked out?

`outcomePromptText(..., isLastHotelNight: true)` is uncalled from
production. Pass it from the timeline using the existing hotel
coverage / continuation logic: first night `Checked in?`, last
coverage date `Checked out?`, middle continuation nights no extra
prompt if they already hide Edit/Delete.

Do not invent a new hotel model.

### 5. Flight city must not be venueName

`Arrived in $venueName` will print airline or hotel strings. Use an
existing friendly city/segment/region display if one already exists
on the node or corridor section. If none, `Arrived?`. Never invent a
city. Keep a test that empty/unknown city yields `Arrived?`.

### 6. Tests the first slice claimed but did not write

Widget or small widget-adjacent tests, clock injected:

- Review alternatives absent when the first affected node is locked;
  present when unlocked and `review_outdoor_plans`.
- Empty SwapSheet with `refusalCopy` shows that sentence.
- Yesterday prompt visible in a day-section card, absent from a Today
  filter of the same list.

R17 for the cap: in `ItineraryAlertsSection`, temporarily render
`alertsState.visible` without `cappedAlerts`; a test that 5 distinct
types produce 2 cards plus `N more alerts` goes red. Restore. Do not
treat `expect(maxVisibleAlerts, 2)` as sabotage.

Python: do not treat "if candidates empty, then assert refusal" as
proof. Force an empty set (hours-closed or empty catalog for that
slot) and always assert `refusal_code` in `{hours, reachability,
no_catalog}` plus non-empty copy.

## Gates

```text
flutter analyze --no-fatal-infos
flutter test
pytest -q tests/test_spec45_trust_hygiene.py tests/test_g0_field_fix_proofs.py
ruff check .
ruff format --check .
git diff --check
grep -rn '\\$' mobile/lib
```

Flutter UNVERIFIED on Databricks. R1 after Dart writes. Do not quote
counts into living docs.

PR update on the same branch. Stop.
