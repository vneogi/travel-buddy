# Genie brief: SPEC-57 sourced flat-fare cards and official option display

Flutter only. Supersedes `GENIE_SPEC57_FERRY_OFFICIAL_OPTION.md` (PR #394), which was withdrawn and removed on 2026-11-27.
Read all of it before editing.

Owning spec: `docs/specs/SPEC-57-arrival-armor.md`, Amendment 1 (ferry
official option) and Amendment 2 (sourced flat-fare cards, 2026-11-27).

## 0. Scope in one paragraph

The Captain HUD (`mobile/lib/features/arrival_armor/`) gets two display
changes. (a) The hub's official option and its source line show even when
the hub has no fare bands. (b) A new "Typical fares" section shows sourced,
dated flat-fare cards from a new `flat_fares` list in the hub JSON. No
computed fare, no formula, no routing, no new booking type, no network call.

## 1. Gate and rules

- Flutter only. No server change, no new dependency. CI is the gate:
  `flutter test` and `flutter analyze --no-fatal-infos`. Genie has no
  Flutter SDK; CI is the first compile.
- R1 (no `\$` in Dart), R14 (ASCII in new files and docs), R16 (no
  hard-coded test counts in docs).
- Do not edit `mobile/assets/arrival_hubs.json`. It is owner data. Genie
  may read it. Only the owner (data PRs) writes fare numbers.
- Do not edit existing tests in `mobile/test/spec57_arrival_armor_test.dart`.

## 1a. Decisions already made (owner, 2026-11-27)

- Heading: "Official option" everywhere (option C). Do not use "Published
  rates" as a heading. Existing test at `spec57_arrival_armor_test.dart`
  line 235 stays unchanged.
- Base: build from `origin/main` after the ferry data PR (#394) is merged.
  Do not stack on `feat/ferry-rates-data`.
- The ferry-only brief (`GENIE_SPEC57_FERRY_OFFICIAL_OPTION.md`) was withdrawn
  and removed on 2026-11-27 and is not to be used. Its "Published rates" heading is withdrawn.
- Preflight item 1 and the empty-state gap found by Genie are accepted.

## 2. Preflight (report before coding)

1. `arrival_armor_screen.dart` `_body`: confirm `official`, `source` and
   `surveyed` sit inside `if (fareHub != null)`. Name the lines to move.
2. `arrival_hubs.dart`: confirm `hasFare` requires both bands, and that
   `officialOption`, `source`, `surveyedOn` parse (lines about 40 to 60).
3. Confirm `hubForBooking` matches on `booking_types` and region only.
4. Confirm the current JSON shape and that `flat_fares` is absent today
   (no hub has it).
5. Confirm no existing test in `spec57_arrival_armor_test.dart` needs a
   change. If one does, stop (section 7).

## 3. Build

### 3.1 Model (`arrival_hubs.dart`)

Add `FlatFare` (immutable): `route`, `vehicle`, `currency`, `low`, `high`,
`basis`, `source`, `surveyedOn`. Add `List<FlatFare> flatFares` to
`ArrivalHub`, parsed from `flat_fares` (default empty list when missing).

A `FlatFare` is valid only when: every string field is non-empty after
trimming; `currency` is a 3-letter uppercase code; `low` and `high` are
integers with `0 < low <= high`; `surveyedOn` is an ISO date that parses.
Parse invalid entries as skipped (not as an error, not repaired). Expose
`validFlatFares` for the screen.

### 3.2 Screen (`arrival_armor_screen.dart`)

- **Official option (Amendment 1).** Show the heading "Official option"
  (the existing constant and test expectation, unchanged) and the stored
  official text whenever `officialOption` is non-empty, whether or not the
  hub has bands. One heading for one field; do not add "Published rates" as
  a heading. Show `Source: <source> (<surveyedOn>)`
  whenever `source` and `surveyedOn` are both non-empty. Keep these
  outside the fare-band block.
- **Typical fares (Amendment 2).** When `validFlatFares` is non-empty, show a
  "Typical fares" heading, then one line per card: `route`, `vehicle`, the
  range `low - high <currency>`, `basis`, and `Source: <source>
  (<surveyedOn>)`. Show the caption "Guides only. Agree the price before you
  get in." once under the section.
- Keep the existing fare-band section ("Fair fare guide", "Walk-away
  above", and the caption constant `kArrivalFareCaption`, which reads
  "Guides only -- confirm before you pay.") exactly as it is, shown only
  when `hasFare` is true. The caption text is the constant, not a phrase
  from memory.
- The empty state `kArrivalEmptyHub` ("No verified fare or tip sheet for
  this hub yet.") shows only when the hub has no fare band, no scam notes,
  no official option and no valid flat fare. Today the check is only
  `fareHub == null && notes.isEmpty`; add the official-option and
  flat-fare conditions, otherwise the ferry hub shows the empty message
  under its official text.
- Omit any empty section entirely. An incomplete card is skipped with no
  placeholder text.
- Nothing computed: no midpoint, no multiplied upper bound, no converted
  currency, no "about" text. Show `low` and `high` exactly as stored.
- No fare or official text on the Driver Card or in Show-to-driver mode.

### 3.3 Booking type

No change. The ferry hub stays on `train` until SPEC-55 transfer cards land.
Do not add a `ferry` type: the server treats `flight` and `train` as travel
(`services/day_slots.py`, `services/booking_reflow.py`), and
`services/itinerary_normaliser.py` maps only `flight`, `hotel` and `train`
to travel node types. A new type would be scheduled as an activity.

## 4. Tests

New file `mobile/test/spec57_flat_fares_test.dart`. Do not edit existing
tests.

1. A hub with null bands and a non-empty `official_option` shows the
   "Official option" heading, the stored text and the source line with its
   date, and does not show the empty message.
2. A hub with null bands and no official option shows neither.
3. A hub with bands still shows the fare-band section, the walk-away line and
   the "ranges are guides" caption; the official option shows too when set.
4. A hub with no `flat_fares` key shows no "Typical fares" section.
5. A complete card shows route, vehicle, `low - high currency`, basis and
   source with date, plus the caption "Guides only. Agree the price before you
   get in."
6. Each incomplete or invalid card is skipped: null `low`, `low > high`,
   missing `source`, missing `surveyed_on`, unparseable date, lowercase or
   missing currency. Neighbouring valid cards still show. No placeholder text
   appears.
7. No computed value appears: the rendered text for a card contains only the
   stored numbers (assert no midpoint and no multiple of `high`).
8. The ferry hub from the real JSON parses and shows the Azam Marine text and
   `Source: https://azammarine.com/rates/`.
9. The Driver Card route and Show-to-driver mode show no official or fare
   text.

## 5. Pull request and R17

- Branch `feat/spec57-flat-fares` from `origin/main`. Merge order: the data
  PR (#394) first, or rebase onto it; the data file must already have the
  ferry entry.
- R17 sabotage branches, one commit each from the feature head:
  - `-r17a`: compute a midpoint or an upper bound and show it (expect tests
    5 and 7 to fail).
  - `-r17b`: show a placeholder when a card is incomplete (expect test 6).
  - `-r17c`: put the official option back inside the fare-band block (expect
    tests 1 and 8).
  Name each expected failure in the PR body.
- Do not merge. The planning agent opens the PR, reads CI, and the owner
  merges.

## 6. Non-goals

- No formula, rate, waiting-time, surcharge or multiplier.
- No road routing, distance or time service.
- No fare-paid prompt, signal or personal-data capture.
- No runtime network fetch of fares.
- No booking-type change, no scheduler change, no server change.
- No new JSON data, no edits to fare numbers.

## 7. Stop rules

Stop and report, quoting the preflight line, if:

1. An existing test in `spec57_arrival_armor_test.dart` must change. (The
   heading decision above means none should; if one seems to, stop.)
2. Any part needs a server, schema-migration or scheduler change.
3. Any part needs a number the JSON does not contain, or a computed value.
4. A booking type must change to show a hub.
5. Showing fares needs the Driver Card or Show-to-driver changed.

## 8. Report

PR-ready branch and head SHA; preflight answers 1 to 5; the test-to-code
table; the three R17 heads with their expected failures; any stop rule hit.
