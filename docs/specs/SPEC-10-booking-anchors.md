# SPEC-10: Manual Booking Anchors

## Goal

Let the user enter bookings (flight, hotel, train, tour) as immovable anchors.
Unlocks: "early flight tomorrow, take a cab back", "best food near your hotel".

## Design: manual entry is first-class, not a stopgap

Target markets have unparseable bookings as the majority case (paper tickets,
Lao-language SMS, photos). Manual entry: booking type, date+time, place, optional
code, optional notes. Four required fields.

## Data model: reuse the node

A booking is a locked TripNode with extra metadata:

| Field | Type | Default |
|---|---|---|
| node_kind | enum | activity |
| booking_type | enum/null | null |
| confirmation_code | string/null | null |
| booking_notes | string/null | null |

All fields MUST have defaults (UserTier deserialization bug protection).

## Privacy: confirmation_code

- Never log confirmation_code
- Consider client-side only (scheduler needs time+place, not the code)
- Do not collect passenger names (keeps app PII-free)

## Scheduler behaviours

1. Hard time constraint (flight at 07:00 → nothing after ~04:30 night before)
2. Hotel as daily geographic anchor (morning departure / evening return)
3. Flex buffers (30-45 min before tours for transit)
4. Multi-city transitions (train changes geo_region mid-trip; consider per-node)

## Signal: booking_added

Add to signal_types.py AND migration. value_json: {booking_type: ...}

## Tests

- Booking node never moved by reschedule_and_validate
- Flight truncates prior evening
- Pre-SPEC-10 trip JSON deserializes (the important one)
- confirmation_code never in error logs
- Hotel affects first/last node times

## Acceptance

- [ ] node_kind/booking_type/confirmation_code/booking_notes on TripNode, all defaulted
- [ ] Old trip JSON loads — test proves it
- [ ] Booking nodes locked and unmovable
- [ ] Flight constrains preceding evening
- [ ] Hotel as daily anchor
- [ ] confirmation_code absent from all logs
- [ ] booking_added in registry + migration; drift guard green
- [ ] UI: entry form + distinct locked booking nodes
- [ ] Suite green (R8); verified from origin/main (R10)
