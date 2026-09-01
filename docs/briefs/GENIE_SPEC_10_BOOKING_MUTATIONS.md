# Genie Brief -- SPEC-10 Booking Edit and Delete

> Status: QUEUED AFTER SPEC-31. Do not implement on the SPEC-31 branch.
> Read the "Remainder" section of
> `docs/specs/SPEC-10-booking-anchors.md` before starting.

## Goal

Let a traveller reopen, edit, and delete an existing locked booking without
creating a new node, burning reroute quota, or exposing reservation details to
an LLM.

This is one structural-mutation PR after SPEC-31. It is not date grouping and
not multi-night stay modeling.

## Backend contract

Add `edit_booking` and `delete_booking` to the Python and Dart EventType enums.
Both use the existing `POST /trip/event` and require `target_node_id`.

Router policy:

- target must exist and be `node_kind == "booking"`,
- missing target -> typed 404,
- non-booking target -> typed 409,
- neither event is in the reroute quota set,
- locked-cancel refusal remains unchanged,
- both events use a deterministic/light path and canned response,
- neither event sends trip state or confirmation code to an LLM.

Edit:

- patch only supplied booking fields,
- preserve `node_id`,
- preserve `node_kind == "booking"` and `is_locked == true`,
- preserve omitted fields,
- if start/duration changes, move the same node to chronological position and
  call `reschedule_and_validate`,
- keep hotel background-anchor behavior,
- return scheduler warnings through the existing response.

Delete:

- remove the booking node,
- do not mark it skipped,
- reschedule remaining nodes,
- do not route through `cancel_activity`.

No Supabase column or signal migration is needed.

## Client contract

Give `AddBookingSheet` an explicit edit mode with an existing `TripNode`.

- Prefill type, title, start, duration, confirmation code, notes, and import
  source.
- Save sends `edit_booking` with the existing `node_id`.
- An already-started booking remains a valid edit value.
- Create behavior remains unchanged.

Booking cards expose Edit and Delete. Delete opens a confirmation naming the
booking. Keep/dismiss sends zero events; confirm sends exactly one
`delete_booking` with the displayed `node_id`.

Include every displayed editable field in the ActivityCard rebuild signature so
a notes-only edit renders.

## Privacy

- Never log confirmation code.
- Never include confirmation code, notes, place name, or source text in a
  lifecycle signal.
- Do not add edit/delete signals in this slice.
- Do not use the heavy route or model-generated response.

## Required tests

Backend:

- edit preserves node ID and lock,
- partial edit preserves omitted fields,
- time edit reorders the same node,
- edited hotel remains a background anchor,
- delete removes rather than skips,
- missing and non-booking targets refuse,
- edit/delete do not call quota consumption,
- edit/delete do not call the LLM,
- captured logs contain no confirmation code,
- cancel on a locked booking still returns the existing refusal.

Client:

- edit sheet prefills every booking field,
- save sends `edit_booking` and target node ID,
- already-started date can remain selected,
- notes-only edit rebuilds the card,
- delete Keep/dismiss sends zero calls,
- delete confirm sends one call for the named node,
- processing guard prevents duplicate submit,
- create-only tests remain green.

## Sabotage proofs

1. Recreate the booking with a new node ID: stable-ID test fails.
2. Put edit/delete in the quota set: no-quota test fails.
3. Route either event through heavy: no-LLM test fails.
4. Delete by cancel/skip: removal test fails.
5. Drop an omitted field during edit: partial-patch test fails.
6. Remove notes from the card signature: notes-only render test fails.
7. Bypass delete confirmation: Keep-zero-call test fails.

## Explicitly out

- SPEC-31 grouping/rescue,
- `day_index`,
- `trip_stay`,
- check-in/check-out columns,
- multi-night redesign,
- PDF/screenshot/provider import,
- Laos creation.

## Verification and report

Run full Python and Flutter gates plus `git diff --check`. Report branch/SHA,
files, event policy, stable-ID proof, quota/LLM proof, privacy proof, and all
sabotage results. Do not open a PR until review is requested.
