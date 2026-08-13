# SPEC-10: Manual Booking Anchors

> Status: SPECIFIED. Not implemented.
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

## Acceptance

- [ ] node_kind, booking_type, confirmation_code, booking_notes, import_source on
      the node, all defaulted
- [ ] Old trip JSON loads, with a test that proves it
- [ ] Booking nodes locked and unmovable
- [ ] Flight constrains the preceding evening; hotel acts as a daily anchor
- [ ] `confirmation_code` absent from all logs
- [ ] `booking_added` in the registry and the seeding migration; drift guard green
- [ ] At least one import path shipped end to end, degrading to manual entry
- [ ] UI: entry form plus visually distinct locked booking nodes
- [ ] Suite green (R8); verified from `origin/main` (R10)
