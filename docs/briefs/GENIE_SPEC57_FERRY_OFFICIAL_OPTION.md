# Genie brief: SPEC-57 show official option and source without fare bands

Flutter only. Small. Read all of it before editing.

Owning spec: `docs/specs/SPEC-57-arrival-armor.md`. Data change this brief
depends on: `mobile/assets/arrival_hubs.json` (hub `stone_town_ferry`,
fields `official_option`, `source`, `surveyed_on`), recorded on the PR that
carries this brief.

## 0. Why

The owner recorded published Azam Marine ferry rates as the official option
for the `stone_town_ferry` hub. Those are fixed ticket prices, not a taxi
fare band. Today the Captain HUD shows the official option and the source
line only inside the fare-band block, so a hub with no bands shows neither.
This brief moves those two lines so they show whenever the data has them.

## 1. Preflight (report before coding)

1. Read `mobile/lib/features/arrival_armor/arrival_armor_screen.dart`
   `_body` (about lines 60 to 140). Confirm `official` and `source` and
   `surveyed` are inside the `if (fareHub != null)` block, and say which
   lines of that block would have to move.
2. Read `mobile/lib/features/arrival_armor/arrival_hubs.dart`:
   `hasFare`, `visibleScamNotes`, `hubForBooking`. Confirm `hubForBooking`
   matches on `booking_types` and region only.
3. Confirm the hub JSON in the data change loads: `officialOption`,
   `source` and `surveyedOn` are parsed (`arrival_hubs.dart` lines 40 to 50).
4. Confirm no existing test in `mobile/test/spec57_arrival_armor_test.dart`
   needs to change for this. If one does, stop (section 6).

## 2. Build

Change only the display in `arrival_armor_screen.dart`:

- Show the official option (heading "Published rates", body text as
  stored) whenever `officialOption` is non-empty, whether or not the hub
  has fare bands.
- Show the source line `Source: <source> (<surveyedOn>)` next to it
  whenever both `source` and `surveyedOn` are non-empty.
- Keep the fare-band section, the "Walk-away above" line and the
  "ranges are guides, not guarantees" caption exactly as they are, shown
  only when `hasFare` is true.
- When only the official option shows, use the caption "Published rates.
  Check the price on your booking." (ASCII, no `$`).
- Scam notes behave as today. Empty sections stay omitted.
- Do not put fare or official text on the Driver Card or in Show-to-driver
  mode (SPEC-57 section 3, unchanged).

No change to `arrival_hubs.dart` parsing, to `hubForBooking`, to the
booking sheet, or to any booking type list.

## 3. Do not do this

- Do not add a `ferry` booking type, or any new type. The server's
  scheduler treats `flight` and `train` as travel (`services/day_slots.py`,
  `services/booking_reflow.py`), and `itinerary_normaliser.py` maps only
  `flight`, `hotel` and `train` to travel node types. A new type would be
  scheduled as an activity. The ferry hub stays on `train` until SPEC-55
  transfer cards land, as SPEC-57 already says.
- Do not invent or round any fare. Show the text exactly as stored.
- Do not change the JSON file. It is the owner's data.

## 4. Tests

New file `mobile/test/spec57_official_option_test.dart` (do not edit
existing tests):

1. A hub with null fare bands and a non-empty `official_option` shows the
   official text, the "Published rates" heading and the source line with
   its date.
2. A hub with null fare bands and no official option shows neither, and
   the existing empty state still appears when there are also no scam
   notes.
3. A hub with fare bands still shows the fare-band section, the walk-away
   line and the "ranges are guides" caption, and the official option shows
   too when present.
4. The official-only caption text is exactly "Published rates. Check the
   price on your booking."
5. The Driver Card route and Show-to-driver mode show no official or fare
   text (widget or route test; use the existing Driver Card test helpers).
6. The ferry hub from the real JSON (`stone_town_ferry`) parses and shows
   the Azam Marine text and `Source: https://azammarine.com/rates/`.

Gate: `flutter test` and `flutter analyze --no-fatal-infos` in CI. R1 (no
`\$` in new Dart), R14 (ASCII in new files).

## 5. Pull request and R17

- Branch `feat/spec57-official-option` from current `origin/main`, after
  the data PR is merged.
- One R17 sabotage branch `-r17a`: the official option is again inside the
  fare-band block. Expect tests 1 and 6 to fail. Name the expected failures
  in the PR body.
- Do not merge. The planning agent opens the PR and reads CI. Owner merges.

## 6. Stop rules

Stop and report, quoting the preflight line, if:

1. An existing test in `spec57_arrival_armor_test.dart` must change.
2. The fix needs a new JSON field, a schema change, or a server change.
3. A booking type or the scheduler must change to make the ferry hub show.
4. Showing the official option needs the Driver Card changed.

## 7. Report

PR-ready branch and head SHA; preflight answers 1 to 4; the test-to-code
table; the `-r17a` head and expected failures; any stop rule hit.
