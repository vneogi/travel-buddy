# Genie brief: SPEC-53 slice 1, situation chips in chat

Read this whole file before touching anything. It is the complete job.
If something here is unclear, stop and ask; do not guess and do not
widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA.

Owning spec: `docs/specs/SPEC-53-situation-chips.md`. Parents:
SPEC-46 (What Now) and SPEC-25 (trip Ask thread). This slice is
Flutter-only. No backend, no new endpoint, no migration, no Cloud Run
deploy.

## 0. Context

The chat screen already has a "What now?" button that opens a form
(time, energy, walking, intent) and sends the choices to the existing
What Now path. Typing the same choices on a phone, on the move, is the
friction. Slice 1 adds a short row of one-tap chips above the input.
Each chip is a fixed, named bundle of the same four settings and sends
through the same path.

Verified on `main` (re-verify in preflight):

1. `_openWhatNowSheet` / `_sendWhatNow` in
   `mobile/lib/features/chat/chat_screen.dart` send
   `tripEvents.sendEvent(type: EventType.askInfo, message: 'What now?',
   preferences: {mode, available_minutes, energy, walking, intent,
   context_node_id?})`. Offline, `_sendWhatNow` adds the offline refuse
   entry and returns without sending or queuing.
2. The backend routes on `preferences.mode == 'what_now'`
   (`agents/state_machine.py`), not on the message text. Allowed values
   (`WhatNowRequest` in `services/ask_service.py`): minutes 45, 90, 120;
   energy low, normal, high; walking short, normal, longer; intent
   quiet, food, indoors, culture, anything.
3. The engine's intent filter is by venue category only
   (`_WHAT_NOW_INTENT_MAP`): "indoors" means museum, cafe, restaurant,
   massage_spa. It does not know about rain, AC, crowds or weather.
4. The chat controller lifetime fix is on main (PR #260, owner device
   check passed 2026-11-16), so sends from chat opened from Home work.

## 1. Goal

A horizontally scrollable row of four text chips in `ChatScreen`, next
to the existing "What now?" button, above the input bar. One tap sends
What Now immediately with that chip's fixed settings. The result is the
existing What Now bubble. The user bubble shows the chip label.

The four chips (labels are exact; do not rename, add or reorder):

| id | Label | available_minutes | energy | walking | intent |
|---|---|---|---|---|---|
| `quick_break` | Quick break | 45 | low | short | anything |
| `low_energy` | Low energy | 90 | low | short | quiet |
| `indoors` | Indoors | 90 | normal | short | indoors |
| `food` | Something to eat | 90 | normal | normal | food |

Each also sends `mode: 'what_now'` and, when the default context stop
exists, `context_node_id` (same helper the sheet uses:
`_defaultWhatNowContextNode()`).

Deliberately NOT in this slice, and recorded in SPEC-53: "Head back"
(the engine has no return-to-hotel intent) and "Find shelter" (the
engine cannot know shelter or weather; "Indoors" is the honest label).
Do not add either, and do not add any label that claims rain cover, AC,
quiet levels, opening status, distance in km, or anything the engine
does not compute.

Behaviour that must not change: the What Now sheet and its keys, the
"What now?" button and its key `what_now_entry`, `_send`, the Ask-to-Add
path, the What Now bubble, routing, backend, and every existing test
assertion.

## 2. Preflight

1. `git fetch origin`. Work from the base SHA in the message that sent
   this brief.
2. Confirm on that SHA: `_sendWhatNow` and `_WhatNowEntryBar` exist in
   `chat_screen.dart` as described; `ChatScreen` has the
   `ref.listenManual(itineraryControllerProvider(...))` hold from #260;
   `docs/specs/SPEC-53-situation-chips.md` exists. If any differs, stop
   and report.
3. Confirm `mobile/lib/features/chat/situation_chips.dart`,
   `mobile/test/spec53_situation_chips_test.dart` and
   `origin/feat/spec53-situation-chips` do not exist.
4. Branch: `feat/spec53-situation-chips`.

## 3. Read before editing

- `docs/specs/SPEC-53-situation-chips.md`,
  `docs/specs/SPEC-46-what-now-foreground-context.md`
- `docs/ENGINEERING_RULES.md` R14, R16, R17
- `mobile/lib/features/chat/chat_screen.dart` (`_defaultWhatNowContextNode`,
  `_openWhatNowSheet`, `_sendWhatNow`, `build`, `_WhatNowEntryBar`,
  `_WhatNowSheet`)
- `mobile/test/spec46_what_now_test.dart` (the harness you reuse:
  in-memory `OfflineDatabase(testPath:)`, `_FakeConnectivity`, mocked
  `tripEventProvider`, `tester.runAsync` + flush; no `pumpAndSettle`)
- `mobile/test/chat_controller_lifetime_test.dart` (do not change it)

## 4. Files you may touch

- `mobile/lib/features/chat/situation_chips.dart` (new): the chip
  definitions and the chip row widget.
- `mobile/lib/features/chat/chat_screen.dart`: (a) give `_sendWhatNow` an
  optional named `String text = 'What now?'` parameter used for the user
  bubble, the persisted user row and the `sendEvent` `message`, with the
  existing call site unchanged; (b) render the chip row in `build`
  beside the existing entry button. Nothing else in this file.
- `mobile/test/spec53_situation_chips_test.dart` (new).

Nothing else. No backend, no docs (the planning agent owns docs), no
router, no `pubspec`, no theme or design-token files, no existing test
file.

## 5. Implementation

`situation_chips.dart`:

- `class SituationChip { final String id; final String label; final int
  availableMinutes; final String energy; final String walking; final
  String intent; }` as `const`, plus `const List<SituationChip>
  kSituationChips` in the table order above, and a method
  `Map<String, dynamic> preferences({String? contextNodeId})` returning
  the exact map from section 1 (`mode`, the four settings, and
  `context_node_id` only when non-null).
- `class SituationChipRow extends StatelessWidget` with `enabled`,
  `onSelected(SituationChip)`. A horizontally scrolling `ListView` (or
  `SingleChildScrollView` + `Row`) of `ActionChip`s, key
  `Key('situation_chip_<id>')`. Minimum tap target 44dp high. Existing
  `AppSpacing`/theme tokens only; do not add colours or fonts.
- Plain text labels, no icons required; if you add an icon it must be
  decorative (excluded from semantics). Each chip is a button in
  semantics with its label.

`chat_screen.dart`:

- Layout: the existing "What now?" button stays first and keeps key
  `what_now_entry`; the chip row follows it in the same row if it fits,
  otherwise as a second scrollable line. Both are disabled while
  `_isThinking`. At 360dp width and 2.0 text scale nothing may overflow
  and every chip stays reachable by scrolling.
- Chip tap: `_sendWhatNow(chip.preferences(contextNodeId:
  _defaultWhatNowContextNode()?.nodeId), text: chip.label)`.
- Do not add a confirm step. Do not mutate the itinerary. Adding a
  result to the plan stays the existing "Add to plan" confirmation.
- Offline behaviour is the existing one (offline refuse entry, no
  send, nothing queued). Do not add a queue.

## 6. Tests

`mobile/test/spec53_situation_chips_test.dart`, exact names. Reuse the
spec46 harness. Mock `tripEventProvider` as spec46 does (the real
controller lifetime is already covered by PR #260's tests).

Unit (no widgets):

1. `chip presets use only values the backend accepts`: every chip's
   minutes are in {45, 90, 120}, energy in {low, normal, high}, walking
   in {short, normal, longer}, intent in {quiet, food, indoors, culture,
   anything}. Put the allowed sets in the test, with a comment naming
   `WhatNowRequest.ALLOWED_*` in `services/ask_service.py` as the source.
2. `chip labels and order are exact`: Quick break, Low energy, Indoors,
   Something to eat.
3. `preferences omit context_node_id when none`, and `include it when
   given`.

Widget:

4. `chip row renders four chips next to the What now button`.
5. `tapping Quick break sends the exact What Now preferences`: capture
   the `sendEvent` arguments: `type` askInfo, `message` 'Quick break',
   `preferences` equal to the table row plus `mode` and the context node
   id from the seeded itinerary. Result bubble appears (use the same
   `_whatNowResponse()` style fixture as spec46); the user bubble reads
   "Quick break", not "What now?".
6. `each chip sends its own preset`: loop over all four.
7. `chips are disabled while a request is in flight`: hold the
   `sendEvent` future with a `Completer`; chips and the What now button
   are disabled; a second tap sends nothing; complete and they re-enable.
8. `offline tap refuses and sends nothing`: connectivity false; offline
   refuse entry shown (`ask_offline_refuse`), `sendEvent` never called,
   thread has the user row only, and no outbox row.
9. `no context stop omits context_node_id`: itinerary with no usable
   stop.
10. `chip row has no overflow at 360dp and 2.0 text scale`: pump at that
    size and scale, no `FlutterError` overflow, last chip reachable by
    scrolling.
11. `chips keep 44dp tap targets and button semantics`.
12. `history reopens with the chip label`: send a chip, start a new
    widget over the same thread, user entry shows "Quick break" and the
    stored What Now envelope renders display-only (no Add to plan), as
    spec46 does for reopened results.

## 7. R17

Run each, confirm the named test fails, then restore and confirm green:

A. Change `quick_break` minutes from 45 to 90: tests 5 and 6 fail.
B. Make the chip row `enabled: true` always: test 7 fails.
C. Remove the `text:` pass-through (always 'What now?'): tests 5 and 12
   fail.
D. Change a chip's intent to a value outside the allowed set: test 1
   fails.

## 8. Stop rules

Stop and ask if:

- the chip row needs any file outside section 4;
- an existing test needs an assertion changed (an import-only change
  is also a stop: there should be none);
- you want to add a chip, rename a label, or add any claim about rain,
  AC, crowds, quiet, hours or distances;
- you want a new endpoint, a backend change, or to queue anything
  offline;
- the layout cannot meet 360dp and 2.0 text scale without changing the
  What Now button's key or behaviour.

## 9. Gates

```
cd mobile && flutter analyze && flutter test
git diff --check
```

`flutter analyze` 0 issues, `flutter test` all passed. ASCII only in
every touched file. Do not add `SPEC-NN` references except to numbers
with a file under `docs/specs/`.

The Mac has no Flutter. If you also lack it, say so and rely on CI (the
planning agent will run CI on the PR); do not install Flutter without
the owner's approval.

## 10. Delivery

One commit on `feat/spec53-situation-chips`:
`feat: SPEC-53 situation chips send What Now in one tap`.
Push and verify the remote SHA. Do not merge. No `gh`. No APK build or
Cloud Run deploy.

## 11. Report

1. Base SHA.
2. Branch and remote SHA.
3. `flutter analyze` and `flutter test` last lines (or "no Flutter,
   CI only").
4. `git diff --check` result.
5. Files touched, with +/- counts.
6. R17 A, B, C and D results.
7. Confirmation that the sheet, `what_now_entry`, `_send`, Ask-to-Add,
   the What Now bubble, routing and the backend are unchanged.
8. Layout choice (same row or second line) and why.
9. Anything you were unsure about.

## 12. Owner device check (after merge and APK rebuild)

Open a trip chat (Home chat icon, then once from the itinerary Ask bar).
Tap each chip once: Quick break, Low energy, Indoors, Something to eat.
Expect a What Now result bubble each time, with the user bubble showing
the chip label. "Something to eat" should return food or cafes only,
"Indoors" museums, cafes, restaurants or spas only. Switch to airplane
mode and tap a chip: expect the offline message and nothing queued.
Check the row scrolls and nothing is clipped at the largest system
font size.
