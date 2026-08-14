# Consumer Surface Roadmap

The question this document answers: the app has to become something a stranger
can download and use, so what part of that is Flutter work and what has to be
provisioned on the server?

The short version is that most of it is backend, and the largest piece is one
nobody would guess from looking at the screens.

## The structural fact

Every intelligent path in this backend is reachable only through a trip.

The API surface today is `health`, `user/status`, `trip/create`,
`trip/{trip_id}`, `trip/event`, `venues/search`, `stats`, `signals`, and the
payment routes. Free text does reach the engine, through `trip/event`, which
carries a `message` and runs intent classification -- but it requires a
`trip_id`. There is no trip-less way in, and no way to list a user's trips at
all.

That shapes every item below. A home screen, a search box, and a signed-in
account are not decorations on the existing API; they each need a route that does
not exist.

## What is client-only and what is not

| Surface | Client | Server |
|---|---|---|
| Social sign-in | Provider flow via Supabase Auth | JWT verification already exists |
| Account linking and merge | Trigger and sign-out | **All of it** -- SPEC-24 |
| Home screen layout | Yes | Trip list route and a home aggregate -- SPEC-26 |
| Add trip journey | Yes | Region validity -- SPEC-13 gates it |
| Ask Anything box | Yes | **A new endpoint and intent router** -- SPEC-25 |
| Push notifications | Permission and display | Token store and send path -- SPEC-27 |
| Delete and export | Entry point | **All of it** -- SPEC-27 |
| Forced upgrade | Refusal state | Minimum version declaration -- SPEC-27 |

The two bolded rows are the ones that look like client features and are almost
entirely server work.

## The piece that is easy to miss

Sign-in itself is close to free: Supabase Auth runs the provider dance and
`security.py` already verifies the resulting token. What is not free is what
happens to everything the user did before they signed in.

SPEC-09 is shipping anonymous device identity now. From that point on, real trips
and real behavioural signals accumulate under a UUID that belongs to a device
rather than a person. Sign-in creates a second identity, and unless something
deliberately merges them, everything gathered before that moment is stranded --
silently, from the user's point of view, as an app that lost their trip.

The schema makes this sharper than it sounds. `trip_states` and `event_log` both
carry `user_id UUID REFERENCES user_tiers(user_id)`, so they are held together by
referential integrity. `signal.user_id` is `TEXT` with no foreign key and no type
match -- the table holding the asset this product is built around is the one table
outside the constraint system. No merge and no deletion can rely on a cascade,
and nothing in the database will complain if a future table is missed.

This is why SPEC-24 is worth settling now even though it will not be built for
months. The engineering does not get harder with time; the data does.

## The specs

| Spec | Owns | Depends on |
|---|---|---|
| SPEC-24 | Sign-in, credential aliases, anonymous-to-account merge, multi-device, sign-out | SPEC-09 |
| SPEC-25 | Trip-less query endpoint, closed intent set, cost bounds, offline behaviour | SPEC-17, SPEC-18, SPEC-22 |
| SPEC-26 | Trip list, home aggregate, empty state, minimum trip creation | SPEC-13, SPEC-16, SPEC-22 |
| SPEC-27 | Push transport, deletion and export, minimum supported client | SPEC-22, SPEC-24 |

`docs/UX_BACKLOG.md` remains the list of screens we want to build. This roadmap
is about what has to exist beneath them, and SPEC-22 constrains how any of it is
allowed to render.

## Sequencing

None of this is on the October 2 path. That trip is one known user testing
whether a driver card survives a day without connectivity on a real trip
anchored by real bookings. The October spine is device day, SPEC-09 client,
SPEC-22, SPEC-12, SPEC-10, then a thin SPEC-04 rescue entry to the hotel
card -- not the full Offline Vault. SPEC-02 already delivered the offline
substrate; SPEC-12 already owns the venue card on that cache. See SPEC-04
("What SPEC-04 still adds" and "October scope") and docs/PROJECT_STATUS.md.
Consumer surface follows the field test.

The exception is the SPEC-24 design, which is settled now and built later, for
the reason above.

After the field test the order is driven by dependency rather than by appeal.
SPEC-26 is mostly cheap -- the trip list is one route over a service method that
already exists -- and it unblocks having a first screen at all. SPEC-25 wants
SPEC-17's envelope to be real before it can honour it, so it follows the trust
work rather than leading it. SPEC-27 is last, and should not be later than the
first build that goes to people who are not us.

## Deliberately not specified here

Swappable LLM providers, including local models, still has no owning spec. It
maps to the stated objective about next-generation optionality and it is not a
consumer surface concern, so it takes the next free spec number rather than being
folded into one of these four.
