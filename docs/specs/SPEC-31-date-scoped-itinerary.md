# SPEC-31: Date-Scoped Itinerary

> Status: IMPLEMENTED (PR #36). Windows Sep 4 verified date headers (6A).
> Stay-rescue selection was implemented but is now RETIRED with the dedicated
> Hotel Rescue shortcut. Test 6C is canceled by product decision, not pending.
>
> Depends on SPEC-10 booking anchors and the existing itinerary wire shape.
> Does not depend on SPEC-16 phase-two reads, `day_index`, or `trip_stay`.

## Goal

Stop presenting a multi-day trip as one undifferentiated "Your Day" list.

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

### 3. Sep 5 decision: remove the dedicated rescue path

The owner judged the AppBar Hotel Rescue shortcut useless during the Sep 4
Windows review. The app already exposes the same offline driver card from the
hotel booking row. Keeping two entry points creates more navigation and
selection logic without adding a distinct outcome.

Remove the AppBar shield, HotelRescueSheet, `isHotelLikeNode`,
`selectRescueStay`, and their dedicated tests. Keep offline itinerary caching,
place pre-caching, multi-night booking duration, and the driver-card action on
every hotel booking.

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

Keep a pure helper next to the itinerary window helpers. It owns:

```text
ItineraryDayGroup
groupNodesByCalendarDate(nodes)
```

`ItineraryDayGroup` contains a date value and an ordered node list. Its date is
constructed from `scheduledStart.year`, `.month`, and `.day`.

The grouping helper performs a sequential fold over the existing ordered list.
It must not sort or mutate the input. The current backend returns chronological
nodes; changing that ordering contract belongs elsewhere.

## UI

`ItineraryScreen` renders a date header before each group, then the existing
ActivityCard rows. Keep the current AnimatedSwitcher and key expression on the
cards.

The screen remains one scrollable timeline. No tabs, horizontal pager, sticky
header package, new dependency, or automatic jump is needed.

## Tests

Pure helper tests:

- one day produces one group,
- multiple dates produce ordered groups,
- nodes within a date preserve input order,
- the input list is not mutated,
- year boundaries remain distinct,
- offsets are not converted before extracting date fields,
Widget tests:

- app bar says "Your Trip",
- two dates render two unambiguous headers,
- all original ActivityCards remain present,
- existing heart and SPEC-30 outcome wiring still reaches the correct node,
- no RenderFlex overflow at an 800x600 surface.

- no Hotel Rescue shield appears in the itinerary AppBar,
- a hotel booking still renders its driver-card action.

## Acceptance

- [x] Multi-day itinerary renders date headers without hiding nodes
- [x] Existing node order and card identity are preserved
- [x] Header date uses the same parsed clock fields as the card
- [ ] Dedicated Hotel Rescue code path removed; 6C canceled
- [ ] Multi-night booking duration remains a separate product slice
- [x] No API, schema, scheduler, or timezone conversion change
- [x] Flutter analyze and full Flutter test green from `origin/main`
