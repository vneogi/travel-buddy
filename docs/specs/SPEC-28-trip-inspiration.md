# SPEC-28: Location-Based Trip Inspiration

> Status: DECIDED, NOT SCHEDULED.
>
> Depends on SPEC-24 for durable identity and data rights, SPEC-26 for the home
> surface, and SPEC-27 for deletion/export. This is post-October work.

## Goal

Let a traveller browse useful itinerary ideas from the same region without
turning Travel Buddy into a live people finder, dating surface, or solicitation
channel.

## Product boundary

The shared object is a delayed, anonymized trip snapshot. It is never a person's
live location.

Version 1 has:

- opt-in publishing after a trip or day is complete;
- region-level discovery, not precise proximity to a person;
- itinerary stops, public notes, and coarse timing;
- save/copy as inspiration;
- report and block controls from the first release.

Version 1 does not have:

- live traveller locations or "people near me";
- direct messages;
- comments or replies;
- profiles optimized for meeting strangers;
- automatic publishing;
- confirmation that a traveller is currently at a venue.

Comments are deliberately deferred. If introduced later, they attach to the
trip artifact, not the traveller, and require moderation, rate limits, reporting,
and an abuse-response owner before launch.

## Privacy and safety rules

1. Publishing is explicit and off by default.
2. Home, hotel, booking references, confirmation codes, and free-text booking
   notes are removed before a snapshot can be published.
3. A currently active trip cannot publish an exact timestamp or sequence.
   Publication is delayed and times are coarsened.
4. Discovery filters by `geo_region`; precise device coordinates are neither
   uploaded nor exposed for this feature.
5. Deleting the source trip withdraws its published snapshot.
6. A blocked identity cannot view or interact with the blocker's snapshots.
7. Public snapshots have a retention policy and an owner-visible unpublish
   control.

## Data shape (future)

- `trip_inspiration`: snapshot id, owner identity, source trip id, geo region,
  title, redacted node projection, published at, visibility, moderation state.
- `trip_inspiration_save`: identity, snapshot id, saved at.
- `trip_inspiration_report`: reporter, snapshot id, closed reason, status.

No raw `state_json` is public. The publication service constructs and validates
an allowlisted projection.

## Acceptance gates

- A private trip is absent from discovery.
- A published snapshot contains no booking code, hotel-rescue note, exact live
  location, user email, or device UUID.
- Active-trip timestamps are delayed/coarsened.
- Region queries cannot reveal snapshots from another region.
- Unpublish and trip deletion remove discovery access.
- Report and block behavior is covered before any social interaction ships.
