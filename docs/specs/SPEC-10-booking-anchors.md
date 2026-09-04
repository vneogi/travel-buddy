# SPEC-10: Manual Booking Anchors

> Status: CREATE AND EDIT/DELETE IMPLEMENTED (PR #20, PR #37).
> Windows Sep 4 verified notes on card, edit, and delete. Multi-night stays
> remain out.
>
> Resequenced to follow SPEC-16. A booking anchor is a locked node. Once nodes
> are rows rather than keys inside a JSON blob, this spec is a few columns and a
> scheduler rule; built against the blob first, it gets built twice.
>
> No migration number is claimed here. Numbers are taken at implementation time,
> because pre-allocating them turns a change of priority into a renumbering
> exercise.

## Goal

Let the user record bookings (flight, hotel, train, tour) as immovable anchors,
so the engine plans around the trip that actually exists. Unlocks "early flight
tomorrow, take a cab back" and "best food near your hotel".

## Design: import is the primary path, manual entry is the floor

An earlier draft of this spec treated manual entry as first-class and import as a
later luxury. That is backwards. Four fields per booking, times half a dozen
bookings, lands on the user at the moment they are busiest, and a trip whose
anchors are half-entered is worse than one with none because the scheduler
plans confidently around a false picture.

So the order is:

1. **Forwarded confirmation email.** The majority of bookings made online arrive
   as structured-enough email. This is the highest-yield path.
2. **PDF or screenshot.** Covers app-only bookings and printouts.
3. **Manual entry.** Four fields: booking type, date and time, place, plus
   optional code and notes. This is the floor, not the aspiration, and it must
   stay because target markets genuinely have unparseable bookings -- paper
   tickets, Lao-language SMS, a photo of a hotel voucher.

Every import path must degrade into manual entry with the fields it managed to
extract pre-filled, never fail closed.

**Direct platform APIs do not solve this.** Booking.com, Trip.com and their peers
expose affiliate and inventory APIs, which exist so you can sell their stock.
They are not "read this user's reservations" APIs. Integrating them is a revenue
decision, not an import mechanism, and conflating the two has already cost one
round of discussion. Record it here so it is not re-proposed.

## Extraction runs on the device wherever it can

A boarding pass, a hotel voucher and a train ticket are the most sensitive
documents this app will ever handle. They carry names, codes and sometimes card
or passport fragments, which is why the privacy rules below exist at all. So the
preferred implementation of the email, PDF and screenshot paths is extraction on
the device, with only the derived anchor fields leaving it.

This is not aspirational. Shots Studio, an open-source Flutter app, already turns
a folder of screenshots into a structured archive using a small on-device model,
and this is an easier task than that one: a short document, a fixed vocabulary,
and a handful of fields to find.

Where on-device extraction is not viable, because the device is old or the format
defeats the local model, server-side extraction requires explicit per-import
consent, the document is deleted as soon as the fields are extracted, and it is
never retained as training data. `import_source` records which path ran, not the
document it read.

This is the SPEC-15 rule applied to a higher-stakes document: keep the raw thing
on the device, sync only what was derived from it.

## Data model: reuse the node

A booking is a locked node with extra metadata:

| Field | Type | Default |
|---|---|---|
| node_kind | enum | activity |
| booking_type | enum/null | null |
| confirmation_code | string/null | null |
| booking_notes | string/null | null |
| import_source | enum/null | null |

All fields MUST have defaults, for the deserialization reason that bit UserTier.
`import_source` records which path produced the booking (`email`, `pdf`,
`screenshot`, `manual`), because an anchor extracted by a parser deserves less
trust than one a human typed, and the scheduler should be able to tell.

## Privacy: confirmation_code

- Never log `confirmation_code`.
- Prefer client-side only. The scheduler needs time and place, not the code.
- Do not collect passenger names. The app stays free of that class of PII.
- An imported email may contain far more than the booking. Extract the four
  fields and discard the rest; do not retain the source document.

## Scheduler behaviours

1. Hard time constraint: a 07:00 flight means nothing scheduled after roughly
   04:30 the night before.
2. Hotel as daily geographic anchor, for morning departure and evening return.
3. Flex buffers, 30 to 45 minutes ahead of tours, for transit.
4. Multi-city transitions. A train changes `geo_region` mid-trip, which argues
   for region being a property of the node rather than the trip.

## Signal: booking_added

Registry entry in `models/signal_types.py` plus the migration that seeds
`signal_type`, in the same commit, or the drift guard fails (R5). `value_json`
carries `{booking_type, import_source}` -- never the code, never a place name
that could identify an individual reservation.

## Tests

- A booking node is never moved by `reschedule_and_validate`
- A flight truncates the preceding evening
- A trip serialised before this spec still deserializes -- the important one
- `confirmation_code` appears in no log line, asserted by grep over captured logs
- A hotel affects first and last node times for each day it covers
- Each import path yields a booking whose `import_source` is set correctly
- A malformed import degrades to a partly filled manual form rather than raising
- The on-device path extracts a booking with no network call, asserted by failing
  the test if the import opens a socket
- The server-side fallback refuses to run without recorded consent

## Acceptance

- [x] node_kind, booking_type, confirmation_code, booking_notes, import_source on
      the node, all defaulted
- [x] Old trip JSON loads, with a test that proves it
- [x] Booking nodes locked and unmovable
- [ ] Flight constrains the preceding evening; hotel acts as a daily anchor
- [ ] `confirmation_code` absent from all logs
- [x] `booking_added` in the registry and migration 0021; drift guard green
- [x] Text paste plus manual entry shipped end to end, degrading to manual entry
- [x] Text extraction runs on the device, proven by the no-network test
- [ ] Server-side fallback gated on per-import consent, deleting the document once
      the fields are out
- [x] UI: entry form plus visually distinct locked booking nodes
- [x] Create-slice suite green from `origin/main`
- [x] Existing booking can be reopened and edited without changing `node_id`
- [x] Existing booking can be deleted after explicit confirmation
- [x] Edit/delete never consume reroute quota or route reservation data to an LLM

## Remainder: edit and delete existing bookings

This is a separate structural-mutation slice after SPEC-31. Date grouping and
booking mutation share a screen but not a failure model; mixing them makes
locked-node and privacy review harder.

### API

Keep `POST /trip/event`. Add:

```text
edit_booking
delete_booking
```

Both require `target_node_id`. The target must exist and have
`node_kind == "booking"`; otherwise return a typed 404/409 rather than mutating
an activity.

Do not reuse `add_booking`: it creates a new `node_id`. Do not reuse
`cancel_activity`: locked cancel correctly refuses and skip-in-place is not
deletion.

Edit/delete are structural events but are not reroutes:

- no daily reroute quota,
- no heavy-model route,
- canned deterministic response,
- no trip-state dump to an LLM.

### Edit

Patch only the booking fields supplied by the client. Preserve:

- `node_id`,
- `node_kind == "booking"`,
- `is_locked == true`,
- fields omitted from the patch.

If start or duration changes, reinsert the same node into chronological order
and run `reschedule_and_validate`. A hotel remains a background anchor. Return
hard-conflict warnings through the existing response shape.

The edit form reuses AddBookingSheet in an explicit edit mode, prefilled from
the target node. It must allow an already-started booking date to remain
selected; the create form may continue to prevent accidental past dates.

### Delete

Delete removes the booking node, then reschedules the remaining itinerary. It
does not mark the node skipped and does not call locked cancel.

The client names the booking in an explicit destructive confirmation. Dismiss
and Keep make zero event calls. Confirm sends exactly one `delete_booking` for
the displayed `node_id`.

### Privacy and signals

No lifecycle signal is required for this bounded slice. If later added, it must
carry only booking type and import source, with Python registry and a migration
in one commit. It must never include confirmation code, notes, place name, or
raw source text.

No log, model prompt, or error detail may contain `confirmation_code`.

### Tests

- edit preserves `node_id` and lock,
- omitted fields survive a partial edit,
- time edit reorders the same node,
- hotel edit remains a background anchor,
- delete removes rather than skips,
- non-booking target refuses,
- missing target refuses,
- edit/delete do not consume reroute quota,
- router classifies both deterministic/light and never invokes the LLM,
- confirmation code is absent from logs and model input,
- edit form prefills all current fields,
- delete Keep/dismiss makes zero calls; confirm sends the displayed node ID,
- SPEC-30 locked outcome behavior remains unchanged.

### Explicitly out

- `trip_stay`,
- check-in/check-out columns,
- multi-night UI redesign,
- `day_index`,
- date grouping,
- Laos creation,
- PDF/screenshot/email-provider ingestion.
