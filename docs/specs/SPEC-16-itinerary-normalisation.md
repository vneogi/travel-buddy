# SPEC-16: Itinerary Normalisation

> Status: IMPLEMENTED in 9db053b, as migration 0014. Amended after the fact to
> record the ID type and to state a requirement this spec originally left without
> an owner. See the As built section.
>
> Migration number was taken at implementation time, not reserved here. See the
> process rule in `docs/DATA_LAYER_ROADMAP.md`.
>
> Rationale and priority: `docs/DATA_LAYER_ROADMAP.md` concern 1.
> Sequencing consequence: SPEC-10 should land on this schema, not before it.

## Goal

Move the itinerary out of `trip_states.state_json` into `trip_node` and
`trip_edge` rows, without changing anything the Flutter app can observe.

## Why this is first

The product's central claim is that it learns from what a traveller does to
their itinerary. The itinerary is currently a JSONB blob, so no question about
itinerary behaviour can be answered in SQL. Every analytical question requires
loading trips into Python and parsing them, which means in practice that none of
them get asked.

This blocks, specifically:

- the batch jobs in `docs/DATA_LAYER_ROADMAP.md` concern 4, which need to join a
  signal to the itinerary position it happened at
- transitions as first-class objects, because an edge cannot exist inside a blob
- a graph backend, because edges are what a graph consumes and ours are implicit
- the first question any future recommender asks, which is which venues co-occur

It also makes SPEC-10 cheaper. A booking anchor is a node with a type and
`is_locked` set. Adding booking fields to a blob-resident TripNode first means
doing booking anchors twice.

## Design decisions

1. **Normalise storage; do not change the wire format.** The API keeps returning
   the same JSON the app already consumes, composed from rows at read time. This
   is the decision that makes the whole change safe: no Flutter change, no app
   release, no new offline-cache format, no coordinated deploy. The blob shape
   becomes a serialisation of the tables rather than the system of record.

   It follows that the governing test is a round trip, not a feature test. See
   Tests.

2. **`trip_states` survives as the trip header.** It keeps `trip_id`, `user_id`,
   `is_active` and trip-level fields. Only the itinerary moves out.

3. **Dual-write during transition, then stop.** Phase one writes both the rows
   and `state_json`, and reads from `state_json`. Phase two reads from rows with
   `state_json` still written, so a regression is a one-line revert rather than a
   restore. Phase three stops writing `state_json` and the column is dropped in a
   later migration, once a full field test has run against rows.

   This is not indecision. The itinerary is the one structure whose corruption
   ends a trip in progress, and the Oct 2 field test has no fallback.

4. **Nodes are ordered by `(day_index, seq)` with sparse `seq`.** Leave gaps, so
   inserting an activity does not rewrite every following row. A reschedule that
   renumbers everything makes it impossible to tell a moved node from a new one,
   which destroys the signal we are trying to capture.

5. **A node does not have to reference a venue.** `node_type` is a closed
   vocabulary covering at least `activity`, `flight`, `hotel`, `train`, `rest`
   and `transit`. Rest and travel time are real itinerary content, and forcing
   them to point at a venue is what pushed them into the blob as special cases in
   the first place.

6. **`is_locked` is a node property and booking anchors set it.** The scheduler
   already respects locked anchors; this gives locking a column instead of a JSON
   key, and gives SPEC-10 its implementation almost for free.

7. **`status` is explicit:** `planned`, `visited`, `skipped`, `cancelled`. This is
   what lets a signal be joined to what actually happened at that position. A
   skipped node is data, and today it is indistinguishable from a node that was
   never scheduled.

8. **Signals point at nodes, using the generalisation that already exists.**
   Migration `0005` replaced the venue-only subject with `(entity_type,
   entity_id)`. `entity_type = 'trip_node'` needs no schema change, which is that
   migration's foresight paying off.

9. **Separate the trip edge from what we know about a pair of places.** This is
   the decision most likely to be got wrong. A `trip_edge` is an instance inside
   one itinerary: from this node, to that node, by this mode, at this time. It is
   ephemeral and a reschedule legitimately destroys it.

   What we learn about getting from one place to another -- the exit to use, the
   realistic duration, the fare band, where drivers actually wait -- must outlive
   any single itinerary, or the convenience layer loses its knowledge every time
   the traveller reroutes. That belongs to the pair of places, not to the trip,
   and it lives as a derived feature keyed on the place pair.

   So: `trip_edge` carries the choice made and the outcome observed. Durable
   knowledge is aggregated out of many such observations and stored separately.

10. **Both backends implement it, in the same commit.** `DatabaseService` and
    `SupabaseService` are independent implementations of one contract (R4, R13). A
    green suite against in-memory proves nothing about Supabase, and
    `tests/test_backend_parity.py` must cover the new methods.

11. **The backfill is idempotent and verifiable.** It parses every existing
    `state_json` into rows and can be re-run without duplicating. It reports how
    many trips it converted and how many round-tripped exactly, and a
    non-exact round trip is a failure that stops the migration rather than a
    warning.

12. **No PostGIS.** Coordinates stay as columns, consistent with the rest of the
    schema. Distance is computed in application code as it is today.

## Shape

Illustrative, not final DDL:

    trip_node(
      node_id, trip_id, day_index, seq, node_type, venue_ref NULL,
      title, scheduled_start, scheduled_end, is_locked, status,
      created_at, updated_at
    )

    trip_edge(
      edge_id, trip_id, from_node_id, to_node_id, transport_mode,
      expected_duration_minutes, observed_duration_minutes NULL,
      expected_cost_band NULL, notes NULL, created_at
    )

`venue_ref` is the existing venue reference, nullable for non-venue nodes.
Edges reference nodes rather than venues, so a trip can visit the same venue
twice without ambiguity.

## As built

Two things were settled during implementation rather than here, and both belong
in the spec rather than only in a commit message.

**`node_id` and `edge_id` are TEXT, not UUID.** The application has always
generated node IDs as an 8-character hex slice of a UUID. The first version of
migration 0014 declared the columns UUID, which Postgres would have rejected on
every insert, and the suite stayed green over it because the in-memory backend
does not type-check and the Supabase tests skip without credentials. That is the
more useful lesson than the fix: a green suite says nothing about a column type
while the only backend that enforces types is never exercised. Both generators
now live in `models/ids.py` so the format is declared once. Eight hex characters
is 32 bits, which is an accepted limit for now rather than an oversight, and
widening it is a one-file change plus a decision about existing rows.

**`observed_duration_minutes` is filled on ingest, not when a trip is saved.**
This spec named the column without naming who fills it, so the first
implementation wrote NULL. The value is the gap between consecutive arrival
signals and is only known after the fact. SPEC-30 (`f8349a8`) writes it on
`trip_edge` via `update_edge_observed_duration(trip_id, from_node_id,
to_node_id, minutes)` when two confirmed arrivals land. Dual-write of itinerary
JSON must preserve observed minutes on matching from/to pairs. Transport cost
on the same table is still unwritten (SPEC-23).

## Tests

- **Round trip, over every trip in the database.** Compose the normalised rows
  back into JSON and assert equality with the original `state_json`. This is the
  test that proves the change alters nothing observable, and it is the acceptance
  gate for phase two. Assert on parsed structures, not on formatted strings.
- Backfill is idempotent: running it twice produces the same row count and the
  same content.
- A non-round-tripping trip fails the backfill loudly, proven by feeding it a
  deliberately malformed `state_json`.
- Sparse `seq` holds: inserting a node between two others changes no other row's
  `seq`.
- A locked node survives a reschedule that moves everything around it.
- A node with `venue_ref` null persists and composes correctly, so rest and
  transit nodes are not a special case.
- `status` transitions are recorded, and a skipped node is distinguishable from
  one that was never scheduled.
- A signal with `entity_type = 'trip_node'` records and reads back on both
  backends, with no migration required.
- Backend parity covers every new method (R13).
- The same trip visited twice by the same venue produces two distinct nodes and
  unambiguous edges.
- Deleting a trip removes its nodes and edges, with no orphans.
- Two arrival signals on consecutive nodes produce an observed duration on the
  edge between them, and re-running the sync does not double count it.

## Acceptance

- [ ] `trip_node` and `trip_edge` created by an additive migration, number taken
      at implementation time
- [ ] Both backends implement the contract; parity test covers the new methods
- [ ] Backfill written, idempotent, and reporting converted and round-tripped
      counts
- [ ] Round-trip equality proven for every trip currently in the database
- [ ] API responses byte-equivalent to the previous shape, proven by a test that
      compares parsed payloads before and after
- [ ] Phase one shipped and running with dual write, reads still from
      `state_json`
- [ ] Phase two flipped reads to rows, with `state_json` still written and a
      documented one-line revert
- [ ] No Flutter change required, and none made
- [ ] Signals accepted with `entity_type = 'trip_node'`; drift guard green
- [ ] Suite green with skip reasons named (R8); verified from `origin/main` (R10)
- [ ] Phase three and the `state_json` drop explicitly deferred until after a
      full field test has run against rows
- [ ] observed_duration_minutes populated by a sync-time derivation from arrival
      signals, with a test that a second visit updates the edge. NOT MET
