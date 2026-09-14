# Genie Brief: SPEC-41 Phase A1 -- Structured Hours Core

Start a new branch from `origin/main` at or after `ebdea52`:

```text
feat/spec41-hours-core
```

Do not merge. Do not deploy. Do not build an APK.

Read first:

- `docs/specs/SPEC-41-hours-aware-scheduling.md`
- `docs/ENGINEERING_RULES.md`
- `docs/WAYS_OF_WORKING.md`

Do not edit this brief.

## Goal

Build and prove the canonical structured-hours evaluator and preserve structured
hours through both database providers. This is substrate only: do not change
create, corridor, swap, scheduler, Flutter, or warning behavior in this commit.

The later Phase A2 and A3 commits will consume this evaluator. Keeping the core
separate makes weekday, split-window, overnight, unknown, and provider-parity
failures reviewable before itinerary behavior changes.

## Current defect

The curated Laos rows carry `opening_hours_structured`:

```text
{
  "mon": [["08:00", "12:00"], ["13:00", "16:00"]],
  ...
  "sun": []
}
```

The application currently:

- flattens the first non-empty window into one `HH:MM-HH:MM` string;
- loses weekday, closed-day, and later-window information;
- reads `opening_hours` rather than `opening_hours_structured` from Supabase;
- seeds in-memory `VenueRAG` without preserving the structured value;
- treats unparseable string hours as open in `maps_service`.

Do not fix those consumers yet. This commit creates the one source they will
use and proves both providers return the same structured field.

## 1. Canonical result and evaluator

Add a small module such as:

```text
services/opening_hours.py
```

Expose one public slot evaluator with a typed result:

```text
fits
closed
unknown
```

Inputs:

- structured hours dict or null;
- timezone-aware destination-local start datetime;
- positive duration in minutes.

Rules:

1. Null or malformed hours => `unknown`.
2. A valid weekday key with an empty list => `closed`.
3. Start and end must fit inside the same declared window.
4. Start exactly at opening and end exactly at closing fit.
5. Split windows are independent; a slot crossing the closed gap is `closed`.
6. `close > open` is a same-day window.
7. `close <= open` is an explicit overnight window ending the following day.
8. An early-morning slot may be covered by the previous local day's overnight
   window.
9. A slot cannot be accepted by combining two adjacent or separate windows.
10. Invalid time text, missing weekday keys, wrong container shapes, zero or
    negative duration, or a naive datetime never default to open.

Choose whether invalid duration/naive datetime raises a narrow programmer error
or returns `unknown`, then freeze that decision in tests. Malformed catalog data
must not raise through a request path.

Do not call Maps, an LLM, the server clock, or `datetime.now()`.

## 2. Model and provider parity

Add optional `opening_hours_structured` to the Python venue model with a safe
default so old rows still parse.

Supabase:

- `list_venues_for_region` selects and returns
  `opening_hours_structured`;
- `get_venue_by_id` selects and returns it.

In-memory:

- Laos seed loading preserves the original structured dict on `VenueRAG`;
- `list_venues_for_region` and `get_venue_by_id` return the same shape;
- legacy hardcoded Dubai fixtures with only string hours still parse with
  structured hours null.

Do not add a migration. Migration 0008 and the hosted column already exist.
Do not remove the legacy `opening_hours` string yet; current clients and
scheduler still consume it.

## 3. Required tests

Add focused tests that fail if the evaluator is replaced with the current
flattened-string behavior.

Evaluator:

- Monday morning slot fits;
- same slot on a weekday whose list is empty is closed;
- first split window fits;
- second split window fits;
- lunch-gap start is closed;
- slot starting before close but ending after close is closed;
- exact open/close boundaries fit;
- Monday evening to Tuesday early morning overnight fits;
- Tuesday early-morning lookup finds Monday's overnight window;
- same early-morning slot without the previous overnight window is closed;
- null and malformed structures return unknown;
- missing weekday key returns unknown;
- naive datetime and invalid duration follow the frozen programmer-input rule.

Real-data golden cases:

- use one committed Laos venue with split windows;
- use one committed night market or evening-only venue;
- use one committed closed weekday;
- assert against destination-local aware datetimes, not UTC-shaped values with
  a replaced `tzinfo`.

Provider parity:

- in-memory list and get preserve structured hours;
- mocked Supabase list and get select/preserve the structured column;
- old venue rows without the field still parse;
- no provider invents `09:00-23:00` structured hours.

Sabotage:

- replace weekday selection with Monday for every date and name the golden test
  that fails;
- ignore the second split window and name the test that fails;
- default null to open and name the test that fails;
- remove `opening_hours_structured` from each provider projection and name the
  parity test that fails.

Restore production code after sabotage. Record the failing test names in the
commit message or Genie report.

## Explicitly out

- changing `TripNode`;
- filtering create or corridor venues;
- changing four-stops-per-day behavior;
- changing swap search or apply;
- changing `reschedule_and_validate`;
- deleting `flatten_opening_hours`;
- changing warning copy or UI;
- live Google Places hours;
- transit estimates;
- party/interests/personalization;
- migrations;
- Flutter.

## Gates

```text
pytest -q <new focused hours tests>
pytest -q -ra
ruff check .
ruff format --check .
```

Commit and push the new branch. Report the SHA and the named sabotage results.
Stop for review.
