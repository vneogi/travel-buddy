# SPEC-26: Home Surface and Trip Creation

> Status: PARTIAL. The authenticated trip-list/home thin slice is implemented;
> the richer active-trip aggregate and full SPEC-22 migration remain.
>
> Depends on SPEC-16 for nodes as rows, which is what makes a cheap list
> projection possible, and on SPEC-22 for how the screen is allowed to render.
> SPEC-13 gates the destination half of trip creation.

## Goal

Give the app a first screen that can be built, and a trip creation path that does
not interrogate the user before it does anything for them.

## What is missing, precisely

The service layer has `get_active_trips(user_id)`, now exposed as the
authenticated `GET /api/v1/trips` lightweight projection. The Flutter home
screen caches and renders that list per identity. The richer one-request
aggregate described below is still missing.

So the gap on the home screen is one route, not a subsystem -- but until that
route exists, a returning user opening the app has no way to be shown their own
trips, and no amount of Flutter work changes that. This is worth stating plainly
because it is easy to mistake the home screen for a pure design problem.

The second gap is real work. A first screen wants one answer to "what is going on
right now": the active trip, what is next and how long until it, anything waiting
for a decision, and how old the cached copy is. Assembling that from four calls is
the wrong shape for the network these users are on. The screen people open most
should cost one request.

## Design decisions

1. **A list endpoint returning a projection, never `state_json`.** Trip name,
   destination region, dates, status, and the counts a card needs. Returning the
   full blob to draw a list is the sort of thing that is invisible in development
   and miserable on hotel wifi. SPEC-16 makes this cheap by putting nodes in rows.

2. **One home endpoint whose response is a self-contained snapshot.** Everything
   the first screen renders comes from that single payload, with no follow-up
   call needed to draw anything. That constraint is what makes decision 3
   possible; if the screen needs a second call to render, it cannot render
   offline.

3. **The home payload is cached and the screen renders from cache without
   apology.** Under SPEC-22 decision 7 offline is a designed state. Home is where
   that is most visible, and where a spinner or an error banner would do the most
   damage to the one thing we claim competitors cannot copy.

4. **The empty state is designed, not an accident.** A person with no trips is
   the most common first-run case and the one most likely to be handled as a blank
   list. It is the entry point to trip creation and should be treated as a screen
   with a job.

5. **Creating a trip asks for a destination and dates. Nothing else is
   required.** Party composition (SPEC-03), preferences (SPEC-11) and booking
   import (SPEC-10) are all offered, all deferrable, and all revealed as they
   become useful. A preference quiz standing between a person and their first
   itinerary converts the curious into the departed, and SPEC-11's own argument is
   that revealed preference beats stated preference anyway -- so gating on stated
   preference is both hostile and less accurate.

6. **Trip creation is gated on region validity, and that is SPEC-13's job.**
   `geo_region` is an unconstrained string today and adding a city needs a code
   change, so "plan a trip anywhere" is not true yet. The honest interim is a
   short list of supported regions and a clear refusal outside it, rather than
   accepting a destination we cannot serve and failing later in the itinerary.

7. **Home is where the interruption budget is spent and where the ask box
   lives.** Both are specified elsewhere -- the budget in SPEC-22, the box in
   SPEC-25 -- and this spec's only claim on them is the placement. Naming the
   owner here prevents the home screen from growing its own copy of either.

8. **The trip list works offline from the vault.** A traveller who opens the app
   on a plane sees their trips. This follows from decision 2 but is worth an
   explicit acceptance line, because it is the case most likely to be skipped as
   an edge case when it is in fact the situation the product exists for.

## Tests

- The list endpoint returns a user's trips and no other user's, asserted with two
  identities rather than one
- The list response contains no `state_json`, asserted on the payload shape so it
  fails when somebody widens the projection
- The home endpoint answers in a single request with everything the screen needs,
  proven by a render test that fails if a second call is attempted
- Home renders from cache with the network down, carrying a cache age
- A user with no trips gets the designed empty state, not an empty list widget
- Trip creation succeeds with only a destination and dates
- Trip creation into an unsupported region refuses with a reason rather than
  creating an unservable trip
- Party, preferences and booking import can each be supplied after creation

## Acceptance

- [ ] Trip list endpoint exposing the existing service method, projection only
- [ ] Home aggregate endpoint returning a self-contained snapshot
- [ ] Home and trip list both render offline from cache, with cache age shown
- [ ] Designed empty state routing into trip creation
- [ ] Trip creation requires destination and dates only
- [ ] Region validity enforced at creation with an explicit refusal
- [ ] Ask box and interruption budget consumed from their owning specs, not
      reimplemented
- [ ] Suite green (R8); `flutter analyze` clean; verified from `origin/main` (R10)
