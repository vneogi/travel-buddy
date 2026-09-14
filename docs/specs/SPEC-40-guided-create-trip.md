# SPEC-40: Guided Create Trip Foundation

> Status: DONE. PR #61 squash-merged as `ebdea52`.
>
> SPEC-39 PDF intake remains deferred. This spec deliberately stops before
> LLM generation, vector memory, and similar-trip inspiration. It creates the
> typed, persisted input contract those later capabilities will consume.

## Goal

Replace the single-city Create dialog with a short, full-screen wizard:

1. Where are you going?
2. When? (start and end dates)
3. Who is travelling?
4. What does this trip want more of?
5. Review and create

The result is a deterministic, catalog-backed multi-day itinerary. The flow
must remain useful when every model provider is unavailable.

## Product decisions

### Trip input, not a permanent profile

Party and interests describe this trip. They do not become durable claims
about the person's general preferences. SPEC-11 is explicit that checkbox
preferences are weak ranking evidence; behavioural accept/reject signals
remain authoritative.

### Existing party infrastructure is reused

Use the existing SPEC-03 `TripPartyIn`, `trip_party`, `party_member`, signal
stamping, and hosted migration 0003. Do not add another party table or
vocabulary.

The first UI supports:

- Solo
- Couple
- Friends
- Family with young kids
- Family with teens
- Multi-generation

The family choices may ask party size and age bands. Never collect names or
birth dates.

### Interests are bounded trip constraints

The server owns one registry of interest IDs, labels, and their category/tag
matches. Initial options:

- `history_culture`
- `food_markets`
- `nature_scenery`
- `adventure_outdoors`
- `arts_crafts`
- `wellness_slow`
- `nightlife_social`

The traveller may choose zero to three. Zero means balanced catalog order, not
an invented preference.

### Dates and capacity

Single-city create gains an inclusive `end_date`. `start_date` remains for
backward compatibility.

- `end_date` omitted: preserve the existing one-day SPEC-32 output exactly.
- `end_date` present: build every local calendar date from start through end.
- New range mode uses exactly four unique catalog venues per day.
- A venue cannot repeat anywhere in the trip.
- The advertised maximum for a region is:
  `min(5, floor(unique eligible stable venues / 4))`.
- The API, validator, and UI must consume the same advertised value.
- Unknown, reversed, past, over-capacity, and zero-day ranges return a typed
  422. Never silently shorten a trip.

The five-day product ceiling limits an early catalog itinerary from becoming
an unreviewable wall of cards. It is not a recommendation for how long to stay.

### Deterministic interest ranking

Interest selection changes deterministic catalog priority; it does not call
an LLM or hybrid search.

For each requested day:

1. exclude infrastructure, missing names/coordinates/stable IDs, and venues
   already used by this trip;
2. score category and vibe-tag matches from the server registry;
3. preserve category-bucket diversity;
4. break ties by normalized venue name, then stable venue ID;
5. schedule from 09:00 in the destination IANA timezone and store UTC.

Same catalog + destination + dates + interests must produce the same venue ID
sequence.

This foundation intentionally does not make opening hours, transit, or learned
preferences part of selection. SPEC-41 owns the next engine layer: structured
hours and reachability as hard constraints, followed by deterministic and later
evidence-gated ranking.

## API and persisted contract

`GET /api/v1/trips` keeps existing fields and adds:

```json
{
  "create_trip_options": {
    "party_types": [{"id": "solo", "label": "Solo"}],
    "interests": [{"id": "history_culture", "label": "History & culture"}],
    "max_days_by_region": {"luang_prabang_laos": 5}
  }
}
```

Do not mirror these option lists in Flutter. Old cached Home snapshots without
`create_trip_options` must still parse.

Range create:

```json
{
  "geo_region": "luang_prabang_laos",
  "start_date": "2026-10-06",
  "end_date": "2026-10-09",
  "party": {
    "party_type": "friends",
    "size": 3,
    "members": []
  },
  "preferences": {
    "interest_ids": ["food_markets", "arts_crafts"]
  }
}
```

Add typed creation context to `TripState` and its Dart model so the chosen
dates and interests survive fetch/cache/offline rendering. Party remains in
the existing party contract. No migration is required for creation context
stored inside trip state JSON.

Corridor create remains segment-based and unchanged.

The current persistence implementation writes the trip and party separately.
A failure between those writes can leave an orphan trip. This is a known
pre-existing risk, not redesigned in this foundation. A future persistence
transaction must preserve the wire and creation-context contracts above.

## Flutter flow

- Home's large Create card opens `/trip/create`.
- Use a full-screen wizard, not stacked dialogs or bottom sheets.
- Back returns to the previous step without losing entries.
- Show progress and a plain-language summary on Review.
- Dates use a range picker, destination-local calendar values, and the
  server-advertised maximum.
- Interests are large multi-select cards/chips with zero-to-three validation.
- Disable duplicate submission while create is in flight.
- Success opens the created itinerary. Failure retains entered values and
  displays the typed server message.
- The existing corridor entry and corridor date form remain separate and
  unchanged.
- The flow must scroll without overflow at 800x600 and common phone sizes.

## Required backend proofs

1. Legacy create without `end_date` returns the same one-day venue sequence.
2. A valid four-day range returns 16 nodes on four destination-local dates.
3. No venue repeats across days.
4. Same request is deterministic.
5. Interest selection changes priority only through the registry.
6. Invalid interest IDs, reversed dates, and ranges above the advertised cap
   return typed 422 errors.
7. Insufficient capacity leaves no trip or party behind.
8. Party persists and GET trip returns party plus creation context.
9. Create calls neither LLM nor hybrid search and consumes no reroute quota.
10. Corridor create remains byte-shape compatible.
11. The options test is non-vacuous: every advertised region has a max and
    every option ID is accepted by validation.

Each guard must include a sabotage proof where practical.

## Required Flutter proofs

1. Old and new Home snapshots parse.
2. Home Create opens the wizard; corridor entry still opens its own form.
3. Back/next preserves destination, range, party, and interests.
4. End before start and above-max ranges cannot proceed.
5. Zero interests is allowed; more than three is refused.
6. Review shows the exact payload and one tap sends one request.
7. Repository sends `start_date`, `end_date`, party, and interest IDs.
8. Server error retains the wizard state.
9. Success opens the returned trip.
10. 800x600 has no overflow and every action is scroll-reachable.

## Explicit non-goals

- LLM itinerary generation or model-provider switching
- Similar-trip retrieval, embeddings, vector memory, or traveller profile
- Forced-choice preference training
- PDF/OCR/import, hotels, transport, or booking extraction
- New destinations, venue discovery, or synthetic fallback venues
- Changes to corridor limits or SPEC-38 active-trip behavior

## Follow-up

Hours-aware feasibility and staged ranking under SPEC-41 come before inspiration
or model-generated itineraries.

SPEC-42 later separates the selected trip span from generated content density.
It permits a wider trip range, auto-populates at most five starter days, renders
the remaining dates as editable empty days, and adds direct Add/Move actions.
That change is not folded into this foundation because sparse-day rendering and
structural editing require their own compatibility contract.

A later brief may add inspiration and generation using this exact creation
context. It must define source/provenance, latency and cost budgets, fallback
behavior, and how similar trips are anonymized before any implementation.
