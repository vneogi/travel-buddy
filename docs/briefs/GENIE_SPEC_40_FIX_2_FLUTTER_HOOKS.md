# Genie Brief: SPEC-40 Fix 2 — Flutter production hooks

Start only after Fix 1 is pushed. Continue `feat/spec40-guided-create`.
Do not rewrite the five-step wizard. Do not merge. Do not deploy.

Read first: `docs/specs/SPEC-40-guided-create-trip.md`, `docs/ENGINEERING_RULES.md`.
Do not edit this brief.

## Goal

Make later widget tests able to drive all five steps, and stop the stale Home
create test from blocking `flutter test`.

## Required changes

1. Add a **test-only** way to set the wizard date range without
   `showDateRangePicker` (for example `@visibleForTesting` on the State class,
   or an optional `ValueChanged` / debug hook that production does not use).
   Production still uses the range picker. Inclusive day counts stay
   `DateUtils.dateOnly`, not `DateTime.difference`.

2. Rewrite `mobile/test/features/home/home_screen_test.dart`
   `create posts the selected laos region`:
   - register `/trip/create`;
   - tapping `Create a trip` opens the wizard (`Where are you going?`);
   - do **not** expect `FilledButton` `Create` or `repository.create(...)`.

3. Add a repository unit test that `rangeCreate` POSTs `start_date` and
   `end_date` as `YYYY-MM-DD` (not ISO datetimes).

4. Add an ApiClient unit test that a 422 with
   `detail.error` / `detail.message` (`over_capacity` or `invalid_interests`)
   becomes `ValidationException` with that message.

5. Remove unused imports introduced by SPEC-40 tests (`dart:async` if unused).

Do not write the full five-step behavioral suite here (that is Fix 3).

## Gates

```text
cd mobile
flutter analyze --no-fatal-infos
flutter test
```

If Flutter is unavailable, say so and do not claim the suite is green.
Push the SHA. Stop. Do not start Fix 3.
