# SPEC-46: What Now and Foreground Context

> Status: SPECIFIED. Not implemented.
>
> Recorded 24 Sep 2026. This is the in-the-moment engagement loop:
> "I have two hours, I am tired, what still works?" It is not a generic
> chat mode and not a background-location system.
>
> Phase A depends on G0 scheduling reliability, SPEC-41 feasibility,
> SPEC-34 trip-local search, SPEC-25 grounded trip Ask, and SPEC-45
> visible surfaces. Phase B (device location) additionally depends on
> the applicable SPEC-43 identity, consent, logging, retention, abuse,
> and cache-isolation controls.

## Goal

Turn the product thesis into one obvious action:

> What can I safely do now, before my next locked commitment?

The answer uses current trip context, available time, explicit temporary
state, opening hours, and deterministic reachability. It never invents live
traffic, crowds, price, weather, or a reason.

## Priority

1. Close the current G0 field-test blockers and retest the owner APK
   (include SPEC-45 Phase A chrome already on `main`).
2. Close SPEC-44 Phase A (ephemeral PostgreSQL proof, then merge).
3. Complete remaining SPEC-25 trip-optional Ask and SPEC-10 paste work
   as sequenced in PROJECT_STATUS.
4. Implement SPEC-43 before any non-owner distribution.
4. Re-run G0 hosted/device acceptance.
5. Implement SPEC-43 before any non-owner build.
6. Phase A may be built for the owner alongside grounded SPEC-25 if it
   remains a deterministic, no-GPS slice. It must not delay SPEC-43.
7. Phase B foreground location starts only after its SPEC-43 controls pass.

The capability is designed now but does not jump reliability or release
safety.

## Product shape

Entry copy: **What now?**

The sheet asks only for context the engine can use:

- available time: 45 min / 90 min / 2 hours / until next booking
- energy: low / normal / high
- walking tolerance for this decision: short / normal / longer
- optional intent: quiet / food / indoors / culture / anything
- location source, shown explicitly

It does not ask for a permanent personality profile.

The result is a short list, not a chat essay. Each candidate shows:

- friendly name and neighbourhood
- intended slot or activity type
- typical dwell when known
- deterministic fit reasons
- material unknowns
- one primary action: compare / swap / view details

No selection mutates the itinerary before explicit confirmation.

## Phase A: useful without device GPS

Location source order:

1. Traveller-selected itinerary stop: "I am near this stop."
2. Current actionable or most recently completed node, labelled
   **Using your trip position**, not **Using your location**.
3. Traveller-selected neighbourhood from the current city.
4. Region anchor for city browsing only.

A region anchor must never produce "near you", distance, or walking claims.
It may produce "in Vientiane" browsing results.

Phase A candidates are catalog venues in the active trip region. Selection
is deterministic:

1. exclude infrastructure and existing itinerary venue IDs where relevant;
2. match requested activity/food intent and named slot;
3. require structured-hours fit when known;
4. require available-time fit from dwell + deterministic walking;
5. preserve flight, train, tour, and hotel-return constraints;
6. rank only the feasible set using explicit trip interests and temporary
   request context.

An LLM may not choose or validate candidates. Before SPEC-43, the hosted
owner build remains deterministic. After SPEC-43, model wording may explain
already-computed reason codes but may not add a fact.

## Phase B: one-shot foreground location

Device location is an in-the-moment advantage and should be built, but with
a deliberately narrow contract.

- The traveller taps **Use my current location**. No location request on
  app launch, itinerary open, resume, or background.
- Show just-in-time purpose copy before the OS prompt: location is used once
  to find feasible nearby options and is not used for ads.
- Foreground one-shot fix only. No continuous watcher, geofence, breadcrumb,
  background service, or battery polling.
- Manual/itinerary-position fallback remains first-class after denial.
- Send the minimum precision needed for nearby ranking. Round coordinates
  before network transfer when the search radius permits it.
- The request body may contain the ephemeral coordinate. It must not enter
  URLs, logs, analytics, event payloads, model prompts, semantic-cache keys,
  trip state, or notification payloads.
- No raw-coordinate persistence. Server processing lifetime is the request;
  operational logs retain only a coarse region and request ID.
- Permission can be withdrawn; the product continues with Phase A.
- A location-derived result says **Near your current location** and records
  the location source in the response envelope.

SPEC-43 must prove those properties before Phase B reaches another person.

## Trustworthy recommendation reasons

Reasons are closed codes computed by the same deterministic helpers used to
accept the candidate:

- `fits_available_window`
- `open_for_planned_time`
- `keeps_next_booking_reachable`
- `matches_requested_type`
- `matches_trip_interest`
- `same_neighbourhood`
- `short_walk_from_context`
- `lower_typical_dwell`
- `indoor_option`

Each code has:

- a predicate;
- required source fields;
- user copy;
- a test that makes the predicate false and removes the reason.

Examples:

- **Fits your 90-minute window**
- **Open during the planned slot**
- **Keeps your 18:00 train reachable**
- **In the same neighbourhood**
- **Matches your culture interest**

The following are not allowed without their owning data:

- cheaper / saves INR X (SPEC-23);
- X minutes faster unless deterministic transit computed both sides;
- less crowded / quieter now without a current sourced claim;
- better / hidden gem / locals prefer without SPEC-17 evidence;
- cooler / weather-safe without provider evidence and a defined predicate.

Unknowns are useful:

> Price unknown | live crowds unknown | traffic not checked

That is more trustworthy than leaving the traveller to infer completeness.

## Response contract

The server returns structured candidates. It does not return only prose:

```text
candidate_id
venue_id
name
micro_location_display
category
typical_dwell_minutes?
scheduled_start?
reason_codes[]
unknown_fields[]
location_source
sponsored_boost_applied
```

Opening-hours, dwell, distance, and recommendation-reason values must migrate
to SPEC-17 envelopes when that backend exists. Until then, copy is limited to
the deterministic reason registry and fields already used by scheduling.

Sponsored contribution remains visible and inspectable.

## Relationship to Ask

Suggested prompts such as "I am tired" may open this sheet with `energy=low`.
Ask does not free-form mutate the itinerary. The operational path is:

```text
intent -> structured temporary context -> feasible candidates
       -> compare -> explicit confirm -> server mutation
```

The assistant may explain a refusal:

> Nothing nearby fits before your train. Keep the current plan or widen
> walking tolerance.

It may not bypass the candidate predicates.

## Temporary context vs durable preference

Energy, mood, heat tolerance, available time, and today's walking tolerance
expire with this request or trip day. They are not silently promoted into a
traveller profile.

An accepted/rejected recommendation may emit the existing closed signals.
Raw device location never accompanies those signals.

## Offline

Cached venue/details may support browsing from a selected trip stop. Offline:

- show cached freshness;
- do not claim open now unless the necessary hours and clock logic are local;
- do not compute or queue a structural replan;
- allow a heart or other already-supported local outcome;
- offer retry after reconnect for live candidate generation.

Full offline maps remain outside this spec.

## Tests

Phase A:

- Vientiane trip never searches Dubai.
- No infrastructure candidate.
- A 90-minute request excludes candidates whose dwell + walking exceed it.
- Candidate cannot violate a locked flight/train/tour or hotel return.
- Every displayed reason predicate is true; sabotage one predicate and its
  reason test fails.
- Region-anchor results never say near you or show distance.
- Selecting a row does not mutate; confirm sends one command.
- Unknown price/crowds/traffic are explicit when absent.

Phase B:

- no permission request before the explicit button;
- denial uses Phase A without an error dead end;
- coordinate appears only in the approved request body;
- URL, logs, signals, cache key, trip state, and model DTO contain no raw
  coordinate;
- no background-location manifest permission or watcher;
- server request handling does not persist the coordinate.

## Acceptance

- The owner can ask What now from an active trip without GPS.
- Results fit the actual time window and next locked commitment.
- Reasons are deterministic and inspectable; unknowns are named.
- Confirm is required before mutation.
- Phase B cannot ship externally until its SPEC-43 location proofs pass.
- Denying location does not reduce the product to an empty screen.

## Non-goals

- Background GPS, geofencing, live people map, location history
- Generic trip-less chat
- Live traffic or crowd inference
- Money estimates before SPEC-23
- Full map shell or offline tiles
- Persisting mood/energy as a durable personality
- New city support
