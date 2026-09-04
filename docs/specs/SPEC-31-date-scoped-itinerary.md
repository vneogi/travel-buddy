# SPEC-31: Date-Scoped Itinerary and Stay Rescue

> Status: GROUPING IMPLEMENTED (PR #36). Windows Sep 4 verified date headers
> (6A). Stay-rescue selection (6C) was not run on device.
>
> Depends on SPEC-10 booking anchors and the existing itinerary wire shape.
> Does not depend on SPEC-16 phase-two reads, `day_index`, or `trip_stay`.

## Goal

Stop presenting a multi-day trip as one undifferentiated "Your Day" list, and
make Hotel Rescue choose the stay that is useful now rather than the first
hotel-like node in the trip.

The existing node already carries the only facts this slice needs:
`scheduled_start` and `duration_minutes`. This is a view change over those
facts, not a new trip model.

## Product decisions

### 1. Group without filtering

The itinerary shows every node, grouped under a calendar-date header. Opening
the itinerary does not hide past or future days and does not silently select
one day.

Grouping preserves the order received from the server. Nodes inside a day keep
their current order, stable IDs, ActivityCard keys, heart state, and SPEC-30
outcome state.

The app bar changes from "Your Day" to "Your Trip". A date header is text, not
color alone, and includes weekday, day, month, and year when needed to avoid an
ambiguous trip crossing New Year.

### 2. Use the clock already displayed

This slice groups by the year, month, and day fields on the parsed
`TripNode.scheduledStart`. It does not call `toLocal()` or `toUtc()` first.

That is deliberate. Existing booking entry, server normalization, card display,
and destination-timezone lookup are not yet one coherent timezone contract.
Converting only the section header would let a card display 00:30 while placing
it under the previous date. A later timezone slice must change entry, storage,
display, grouping, and tests together.

### 3. A hotel stay occupies an instant window

For rescue selection, a hotel-like node occupies:

```text
[scheduledStart, scheduledStart + durationMinutes)
```

Selection order:

1. Active stay containing `now`. If data overlaps, choose the one with the
   latest start.
2. Earliest future stay.
3. Most recently elapsed stay, by latest end.
4. No stay.

This keeps rescue useful before check-in, during a multi-day booking, and just
after checkout. The hotel node still appears once in the itinerary, under its
check-in date. Do not clone it under each occupied date.

Hotel detection keeps the current two paths:

- `booking_type == "hotel"`, or
- case-insensitive name fallback for hotel, resort, hostel, villa, or
  guesthouse.

### 4. Keep data and scheduling unchanged

This slice does not:

- derive or expose `trip_node.day_index`,
- alter API JSON or `TripNode`,
- change SQLite,
- change Python or SQL,
- change scheduler behavior,
- create daily hotel anchors,
- add check-in/check-out columns,
- create `trip_stay`,
- edit or delete bookings,
- change booking parsing or timezone conversion.

## Implementation shape

Add a pure helper next to the itinerary window helpers. It owns:

```text
ItineraryDayGroup
groupNodesByCalendarDate(nodes)
isHotelLikeNode(node)
selectRescueStay(nodes, now)
```

`ItineraryDayGroup` contains a date value and an ordered node list. Its date is
constructed from `scheduledStart.year`, `.month`, and `.day`.

The grouping helper performs a sequential fold over the existing ordered list.
It must not sort or mutate the input. The current backend returns chronological
nodes; changing that ordering contract belongs elsewhere.

`selectRescueStay` must not depend on list order. It compares start/end instants
and applies the precedence above.

## UI

`ItineraryScreen` renders a date header before each group, then the existing
ActivityCard rows. Keep the current AnimatedSwitcher and key expression on the
cards.

The screen remains one scrollable timeline. No tabs, horizontal pager, sticky
header package, new dependency, or automatic jump is needed.

Hotel Rescue calls `selectRescueStay(nodes, DateTime.now())`. Tests inject
`now`; production obtains it only at the call boundary.

## Tests

Pure helper tests:

- one day produces one group,
- multiple dates produce ordered groups,
- nodes within a date preserve input order,
- the input list is not mutated,
- year boundaries remain distinct,
- offsets are not converted before extracting date fields,
- active hotel wins over past and future,
- latest-starting active hotel wins if stays overlap,
- earliest future hotel wins when none is active,
- most recently ended hotel wins when no active/future stay exists,
- a long hotel booking remains active on a later calendar day,
- keyword fallback still works,
- no hotel returns null.

Widget tests:

- app bar says "Your Trip",
- two dates render two unambiguous headers,
- all original ActivityCards remain present,
- existing heart and SPEC-30 outcome wiring still reaches the correct node,
- no RenderFlex overflow at an 800x600 surface.

Hotel Rescue tests:

- two stays on different dates select the active one,
- before both stays selects the earliest future one,
- after both stays selects the most recently elapsed one,
- empty state remains unchanged when there is no hotel.

## Acceptance

- [x] Multi-day itinerary renders date headers without hiding nodes
- [x] Existing node order and card identity are preserved
- [x] Header date uses the same parsed clock fields as the card
- [ ] Hotel Rescue selects active, then future, then elapsed stay
- [ ] Long hotel duration works across calendar days without cloned nodes
- [x] No API, schema, scheduler, or timezone conversion change
- [x] Flutter analyze and full Flutter test green from `origin/main`
