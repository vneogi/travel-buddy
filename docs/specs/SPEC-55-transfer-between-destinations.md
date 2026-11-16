# SPEC-55: Transfer Between Destinations

> Status: PENCILED (owning spec written 2026-11-16). Not implemented.
> Amends SPEC-10 (booking anchors) and SPEC-36 (corridor trip).

## Goal

Show known travel between destinations without inventing transport.

## Scope

- Inside a corridor trip: a transfer card between city sections.
- Owner decision 2026-11-16: also between two of the traveller's own
  separate trips, for example Stone Town (ends 28 Dec) to Nungwi (starts
  29 Dec).
- Booking-confirmed only. A transfer card shows mode, destination-local
  departure and arrival, origin, destination and reference when the
  traveller has entered them.
- With no booking, show only a restrained "travel between your
  destinations" gap with an add-booking action. Never an assumed vehicle,
  station or time.

## Design questions to answer before a brief

1. Which trip owns a cross-trip transfer record: the departing trip's last
   day, the arriving trip's first day, or one record shown on both.
2. How two trips are linked without merging their regions. They stay
   separate on purpose, because day plans do not cluster across them.
3. Destination-local times when the two trips are in different timezones
   (not the case for Tanzania; the model must still handle it).
4. Offline: the card must render from either trip's cache.
5. Whether existing booking types can hold station-to-station details, or
   a narrow schema amendment with a migration and rollback plan is needed.
   Do not subclass trip nodes speculatively.

## Owner decisions (2026-11-16)

1. Owner of a cross-trip record: the departing trip, on its last day.
   The arriving trip shows a read-only link to it.
2. Details captured when adding a booking: mode, departure and arrival
   times, origin, destination and reference.
3. Station-to-station details use an existing booking type with free-text
   fields. No database change or migration in this spec. A dedicated
   transfer type is a later decision that needs your Supabase go-ahead.
4. Still parked until after the Tanzania trip.

## Acceptance

- Confirmed transfer details render offline with correct local times.
- Missing details are absent, not synthesised.
- Add, edit and delete follow existing confirmation, ownership and anchor
  rules. Corridor and single-city timelines stay compatible.

## Trip relevance

Medium to high (the 29 Dec move).
