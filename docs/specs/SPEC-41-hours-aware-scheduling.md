# SPEC-41: Hours-Aware Scheduling and Staged Ranking

> Status: PHASE A COMPLETE. A3a merged as `d1fde14`; A3b was reviewed at
> branch head `7f25042`. Create, corridor, range planning, swap search/apply,
> and scheduler validation use deterministic destination-local hours and
> walking reachability. Advertised capacity is truthful across weekdays and
> valid interest profiles.
>
> Sequenced after SPEC-40. This spec owns itinerary feasibility and ranking.
> SPEC-08 owns the structured hours data, SPEC-10 owns locked booking anchors,
> SPEC-13 owns the future region registry, and SPEC-17 owns traveller-facing
> factual claims. SPEC-44 owns the recommendation-decision record, embedding
> spaces, derived-feature boundary, and evidence required before Stage 4 can
> receive non-zero weight.

## Goal

Never recommend a venue that the product already knows is closed or unreachable
at the proposed time. Rank only the feasible set, keep the result deterministic
without behavioural history, and allow personalization to improve that order
later without weakening any hard constraint.

The recommendation engine is a staged pipeline:

```text
catalog facts
  -> hard feasibility
  -> deterministic ranking
  -> schedule and validate
  -> optional evidence-gated personalization
  -> explanation
```

An LLM may classify a request or explain a result. It never selects a venue,
assigns a time, invents hours or transit, or restores a candidate excluded by
the feasibility stage.

## Why this is a separate spec

The existing create and swap paths can select a venue first and discover only
after the mutation that its saved hours do not cover the slot. The scheduler
then returns warnings for many nodes, including nodes unrelated to the edit.
That sequence is backwards: a known hours conflict is an eligibility failure,
not advisory copy.

SPEC-40 intentionally freezes a deterministic catalog-create foundation.
SPEC-11 captures preference signals but explicitly does not build a preference
model. SPEC-29 and SPEC-35 own alerts, not itinerary selection. This spec is the
missing engine contract between those surfaces.

## Source contracts

1. Structured opening hours use the seven-day, split-window shape curated under
   SPEC-08. A closed day is an empty list. Unknown hours are null.
2. Destination-local conversion uses the IANA timezone in the current region
   registry. Server, device, and UTC calendar dates are never substitutes.
3. Locked bookings from SPEC-10 are immovable hard constraints.
4. Catalog identity, coordinates, dwell time, category, tags, and region are
   inputs. Missing required identity or geometry makes a venue ineligible.
5. Live provider `open_now` is not historical or future-slot authority.
6. Missing hours mean unknown. They do not become invented default hours and do
   not support an "open" claim.

The scheduling path must consume the structured hours. Flattening them into one
weekday-independent `HH:MM-HH:MM` string may remain for backward-compatible
rendering, but it cannot decide feasibility.

## Stage 1: hard feasibility

A candidate enters the ranker only when all known hard constraints pass:

- correct `geo_region`;
- stable venue identity, name, and coordinates;
- not an infrastructure category;
- not already used where the active no-repeat contract applies;
- open for the full `[local_start, local_start + dwell]` interval on the
  scheduled local weekday, including split windows and overnight windows;
- reachable from the preceding active node using the deterministic transit
  estimate;
- leaves enough time to reach the next locked booking;
- does not move or overlap a locked booking;
- remains inside its local calendar day.

Unknown hours skip only the hours check. They carry uncertainty into the
explanation layer and must not be described as open.

When no candidate is feasible, the fallback order is deterministic:

1. try another open window on the same local day;
2. try another category bucket;
3. reduce the number of stops;
4. return a typed insufficient-capacity result.

The engine never keeps a known-closed venue merely to preserve four stops.

## Stage 2: deterministic ranking

Rank only the feasible set. Initial factors are:

- SPEC-40 trip-interest overlap;
- time-of-day suitability;
- route compactness and distance;
- category diversity within and across days;
- trip party suitability where catalog tags are discriminative;
- a stable tie-break by normalized venue name and then `venue_id`.

Same catalog, trip context, dates, and constraints must produce the same venue
ID sequence. Random transit multipliers, server clock time, and unordered set
iteration are forbidden.

Sponsored influence, if present, is applied only after feasibility and remains
subject to the SPEC-17 disclosure contract. Payment can never reopen an
infeasible candidate.

### Slot-shaped days, not clock-shaped days

Flexible itinerary UI shows coarse destination-local slots, not invented clock
times. Groups, pace, and traffic make 10:52 unusable as a promise.

The default full in-city day has four named slots:

```text
morning_tour
lunch
afternoon_evening_tour
dinner
```

Breakfast is optional later; it is not a default generated slot. An afternoon
show and dinner may share one remaining evening after a late arrival; they are
not a fifth default slot on a full day.

Keep exact instants internally for hours, walking, locked bookings, and
validation. Render locked flights, trains, and hotel check-in/out as exact
local times. Render flexible stops as the slot name. Do not display walking
arithmetic as the traveller-facing start.

A catalog venue occupies one or more slots from its dwell and category:

- a typical sight or activity occupies `morning_tour` or
  `afternoon_evening_tour`;
- a restaurant occupies `lunch` or `dinner`;
- a known whole-day excursion (canyoneering, island hopping, long out-of-city
  tour) occupies morning and afternoon, including lunch on site or packed, and
  leaves `dinner` as the only remaining generated recommendation that day.

Do not pack four city stops around a whole-day trip. Do not invent filler to
look busy.

### Travel days consume slots before packing

Arrival, departure, and inter-city transfer days derive remaining slots from
the locked booking plus buffer, then pack only what still fits.

Conservative defaults until the traveller confirms a more ambitious intent:

- landing or arriving early evening: `dinner` only;
- arriving mid-afternoon (for example a 15:00 Vientiane to Luang Prabang
  train) plus hotel check-in: remaining evening may hold one show or walk
  plus `dinner`, never a morning-style tour;
- departing on a morning flight or train: no tour that morning; hotel-near
  logistics only if the remaining window is honest;
- checkout day: remaining morning activity, if any, stays near the hotel.

Buffers already specified for pre-flight cutoff and hotel return still apply.
`pack_day` must consume those remaining slots; earliest-fit four-stop packing
on a travel day is a product bug even when every venue is open.

A later HITL intent (rest vs explore after arrival; tight vs open before
departure) may restore extra remaining slots. It cannot restore a slot the
booking and buffer have already consumed. Empty remaining time stays empty.

## Stage 3: schedule and validate

Creation schedules each local calendar day independently. Work on one day
cannot push the next day's first stop.

Phase A3 implementation is deliberately split:

- A3a schedules candidates into their earliest fitting same-day structured
  hours window and makes pre-date `max_days` conservative across all seven
  possible start weekdays.
- A3b replaces random/synthetic transit in feasibility decisions and enforces
  reachability from the previous active node and to the next locked anchor.

The create paths under SPEC-32, SPEC-36, and SPEC-40 validate before
persistence. A failed validation leaves no trip, party, or partial schedule.

Swap search receives the trip, target node, target local slot, and neighbouring
constraints. It returns only feasible candidates for that slot, using each
candidate's own dwell time. Applying a selected candidate reruns the same
feasibility check so search and mutation cannot drift.

Warnings are scoped to uncertainty or to nodes actually affected by the current
operation. One swap must not emit a trip-wide dump of pre-existing messages.
Known infeasibility is resolved or refused before persistence rather than
rendered as a warning afterward.

## Stage 4: evidence-gated personalization

Personalization is deferred until enough clean signals exist. The deterministic
ranker remains the fallback.

An outcome alone is not a training label. Before collecting a cohort for
learning, SPEC-44 records the complete feasible exposure, exact exclusion
reasons, component scores, displayed order, policy/catalog/taxonomy versions,
and sponsored contribution. Accepted/rejected swaps, skips, visits, arrival,
and dwell link to that immutable decision.

Eligible future inputs include:

- SPEC-11 forced choices;
- loved venues;
- accepted and rejected swaps;
- confirmed skips and their reason;
- observed arrival deltas and dwell times;
- venue acceptance by local weekday and slot.

Learned signals may reorder only the feasible set. They cannot weaken hours,
region, reachability, lock, or day-boundary constraints.

Each learned feature has a minimum sample threshold, recency window, and
fallback. A small number of interactions must not materially move the schedule.
Collaborative filtering, user embeddings, and cross-user similarity remain out
until volume and deletion semantics justify them.

The earlier suggested 10-15% learned contribution remains an experiment
hypothesis, not a fixed production constant or starting value. Phase B must
first define score normalization, minimum evidence, train/evaluation isolation,
city/party/cold-start/sponsorship slices, rollback, and a maximum influence
bound. Until that evidence exists, learned weight is zero and the deterministic
ranker is the complete ranking path.

Stage 4 is not part of the first implementation brief. Phase A ships stages 1
through 3 and the LLM boundary tests. A later Phase B may activate
personalization only after its signal thresholds and deletion behavior are
specified from observed data.

## LLM boundary

Allowed:

- map ambiguous natural language to structured filters;
- propose a structured mutation patch (`SWAP_NODE`, `ADD_BOOKING`, or the
  existing event equivalent) for the traveller to confirm;
- summarize why a feasible result matched the trip;
- phrase retrieved facts through the SPEC-17 trust envelope.

Forbidden:

- emit itinerary nodes or times directly;
- persist a patch without the existing trip-event path and HITL sheet;
- choose a venue outside the feasible set;
- state opening hours or transit not present in a source;
- override a locked booking;
- hide insufficient catalog capacity behind generated prose;
- invoke the solver through a free-form tool loop or MCP server.

## Cost and offline behavior

Stages 1 through 3 use local catalog data and deterministic code. No model call
is required for create or swap. Per-city normalized hours and ranking features
may be precomputed and cached because they are small and stable.

Offline clients may display cached feasible alternatives with cache age and
unknown-live-state treatment. Structural apply continues to follow the existing
online mutation contract.

## Tests

- destination timezone differs from UTC and device timezone;
- venue closed on the scheduled weekday is excluded;
- split lunch and dinner windows accept covered slots and reject the gap;
- overnight windows are interpreted explicitly;
- unknown hours do not produce an open or closed assertion;
- candidate dwell must fit completely inside the window;
- next locked booking removes an otherwise attractive candidate;
- day N movement cannot push day N+1;
- create validates before persistence and leaves no trip or party on failure;
- swap search and apply share the same target-slot feasibility result;
- warning output is limited to nodes affected by the operation;
- deterministic inputs produce the same ordered venue IDs;
- flexible itinerary rendering uses named slots, not walking-derived minutes;
- a feasible mixed-window catalog fills morning, lunch, afternoon/evening, and
  dinner rather than four morning stops;
- a whole-day excursion occupies morning and afternoon and leaves dinner;
- an early-evening arrival packs dinner only;
- a mid-afternoon arrival plus hotel check-in packs at most evening plus dinner;
- insufficient remaining slots leave open time instead of adding filler;
- interest and later personalization change only feasible-set order;
- sponsored weight cannot restore an excluded candidate;
- LLM sabotage cannot place a closed or unreachable venue;
- create and swap call no LLM when deterministic inputs are sufficient.

Golden cases include a morning-only venue, a night market, a split-window
restaurant, a closed weekday, unknown hours, and a locked transport anchor.

## Acceptance

- [ ] Structured weekday and split hours are consumed by create, swap, and
      validation
- [ ] Known-closed venues are never scheduled or offered for the target slot
- [ ] Destination-local dates and times are used end to end
- [ ] Transit and day packing are deterministic
- [ ] Locked bookings and next-anchor reachability are hard constraints
- [ ] Create validates before any trip or party persistence
- [ ] Swap search and apply cannot disagree on feasibility
- [ ] Warnings are scoped and do not repeat unrelated trip-wide issues
- [ ] Ranking is deterministic without behavioural history
- [ ] Flexible stops render as named slots; locked bookings keep exact times
- [ ] Default in-city generation uses morning, lunch, afternoon/evening, dinner
- [ ] Whole-day excursions and travel days pack only remaining slots
- [ ] LLM paths cannot change the solver result
- [ ] Full Python and Flutter suites are green from `origin/main`

Phase B acceptance, deferred:

- [ ] Feasible exposure, exclusions, score components, displayed order,
      sponsorship, and policy/catalog/taxonomy versions are recorded
- [ ] Outcomes link to immutable decisions rather than acting as context-free
      labels
- [ ] Minimum sample, recency, and fallback rules are specified from field data
- [ ] Held-out evaluation prevents traveler and trip leakage and beats the
      frozen deterministic baseline on named quality measures
- [ ] City, party, cold-start, sparse-data, and sponsorship slices pass
- [ ] Personalization reorders only the feasible set
- [ ] Deletion removes the user's derived preference state
- [ ] A kill switch restores the prior deterministic policy without an app
      release

## Explicit non-goals

- live Maps hours as future-slot truth;
- new venue ingestion or opening-hours mining;
- forced-choice onboarding UI;
- a durable preference profile;
- collaborative filtering or cross-user vectors;
- money and affordability ranking;
- trip-less Ask or grounded chat;
- LLM itinerary generation;
- map-first swap comparison UI.
