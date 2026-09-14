# Genie Brief: SPEC-40 Fix 3 — Wizard behavioral tests

Start only after Fix 2 is pushed. Continue `feat/spec40-guided-create`.
Do not merge. Do not deploy.

Read first: `docs/specs/SPEC-40-guided-create-trip.md`, `docs/ENGINEERING_RULES.md`.
Do not edit this brief.

## Goal

Replace vacuous SPEC-40 widget tests with production-path proofs that fail
when the wizard is broken.

## Delete / rewrite

In `mobile/test/spec40_create_wizard_test.dart`, remove tests that:

- only inspect fixture models;
- reimplement the interest cap in the test;
- conditionally skip if a finder is empty;
- look for copy that is not on screen (`Plan a new trip`);
- claim API-error retention without calling `rangeCreate`.

## Required proofs (must tap production widgets)

Use the Fix 2 date hook plus `homeSnapshotProvider` / `tripRepoProvider`
overrides. Use the real `CreateTripScreen`.

1. Home `Create a trip` → GoRouter `/trip/create` → destinations from snapshot.
   Assertion must fail if navigation fails.

2. Advance all five steps. Party radios are tappable (solo → friends) with
   no Slider assert.

3. Fourth interest chip does not stay selected.

4. Review shows destination, dates, party, interests.

5. One Create tap sends **one** `rangeCreate` with exact geo, YYYY-MM-DD
   dates, party, and interest IDs.

6. Delayed `rangeCreate` Completer: two Create taps → one call.

7. `ValidationException` on submit: typed message shown; destination/party/
   interests still filled; `_submitting` resets.

8. Success `go('/trip/{id}')`.

9. 800×600 and 1.5× text: later steps remain scroll-reachable (not only step 1).

No `if (finder.evaluate().isNotEmpty)` around the assertion.

## Gates

```text
cd mobile
flutter analyze --no-fatal-infos
flutter test
```

If Flutter is unavailable, say so. Push the SHA. Stop for review.
Do not open a PR unless asked.
