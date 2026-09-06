# SPEC-36: Laos Corridor Trip

> Status: IMPLEMENTATION IN REVIEW, NOT MERGED.
>
> Candidate branch `origin/feat/spec36-laos-corridor` is at `f117967`.
> Backend strengthening and later-city swap-coordinate changes are pushed.
> Completion still requires review of the actual diff, Flutter compile/tests,
> date-range form and swap-isolation proof, green CI, and merge to `main`.
>
> Extends SPEC-31 date grouping and SPEC-32 catalog trip creation. Uses
> SPEC-13 region metadata, SPEC-16 stable nodes and normalized rows, and the
> SPEC-35 region-local schedule basis.
>
> No migration is required for this slice. Corridor metadata is additive
> state JSON, and normalized `trip_node` already carries `geo_region` and
> `day_index`.

## Goal

Create one trip for the northbound Laos journey:

1. Vientiane;
2. Vang Vieng;
3. Luang Prabang.

Each city has its own inclusive date range. The backend builds a deterministic
catalog itinerary for every day, and the Flutter itinerary renders collapsible
city sections containing the existing date headers and activity cards.

This is not three unrelated trip cards and not one city's itinerary with its
labels changed.

## First-slice product decisions

### 1. One explicit corridor, one order

The first slice supports only:

```text
laos_northbound_v1:
  vientiane_laos -> vang_vieng_laos -> luang_prabang_laos
```

Do not build arbitrary city ordering, reverse direction, another country, or a
generic route editor. A later corridor may be added to the same registry after
there is a real user need.

### 2. Independent but ordered date ranges

The create form collects an inclusive start and end date for each of the three
cities.

Rules:

- each range is at least one day and at most three days;
- the total corridor is at most seven days;
- each next city starts after the previous city ends;
- gaps are allowed, because the traveller may use them for transport;
- overlapping or out-of-order ranges return 422 `invalid_corridor`;
- all dates are interpreted in `Asia/Vientiane`;
- every generated day starts at 09:00 local and stores a UTC instant;
- the trip carries `schedule_basis = "region_local_v1"`.

The client validates these rules for immediate feedback. The server repeats
every validation and remains authoritative.

### 3. Four unique catalog activities per day

Corridor creation uses the committed or hosted venue catalog through
`list_venues_for_region`. It does not call hybrid search or an LLM.

For each city:

- choose exactly four eligible venues per day;
- preserve the existing category-bucket preference;
- never repeat a venue within that city segment;
- keep selection deterministic for the same request and catalog;
- exclude hospital, pharmacy, and transport hub rows;
- require coordinates and a stable venue ID;
- fail the whole request before saving if any segment lacks enough eligible
  venues.

Four stops are deliberate. The smallest current corridor catalog has enough
eligible rows for three unique four-stop days. Five per day would advertise a
range the current catalog cannot reliably fulfill.

Failure is atomic: no partial trip, party, normalized node, or edge rows may
remain.

### 4. Explicit segment metadata

Add these models:

```text
TripSegmentIn
  geo_region: string
  starts_on: date
  ends_on: date

TripSegment
  geo_region: string
  starts_on: date
  ends_on: date
```

Add optional fields:

```text
CreateTripRequest.segments: list[TripSegmentIn] | null
TripState.corridor_id: string | null
TripState.segments: list[TripSegment]
TripSummary.corridor_id: string | null
FeaturedTrip.corridor_id: string | null
```

`POST /api/v1/trip/create` has two compatible modes:

- existing single-city mode: `start_date` plus `geo_region`;
- corridor mode: `segments`, with no top-level `start_date` or `geo_region`.

Exactly one mode is accepted. Existing single-city request and response
behavior must remain unchanged.

For corridor trips:

- `corridor_id` is `laos_northbound_v1`;
- `segments` are persisted in state JSON and returned by GET `/trip/{id}`;
- `TripState.geo_region` remains the first segment's region as the legacy
  default;
- every generated node carries its actual city in `node.geo_region`;
- `current_context` starts at the first segment's region defaults.

The trip-level default is not permission to relabel later-city nodes or search
the first city for a targeted action.

### 5. Advertise the capability

GET `/api/v1/trips` adds:

```json
{
  "supported_corridors": [
    {
      "corridor_id": "laos_northbound_v1",
      "display_name": "Vientiane to Luang Prabang",
      "geo_regions": [
        "vientiane_laos",
        "vang_vieng_laos",
        "luang_prabang_laos"
      ],
      "max_days": 7,
      "max_days_per_segment": 3
    }
  ]
}
```

Advertise the corridor only when every city can supply at least four eligible
venues for one day. Full request capacity is still validated at create time.
The existing `supported_regions` field remains unchanged.

Flutter parses and caches `supported_corridors` with the rest of the Home
snapshot. Old cached snapshots without the field parse as an empty list.

### 6. City and day grouping

The itinerary stays one vertical timeline.

For a corridor trip, render:

```text
Vientiane        4-5 October
  Sunday, 4 October 2026
    existing ActivityCard
  Monday, 5 October 2026
    existing ActivityCard

Vang Vieng       6-7 October
  ...
```

City sections:

- follow `TripState.segments`, never alphabetical order;
- are expanded for current and future sections;
- start collapsed when every node in that section ends before `DateTime.now()`;
- can always be expanded again;
- hide no data and delete no history;
- use text plus a chevron, not color alone;
- preserve existing ActivityCard keys, hearts, outcomes, booking actions, swap,
  cancel, and driver-card behavior.

The existing `groupNodesByCalendarDate` remains the one-day grouping primitive.
Add a corridor grouping helper that preserves input order and delegates each
city's node list to it. Do not sort or mutate the server list.

Unknown or missing node `geo_region` values render in an `Other stops` section
rather than disappearing.

### 7. Normalized rows must tell the truth

`decompose_trip` currently writes `day_index = 0` for every node. Corridor
creation must derive a zero-based day index from the ordered distinct local
calendar dates in the trip.

For this Laos slice all regions share `Asia/Vientiane`. Use the region registry
timezone and the stored UTC instant. Keep global `seq` order stable.

Single-day trips still produce day index zero. Round-trip composition must
preserve node order and all per-node regions.

### 8. Intercity transport is not invented

Segment boundaries show that the city changed. They do not claim:

- a train, bus, car, or transfer booking;
- a departure terminal;
- travel duration or price;
- hotel check-in or checkout;
- that the traveller can complete a route in a gap.

Do not create synthetic transport nodes. Existing real bookings can still be
added through SPEC-10. Planning or purchasing intercity transport is a later
slice.

### 9. Existing node-scoped behavior remains city-scoped

Swap and other targeted venue operations use the target node's `geo_region`.
They must never use the last itinerary node or the trip's first-city default as
a proxy.

The Flutter swap sheet must also derive search latitude and longitude from the
target node. The current itinerary path builds swap coordinates from the first
trip node, which would search Vientiane when the traveller opens Swap on a
Luang Prabang card. Update the production coordinate resolver; do not fix only
the server-side region filter.

Trip-global "near me" remains outside this slice. If no current city or target
node is known, refuse or ask; do not silently search Vientiane for a traveller
who may be in Luang Prabang.

## API errors

Corridor validation returns HTTP 422 with:

```json
{
  "detail": {
    "error": "invalid_corridor",
    "message": "Safe user-facing explanation.",
    "field": "segments",
    "supported_corridors": ["laos_northbound_v1"]
  }
}
```

Insufficient catalog capacity returns 422 `unsupported_corridor`. Neither
error includes stack traces, SQL, provider responses, or a partial trip ID.

## Out of scope

- reverse or arbitrary corridor order;
- editing segments after creation;
- dragging cities or days;
- synthetic transfer nodes or route estimates;
- hotel/stay generation;
- map-first shell or map tiles;
- OS push;
- background location;
- meal preview or review-derived popularity;
- schema migration or normalized-read cutover;
- LLM itinerary generation;
- reroute quota consumption during create.

## Required proof cases

Backend:

1. A valid three-segment request creates one trip with ordered segment metadata.
2. Every generated node belongs to its segment catalog and carries that
   segment's `geo_region`.
3. Every requested day has four nodes at 09:00 local plus deterministic
   intra-day spacing.
4. No venue repeats within a segment.
5. Repeating the same request keeps the venue ID sequence stable.
6. Overlap, wrong order, duplicate/missing city, range over three days, and
   total over seven days each return 422 `invalid_corridor`.
7. Insufficient capacity returns 422 and leaves no trip or party behind.
8. Single-city create remains byte-shape compatible.
9. Create calls neither the LLM nor hybrid search and does not consume quota.
10. Normalized rows carry increasing day indexes and preserve global sequence.
11. A targeted swap in Luang Prabang cannot return a Vientiane venue.
12. Canceling or swapping an earlier-city node does not move the next city's
    first 09:00 node across its requested date boundary.

Flutter:

13. Home parses and caches missing or present `supported_corridors`.
14. Corridor create sends only the three segment objects.
15. Invalid date ranges cannot submit and show a user-facing reason.
16. One fetched trip renders city sections in corridor order and date headers
    inside each city.
17. Past city sections start collapsed and expand without losing cards.
18. Current and future city sections start expanded.
19. Hearts, outcomes, booking actions, and target-node swaps still reach the
    original node IDs.
20. Opening Swap on a Luang Prabang card sends that node's latitude and
    longitude to venue search, not the first Vientiane node's coordinates.
21. A single-city trip renders exactly as before.
22. No overflow at 800x600 and no raw region code is shown to the user.

## Sabotage proofs

Run each sabotage separately and name the expected failing test:

1. Change corridor creation to reuse the first city's catalog for all segments.
   The per-segment catalog test must fail.
2. Remove the used-venue exclusion. The no-repeat test must fail.
3. Persist one segment before validating the next. The atomic-failure test must
   fail.
4. Set every normalized `day_index` to zero. The normalized day-order test must
   fail.
5. Group Flutter nodes by date only. The city-order widget test must fail.
6. Remove the collapsed gate from the production city-section widget. The past
   section widget test must fail.
7. Make the repository send both `start_date` and `segments`. The request-shape
   test must fail.
8. Resolve a swap from `trip.geo_region` instead of the target node. The
   cross-city swap isolation test must fail.
9. Change the Flutter swap coordinate resolver back to `nodes.first`. The
   later-city swap-search coordinate test must fail.

For every sabotage, verify that the named test itself fails for the intended
assertion. A red suite from another test is not proof.

## Acceptance

- [ ] One northbound Laos corridor creates as one trip
- [ ] Three independent ordered date ranges are validated server-side
- [ ] Four unique deterministic catalog stops are created per city-day
- [ ] Segment metadata survives save and fetch
- [ ] Normalized rows carry truthful day indexes and per-node regions
- [ ] Flutter creates the corridor and renders collapsible city/day sections
- [ ] Past sections collapse without hiding history permanently
- [ ] A later-city swap searches around its target node, not the first city
- [ ] Single-city creation and itinerary behavior remain compatible
- [ ] No transport, stay, traffic, meal, or popularity claim is invented
- [ ] Backend and Flutter proof cases pass and all sabotage proofs fail correctly
