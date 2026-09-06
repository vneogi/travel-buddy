# Genie Brief: SPEC-36 remaining review items after 793ffb2

> HISTORICAL. SPEC-36 landed in PR #55 (`1f2c43d`). Do not implement from
> this brief.

## Read first

- `docs/specs/SPEC-36-laos-corridor-trip.md`
- `docs/ENGINEERING_RULES.md` (R1, R2, R5, R17)
- Existing files on the branch. Do not reconstruct them from this brief.

Base SHA to continue from: `793ffb2`. Confirm with `git fetch` and
`git rev-parse HEAD` before editing.

## What review already cleared (do not redo)

These were broken at `e6522bb` and are present at `793ffb2`:

- `CorridorDateForm({super.key, required this.corridor})`
- `_CityDateRow` is file-private
- HomeScreen widget test: tap corridor card, submit form,
  `corridorCreate` once with three ordered regions, navigate to the trip
- `_submit()` sets `_submitting` before `Navigator.pop`
- Backend proofs for create, validation, atomic capacity, LLM/hybrid/quota
  isolation, later-city HTTP swap isolation, next-city date boundary

Do not reopen those unless a new test fails.

## Must fix

### 1. Date-form city labels are truncated

`_CityDateRow` takes `region.split('_').first`, so the form shows
"Vang" and "Luang". Itinerary grouping already maps to "Vang Vieng"
and "Luang Prabang" in `date_scope.dart`. The form must use the same
human names. Do not invent a second map (R5): extract one helper and
use it in both places.

Update widget tests that currently `find.text('Vang')` / `find.text('Luang')`.
They must look for `Vientiane`, `Vang Vieng`, and `Luang Prabang`.

### 2. Guard the sheet, not only the in-flight create

`_showCorridorDateForm` leaves `_creating` false until the sheet pops.
A second tap on the corridor card while the form is open can stack
another sheet.

Lock before `showModalBottomSheet` (a dedicated open flag is fine;
do not show the creating spinner while the user is still picking dates).
Release the lock when the sheet closes.

### 3. Make the double-submit test fail if the second tap never happens

The current test wraps the second tap in
`if (find.text('Multi-city Laos corridor').evaluate().isNotEmpty)`.
If that finder is empty, the test still passes with `callCount == 1`.
That is not a guard (R17).

After the first Create tap and a `pump` (create still in-flight):

- assert the corridor card is still on screen;
- tap it;
- then complete the Completer;
- assert `corridorCreate` was called exactly once.

Also add a case, or extend this one, that a second tap *while the
sheet is open* does not call `corridorCreate` a second time and does
not open a second `CorridorDateForm`.

### 4. City-order widget proof on the production itinerary

`S5` currently asserts that `groupNodesByCalendarDate` mixes cities.
That does not prove `ItineraryScreen` renders city sections in corridor
order.

Add a widget test that pumps `ItineraryScreen` with a three-city
corridor and asserts the three `CitySection` headers appear in
Vientiane, Vang Vieng, Luang Prabang order. Sabotage 5 in the spec
must fail *this* test if the screen groups by date only.

### 5. Hygiene

`services/corridor_itinerary.py` imports `INFRASTRUCTURE_CATEGORIES`
and `eligible_venues` and does not use them. Remove unused imports.
Run ruff on files you touch.

## Do not do

- Do not start the next spec.
- Do not add a migration, LLM, hybrid search, synthetic transport, or
  background location.
- Do not mark SPEC-36 acceptance boxes complete.
- Do not merge.
- Do not rebase onto main unless a merge conflict blocks the PR.

## Gates

From repo root:

```bash
pytest -q -ra
pytest -q tests/test_docs_hygiene.py
ruff check .
git diff --check
```

From `mobile/`:

```bash
flutter analyze --no-fatal-infos
flutter test
```

R1:

```bash
git diff --name-only origin/main...HEAD -- '*.dart' | xargs rg -n '\\\$'
```

If Flutter is unavailable, say so. Do not report a file inspection as a
Flutter pass.

## Completion

Push the same branch. Report the new full SHA, compare URL, exact gate
results with skip reasons, and which of items 1-5 landed. Stop.
