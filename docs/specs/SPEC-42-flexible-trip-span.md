# SPEC-42: Flexible Trip Span and Sparse Day Editing

> Status: SPECIFIED FOR A LATER PHASE. Not implemented.
>
> Depends on SPEC-31 date-scoped rendering, SPEC-40 guided creation, and
> SPEC-41 feasibility-first scheduling. This spec changes neither the current
> SPEC-40 PR nor its five-day catalog-capacity contract.

## Goal

Let the traveller choose the dates of the trip they are actually taking without
forcing every calendar day to contain a generated itinerary.

Trip duration and generated content density are separate:

- the selected inclusive start/end range defines the trip container;
- initial generation populates at most five starter days;
- every other date remains a visible, valid empty day;
- the traveller can add an activity directly to an empty day or move an
  existing flexible activity between days.

The catalog being able to fill five days is not a reason to reject a ten-day
trip.

## Product decisions

### No catalog-derived date cap

The create UI does not disable or reject a date range because a region has
fewer venues than the number of selected calendar days.

A separate, documented technical sanity limit may protect against accidental
multi-year selections or abusive payloads. It is not calculated from venue
capacity and is not presented as a recommendation for trip length.

### At most five generated starter days

Initial generation selects:

```text
populated_day_count = min(5, trip_calendar_days, feasible_content_days)
```

For a range longer than five days, populated starter days are distributed
deterministically across the span rather than silently shortening the trip.
The first and last day are included when at least two days can be populated.
Intermediate days are spread as evenly as practical.

The review step states:

- total trip dates;
- how many days will receive starter suggestions;
- that remaining days will stay empty and editable.

Generation may produce fewer than five populated days when SPEC-41 cannot find
enough feasible, unique venues. It never duplicates a venue, schedules a
known-closed venue, or fabricates filler to make the day look complete.

### Empty days are first-class

Every calendar date in the trip span renders under SPEC-31, including dates
with no nodes. An empty day is not an error or missing-data state.

Empty-day treatment provides:

- `Add activity`;
- optional short copy that the day is intentionally open;
- no warning, retry, or failure styling.

The empty-day action is available online. A later offline slice may capture an
intent, but it cannot perform local structural reflow against stale data.

### Direct add

`Add activity` starts from the selected local date. The traveller may choose a
time or a broad slot such as morning, afternoon, or evening.

Candidate search and apply both use SPEC-41:

- destination-local structured hours;
- neighbouring activity and locked-booking reachability;
- the candidate's dwell time;
- no repeat where the active trip contract forbids one;
- deterministic ranking inside the feasible set.

If no candidate fits, return a typed honest refusal and keep the day empty.

### Move between days

A flexible activity can move to another date/time inside the trip span. The
operation preserves `node_id`, loved/outcome state, and venue identity.

Locked booking anchors cannot move through this action. Moving a flexible node
reruns SPEC-41 feasibility for the target slot and affected neighbours before
persistence. A failed move leaves the original itinerary unchanged.

Moving is not swapping:

- move changes the date/time of the same node;
- swap changes the venue in a slot;
- add introduces a new node.

Each receives its own typed event and tests.

## API evolution

SPEC-40 currently advertises `max_days_by_region` and rejects a range above that
catalog-derived maximum. This later phase replaces that meaning without
breaking old cached clients.

The options response should advertise separate concepts, for example:

```json
{
  "create_trip_options": {
    "max_auto_populated_days": 5,
    "trip_span_sanity_days": 90
  }
}
```

Names and the final sanity value are implementation decisions, but one field
must not represent both trip span and catalog fill capacity.

Old clients may continue to apply the old maximum. New clients use the
decoupled fields. The server accepts the wider span only after sparse-day
serialization and rendering are supported end to end.

Creation context continues to preserve the exact posted local start and end
dates. Empty days need not be stored as fake nodes; they are derived from that
inclusive span.

## Determinism

Given the same span, catalog, bookings, interests, and feasibility inputs:

- the same local dates are selected for starter content;
- the same ordered venue IDs are chosen;
- the same dates remain empty.

No model call chooses populated days, venues, or times.

## Signals and personalization

Direct add and move are high-quality preference signals because they express
what the generated plan lacked. Signal payloads use stable trip/node/venue
references and local day position, never free-text notes or booking details.

Signals may later re-rank the SPEC-41 feasible set. They cannot weaken hours,
reachability, lock, region, or trip-boundary constraints.

## Tests

- a trip longer than catalog capacity is accepted within the sanity limit;
- creation context preserves the full inclusive range;
- a ten-day range produces at most five populated dates and ten rendered date
  sections;
- first and last dates are populated when at least two feasible starter days
  exist;
- distribution is deterministic for the same inputs;
- unpopulated dates contain no synthetic nodes and render `Add activity`;
- insufficient content leaves additional days empty rather than returning
  `over_capacity`;
- direct add searches and applies against the selected local date and slot;
- no-fit direct add returns a typed refusal and leaves storage unchanged;
- moving preserves `node_id`, venue identity, loved state, and outcome;
- moving a locked booking is refused before persistence;
- a failed feasibility check leaves the source node unchanged;
- old cached options and trips still deserialize;
- create, add, and move do not require an LLM.

## Acceptance

- [ ] Trip span and auto-populated-day capacity are separate API concepts
- [ ] A valid long trip is not rejected because the catalog fills only five days
- [ ] Initial generation populates no more than five deterministic dates
- [ ] Every date in the inclusive span renders, including empty days
- [ ] Empty days provide a direct Add activity action
- [ ] Flexible activities can move across dates without changing `node_id`
- [ ] Locked bookings remain immovable
- [ ] Add and Move use SPEC-41 feasibility before persistence
- [ ] Sparse trips survive API fetch, cache, offline rendering, and restart
- [ ] Existing SPEC-40 clients and one-day create remain compatible
- [ ] Full Python and Flutter suites are green from `origin/main`

## Explicit non-goals

- filling every day with four activities;
- unlimited unvalidated payload size;
- moving locked bookings;
- offline structural replanning;
- free-text itinerary generation;
- similar-trip inspiration;
- collaborative planning;
- transport or hotel import redesign.
