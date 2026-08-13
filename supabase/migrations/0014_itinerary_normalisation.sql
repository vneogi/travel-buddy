-- Migration 0014: Itinerary Normalisation (SPEC-16)
--
-- Moves itinerary data from the trip_states.state_json JSONB blob into
-- normalised trip_node and trip_edge tables.
--
-- TIMEZONE CHOICE: scheduled_start and scheduled_end use TIMESTAMPTZ.
-- Each node carries a geo_region column that maps to an IANA timezone via
-- application-level REGION_TIMEZONES (e.g. 'dubai_uae' -> 'Asia/Dubai',
-- 'luang_prabang_laos' -> 'Asia/Vientiane'). This avoids storing redundant
-- timezone strings on every row while keeping multi-city trips correct.
-- Rationale: a region reference is already present on both trip_states and
-- venues_rag; reusing it here means no new concept for the app to learn.
--
-- NODE_ID STABILITY: node_id is a TEXT primary key (8-char hex) generated once at node
-- creation. Reschedules update day_index, seq, and times but never recreate
-- the node_id. Signals reference nodes via (entity_type='trip_node', entity_id)
-- and a regenerated ID would silently orphan collected signals.
--
-- OBSERVED_DURATION: trip_edge.observed_duration_minutes exists from day one
-- so the schema is ready when signal-driven writes arrive. The column is
-- nullable and starts empty; a future derive_observed_durations() will
-- populate it from visited_confirmed signal pairs once production data
-- accumulates. No writer exists yet — this is an honest empty column.

-- trip_node: one row per scheduled activity/stop in an itinerary.
CREATE TABLE IF NOT EXISTS trip_node (
    node_id         TEXT PRIMARY KEY,
    trip_id         UUID NOT NULL REFERENCES trip_states(trip_id) ON DELETE CASCADE,
    day_index       INTEGER NOT NULL DEFAULT 0,
    seq             INTEGER NOT NULL DEFAULT 1000,
    node_type       TEXT NOT NULL DEFAULT 'activity'
                    CHECK (node_type IN (
                        'activity', 'flight', 'hotel', 'train', 'rest', 'transit'
                    )),
    venue_ref       UUID NULL,  -- nullable: rest/transit nodes have no venue
    title           TEXT NOT NULL,
    scheduled_start TIMESTAMPTZ NULL,
    scheduled_end   TIMESTAMPTZ NULL,
    duration_minutes INTEGER NOT NULL DEFAULT 90,
    is_locked       BOOLEAN NOT NULL DEFAULT false,
    status          TEXT NOT NULL DEFAULT 'planned'
                    CHECK (status IN ('planned', 'visited', 'skipped', 'cancelled')),
    geo_region      TEXT NULL,  -- IANA timezone lookup via REGION_TIMEZONES
    micro_location  TEXT NULL,
    lat             DOUBLE PRECISION NULL,
    lng             DOUBLE PRECISION NULL,
    vibe_tags       TEXT[] DEFAULT '{}',
    opening_hours   TEXT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Ordering index: the query that composes the API response
CREATE INDEX IF NOT EXISTS idx_trip_node_trip_order
    ON trip_node(trip_id, day_index, seq);

-- Lookup by venue across all trips (co-occurrence queries)
CREATE INDEX IF NOT EXISTS idx_trip_node_venue
    ON trip_node(venue_ref) WHERE venue_ref IS NOT NULL;

-- trip_edge: one row per transition between consecutive nodes.
CREATE TABLE IF NOT EXISTS trip_edge (
    edge_id                     TEXT PRIMARY KEY,
    trip_id                     UUID NOT NULL REFERENCES trip_states(trip_id) ON DELETE CASCADE,
    from_node_id                TEXT NOT NULL REFERENCES trip_node(node_id) ON DELETE CASCADE,
    to_node_id                  TEXT NOT NULL REFERENCES trip_node(node_id) ON DELETE CASCADE,
    transport_mode              TEXT NULL,
    expected_duration_minutes   INTEGER NULL,
    observed_duration_minutes   INTEGER NULL,
    expected_cost_band          TEXT NULL,
    notes                       TEXT NULL,
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

-- Edge lookup by trip (compose itinerary order)
CREATE INDEX IF NOT EXISTS idx_trip_edge_trip
    ON trip_edge(trip_id);

-- Edge lookup by node (graph traversal)
CREATE INDEX IF NOT EXISTS idx_trip_edge_from_node
    ON trip_edge(from_node_id);
CREATE INDEX IF NOT EXISTS idx_trip_edge_to_node
    ON trip_edge(to_node_id);
