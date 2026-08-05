-- =============================================================================
-- Migration: 0002_signals_core.sql
-- Description: Core signal-capture tables for the data flywheel (SPEC-01 Part B).
--              Implements the minimal subset of DATA_MODEL_BRD §3: source registry,
--              signal_type taxonomy, and the universal signal fact table.
--              Seeds first_party source + user_loved signal type.
-- Depends on: 0001_initial_schema.sql
-- =============================================================================

-- =============================================================================
-- Table: source — the source registry
-- Purpose: Every signal references its source. Adding a new data provider is an
--          INSERT here, not a schema change. (DATA_MODEL_BRD §3.3)
-- =============================================================================
CREATE TABLE IF NOT EXISTS source (
    source_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key           TEXT UNIQUE NOT NULL,
    display_name  TEXT NOT NULL,
    source_type   TEXT NOT NULL,       -- first_party | third_party_api | third_party_scrape | derived
    trust_weight  FLOAT NOT NULL DEFAULT 1.0,
    legal_basis   TEXT NOT NULL,       -- 'user_consent' | 'official_api_tos' | 'licensed' | 'public_scrape_REVIEW'
    license_notes TEXT,
    active        BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Seed the first-party source (our app users)
INSERT INTO source (key, display_name, source_type, trust_weight, legal_basis)
VALUES ('first_party', 'First Party (app users)', 'first_party', 1.0, 'user_consent')
ON CONFLICT (key) DO NOTHING;

-- =============================================================================
-- Table: signal_type — the taxonomy registry (extensibility lever)
-- Purpose: Defining a new signal = INSERT a row here. No schema change.
--          (DATA_MODEL_BRD §3.5)
-- =============================================================================
CREATE TABLE IF NOT EXISTS signal_type (
    signal_type_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key            TEXT UNIQUE NOT NULL,
    category       TEXT NOT NULL,      -- explicit_user | behavioral | third_party_agg | derived
    value_kind     TEXT NOT NULL,      -- numeric | enum | json | boolean
    enum_values    TEXT[],
    decay_policy   TEXT NOT NULL DEFAULT 'none',
    description    TEXT,
    created_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Seed the first signal type: user_loved (the vertical-slice signal)
INSERT INTO signal_type (key, category, value_kind, enum_values, decay_policy, description)
VALUES ('user_loved', 'explicit_user', 'enum', ARRAY['loved'], 'exp_180d',
        'User explicitly loved a place (one-tap heart)')
ON CONFLICT (key) DO NOTHING;

-- =============================================================================
-- Table: signal — the universal fact table (DATA_MODEL_BRD §3.4)
-- Purpose: Every metric, from every source, is a row here. The heart of the
--          data asset. signal_id is CLIENT-GENERATED (idempotency key for
--          offline retry — SPEC-01 guiding rule #2).
-- =============================================================================
CREATE TABLE IF NOT EXISTS signal (
    signal_id      UUID PRIMARY KEY,            -- CLIENT-GENERATED (idempotency key)
    place_ref      TEXT,                        -- venue_id/name from itinerary (pre-entity-resolution)
    place_id       UUID,                        -- FK later, once place graph exists; nullable now
    source_id      UUID NOT NULL REFERENCES source(source_id),
    signal_type_id UUID NOT NULL REFERENCES signal_type(signal_type_id),
    user_id        TEXT,                        -- pseudonymous (Supabase sub or debug id)
    trip_id        TEXT,
    value_numeric  DOUBLE PRECISION,
    value_text     TEXT,
    value_json     JSONB,                       -- includes party_context (§16.5) later
    captured_at    TIMESTAMP WITH TIME ZONE NOT NULL,  -- when user acted (client clock)
    ingested_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    provenance     JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_signal_place_ref ON signal(place_ref);
CREATE INDEX IF NOT EXISTS idx_signal_type_time ON signal(signal_type_id, captured_at);
CREATE INDEX IF NOT EXISTS idx_signal_user ON signal(user_id);
CREATE INDEX IF NOT EXISTS idx_signal_trip ON signal(trip_id);

-- =============================================================================
-- ROLLBACK (manual):
-- DROP INDEX IF EXISTS idx_signal_trip;
-- DROP INDEX IF EXISTS idx_signal_user;
-- DROP INDEX IF EXISTS idx_signal_type_time;
-- DROP INDEX IF EXISTS idx_signal_place_ref;
-- DROP TABLE IF EXISTS signal;
-- DROP TABLE IF EXISTS signal_type;
-- DROP TABLE IF EXISTS source;
-- =============================================================================
