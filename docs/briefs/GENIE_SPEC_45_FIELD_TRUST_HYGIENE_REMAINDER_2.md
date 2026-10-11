# Genie Brief: SPEC-45 hygiene remainder 2

Continue on `feat/spec45-field-trust-hygiene` from `afcde2a`.
Do not start a new branch from main.

Do not merge. Do not deploy. Do not APK.
Do not start Ask, What Now, Add/Move, or SPEC-43.

Read `docs/briefs/GENIE_SPEC_45_FIELD_TRUST_HYGIENE_REMAINDER.md`.
Do not edit this brief.

## Verdict on `afcde2a`

Compile-shape fixes for `SwapCandidatesResult` and kind copy look
right. The two product predicates are still not production-wired.

Flutter remains UNVERIFIED. Do not treat pytest as Flutter.

## Must fix

### 1. `nodeShouldShowTodayOutcome` is unused

`git grep nodeShouldShowTodayOutcome mobile/lib` is only the helper.
`ActivityCard` still calls `nodeCanRecordOutcome` (line ~130). Day-1
prompts still flood day-8 on the corridor timeline.

Wire it at the timeline, per date header:

- cards under **today's** destination-local date header use
  `nodeShouldShowTodayOutcome`
- cards under **any other date** header use `nodeCanRecordOutcome`

Pass a bool into `ActivityCard` (for example `restrictOutcomeToToday`)
or choose the helper before building the card. Do not leave a dead
function.

Clock-injected widget or timeline test: a yesterday activity shows a
prompt under yesterday's header and does not show one under today's
header.

R17: `ActivityCard` always uses `nodeCanRecordOutcome`; that test goes
red. Restore.

### 2. `isLastHotelNight` is true for every continuation night

`next` already skips later presentations of the same `nodeId`
(`itinerary_screen.dart` ~744-747). Then the flag is:

```text
!isFirstOccurrence && hotel && (next == null || next.nodeId != node.nodeId)
```

`next.nodeId != node.nodeId` is always true when next exists. Middle
nights become checkout.

Last night means: hotel coverage and **no later item with the same
nodeId**. Scan forward; do not reuse `next`.

One-night stay stays `Checked in?` (first occurrence, no later
coverage). First night of a multi-night stay is check-in; last
coverage date is checkout.

The sheet must get the same flag: `_OutcomeSheet` still calls
`outcomePromptText(node)` without `isLastHotelNight`.

### 3. Python refusal test still does not force empty

`test_forced_empty_region_returns_no_catalog_refusal` falls back to
Luang Prabang and still wraps asserts in `if not data["candidates"]`.
That is the same hole as remainder 1.

Monkeypatch venue search or hours so `_considered > 0` and `results`
is empty, **always** assert `refusal_code` in
`{hours, reachability, no_catalog}` and non-empty copy. No skip when
the catalog is healthy.

## Do not reopen

Cap/coalesce helpers, Review-alternatives lock check, region display
names for flights, SwapCandidatesResult fakes. Those stay.

## Gates

```text
flutter analyze --no-fatal-infos
flutter test
pytest -q tests/test_spec45_trust_hygiene.py
ruff check .
ruff format --check .
git diff --check
grep -rn '\\$' mobile/lib
```

PR update on the same branch. Stop.
