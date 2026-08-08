-- =============================================================================
-- Migration: 0003_trip_party.sql
-- Description: SPEC-03 party context tables. The application code
--              (signal_router.py) already stamps party_context at ingest;
--              these tables were never created. Completes SPEC-03.
-- Depends on: 0002_signals_core.sql
-- =============================================================================

-- =============================================================================
-- Table: trip_party — one row per trip, stores party metadata
-- Purpose: Links a trip to its party composition. party_context is frozen
--          onto each signal at ingest time — this table is the source.
-- =============================================================================
CREATE TABLE IF NOT EXISTS trip_party (
    party_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id     TEXT NOT NULL UNIQUE,
    party_type  TEXT NOT NULL,       -- solo|couple|friends|family_young_kids|family_teens|
                                     -- multigen|daddy_kiddo|accessibility_focused|mixed
    size        INTEGER NOT NULL DEFAULT 1,
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- Table: party_member — individual members of a trip party
-- Purpose: Per-member metadata for audience segmentation. Uses age_band
--          only — NEVER a child's birth date or name (DATA_MODEL §16.7).
-- =============================================================================
CREATE TABLE IF NOT EXISTS party_member (
    member_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    party_id    UUID NOT NULL REFERENCES trip_party(party_id) ON DELETE CASCADE,
    role        TEXT NOT NULL,       -- self|partner|child|teen|parent|friend
    age_band    TEXT NOT NULL,       -- infant|toddler|child|teen|adult|senior
    needs       TEXT[] DEFAULT '{}', -- nap_schedule|stroller|dietary:*|low_stamina
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_party_member_party ON party_member(party_id);

-- =============================================================================
-- ROLLBACK (manual):
-- DROP INDEX IF EXISTS idx_party_member_party;
-- DROP TABLE IF EXISTS party_member;
-- DROP TABLE IF EXISTS trip_party;
-- =============================================================================
