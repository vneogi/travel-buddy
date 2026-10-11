# Genie Brief: SPEC-45 field trust hygiene

> Status: READY. First post-Laos application slice.
>
> Start from clean, current `origin/main`. New branch
> `feat/spec45-field-trust-hygiene`.
>
> Do not merge. Do not deploy. Do not APK.
> Do not start SPEC-25 Ask history, SPEC-46, SPEC-42 Add/Move,
> SPEC-43, catalog patches, or weather-day drill-down.

Read first:

- `docs/WAYS_OF_WORKING.md`
- `docs/ENGINEERING_RULES.md`
- `docs/AWAITING_VERIFICATION.md` (11 Oct 2026 finding)
- `docs/specs/SPEC-45-on-trip-visible-surface.md` (Phase B)
- `docs/specs/SPEC-29-context-alerts.md`
- `docs/specs/SPEC-30-retention-instrumentation.md`
- `docs/specs/SPEC-35-proactive-itinerary-notifications.md`

Do not edit this brief.

## Why this slice

Owner Laos use: first open showed 20-plus alerts/reviews; some Review
actions did nothing; old-day "Did this happen?" stayed visible; flights
and hotels used the same outcome copy; empty swaps did not explain why.

This slice restores trust in the current itinerary surface. It does not
build the Ask/What Now/Add/Move loop.

## Scope -- five defects, nothing else

### 1. Cap the advisory flood

Today `ItineraryAlertsSection` renders every unexpired, undismissed
weather alert as its own card. Schedule warnings from
`state.scheduleWarnings` also stack above the timeline.

Required:

- Primary surface shows at most **two** alert/advisory cards.
- Prefer the highest-severity, currently valid, destination-local-today
  items. Coalesce duplicate messages for the same local day + type.
- Remaining items collapse behind one row: `N more alerts`.
- Schedule-issue banner uses only warnings whose matched node is on the
  **current destination-local date**. Older days stay in the trip but
  do not occupy Today.
- Do not invent a new notification transport. SPEC-27 push stays off.

### 2. Outcome prompts are today-only and kind-specific

`nodeCanRecordOutcome` currently returns true for any pending node whose
`scheduledStart` is in the past. That keeps day-1 prompts on day-8.

Required:

- Prompt only when the node's destination-local date is **today**, or
  the node is in the current window.
- Past-day unconfirmed nodes stay recordable from their day section if
  the traveller scrolls there; they must not appear as a Today flood.
- Card button and `_OutcomeSheet` title use booking kind:

  - flight: `Arrived in [city]?` / Yes I arrived / No
  - hotel first night: `Checked in?`
  - hotel last night / checkout node: `Checked out?`
  - tour: `Did the tour happen?`
  - else: `Did you visit?`

- Keep the same `visited_confirmed` / `node_skipped` signals. Copy only.
- City for flights: existing node/city/segment label. If missing, use
  `Arrived?` -- never invent a city.

### 3. Hide dead Review actions

`Review alternatives` currently renders whenever
`suggestedAction == 'review_outdoor_plans'` and a node id exists. The
handler then no-ops on locked bookings.

Required:

- Render `Review alternatives` only when the first affected node is
  unlocked and the client would actually open SwapSheet.
- Locked flight/hotel/train nodes keep `View stop` only.
- Schedule-issue `Review` still opens the warning sheet. Rows still
  Open stop. Do not add a fake Fix it / Rescue button.

### 4. Empty swap explains the constraint

SwapSheet already shows `No alternative venues found nearby.` when the
list is empty. Field use still looked like a broken control.

Required:

- Keep the honest empty state. Do not invent venues.
- If the swap/search response already carries a refusal reason, show it
  in plain language: hours, walking/reachability, locked neighbour, or
  no catalog alternative in this slot.
- If the server does not yet send a reason, add a typed optional field
  on the existing swap-candidate path (`refusal_code` / `refusal_copy`)
  and map known SPEC-41 failures. Do not add a second search endpoint.
- Copy must not say the itinerary was swapped.

### 5. Stale schedule reviews leave Today

Old schedule reviews remaining after the day ended is a separate copy of
(1). Implement by filtering `scheduleWarnings` to today's matched nodes
before the banner count. Dismiss still works. Do not delete history from
the trip payload unless the server already expires those strings.

## Files likely in play

- `mobile/lib/features/itinerary/itinerary_screen.dart`
  (`ItineraryAlertsSection`, `_ScheduleWarningsBanner`, `_OutcomeSheet`)
- `mobile/lib/widgets/activity_card.dart`
- `mobile/lib/widgets/alert_card.dart`
- `mobile/lib/features/itinerary/current_window.dart`
- `mobile/lib/features/itinerary/warning_helpers.dart`
- `mobile/lib/features/alerts/alerts_notifier.dart`
- `mobile/lib/features/swap_sheet/swap_sheet.dart`
- swap-candidate API / `agents/state_machine.py` only if needed for
  refusal_code

Extract helpers. Do not grow `itinerary_screen.dart` with inline policy.

## Tests

Widget / unit, clock injected (`now`):

- 12 unexpired alerts -> 2 cards + `N more alerts`
- coalesced duplicate rain alerts for the same day count as one
- schedule banner hidden when all warnings match yesterday
- `Did this happen?` absent on a yesterday activity while viewing today
- yesterday activity still shows a prompt when that day section is shown
- flight / hotel / tour / activity use the kind-specific strings
- Review alternatives absent for a locked hotel with a weather alert
- Review alternatives present for an unlocked outdoor activity
- empty SwapSheet shows the existing nearby copy plus a reason when the
  stub returns `no_candidates` / hours / reachability
- locked bookings still cannot swap
- confirm-before-mutate swap still required when candidates exist

R17: force `visible` to return the unfiltered list; the cap test goes
red. Restore.

Keep existing SPEC-30 / SPEC-31 / SPEC-45 / G0 swap tests green; update
their copy assertions where they hard-code `Did this happen?`.

```text
flutter analyze --no-fatal-infos
flutter test
pytest -q
ruff check .
ruff format --check .
git diff --check
grep -rn '\\$' mobile/lib
```

Flutter UNVERIFIED on Databricks. R1 after Dart writes. Do not quote
pytest counts into living docs (R16).

## Out of scope

- SPEC-25 durable Ask / place prompts / trip-optional Ask
- SPEC-46 What Now / Rescue / Hungry
- SPEC-42 Add / Move / drag-reorder
- catalog adds (Kuang Si, Pak Ou, Blue Lagoon, Papao)
- packing / Wat Xieng Thong ranking
- maps, GPS, Travelogue, gamification
- production LLM, SPEC-43, non-owner APK
- silent auto-reflow
- weather forecast drill-down (still a later SPEC-29 remainder)

## Stop

PR against `main`. Planning reviews the diff. Owner laptop Flutter is
not claimed from this machine.
