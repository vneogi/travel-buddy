-- =============================================================================
-- Migration: 0005_entity_ref_generalization.sql
-- Description: VISION §29 — generalize signal subject from venue-only to
--              (entity_type, entity_id). Additive only: no DROP, no RENAME.
--              Also creates venue_dish (§28 substrate) and adds trap_score
--              to venues_rag (§30 deferred column).
-- Depends on: 0002_signals_core.sql (signal table), 0001 (venues_rag table)
-- =============================================================================

-- =============================================================================
-- 1. Add entity_type + entity_id to signal table
-- =============================================================================
ALTER TABLE signal
    ADD COLUMN IF NOT EXISTS entity_type TEXT NOT NULL DEFAULT 'venue'
        CHECK (entity_type IN ('venue', 'dish', 'area', 'transit_leg')),
    ADD COLUMN IF NOT EXISTS entity_id TEXT;

-- Backfill: existing rows already have place_ref as the venue reference.
-- entity_type defaults to 'venue' (correct for all existing data).
-- entity_id = place_ref for existing venue-typed signals.
UPDATE signal SET entity_id = place_ref WHERE entity_id IS NULL AND place_ref IS NOT NULL;

-- Composite index for querying signals by subject
CREATE INDEX IF NOT EXISTS idx_signal_entity ON signal(entity_type, entity_id);

-- =============================================================================
-- 2. venue_dish — local food intelligence substrate (§28)
-- =============================================================================
CREATE TABLE IF NOT EXISTS venue_dish (
    dish_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    venue_id      UUID NOT NULL REFERENCES venues_rag(venue_id),
    name_local    TEXT NOT NULL,      -- name in native script (e.g. Lao, Thai, Arabic)
    name_roman    TEXT,               -- romanization for pronunciation
    name_en       TEXT,               -- English translation (may be NULL for local-only items)
    price_band    TEXT CHECK (price_band IN ('budget', 'mid', 'premium', 'splurge')),
    is_signature  BOOLEAN NOT NULL DEFAULT false,
    notes         TEXT,               -- e.g. "spicy", "shared plate", "seasonal"
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_venue_dish_venue ON venue_dish(venue_id);

-- =============================================================================
-- 3. trap_score on venue (§30 — deferred computation, column now)
-- =============================================================================
ALTER TABLE venues_rag
    ADD COLUMN IF NOT EXISTS trap_score NUMERIC;

-- NULL means "not yet computed". Post-Laos: populate from signal volume +
-- price delta + Google reviews sentiment. The column exists so data has
-- somewhere to land without a future migration.

-- =============================================================================
-- ROLLBACK (manual):
-- ALTER TABLE venues_rag DROP COLUMN IF EXISTS trap_score;
-- DROP INDEX IF EXISTS idx_venue_dish_venue;
-- DROP TABLE IF EXISTS venue_dish;
-- DROP INDEX IF EXISTS idx_signal_entity;
-- ALTER TABLE signal DROP COLUMN IF EXISTS entity_id;
-- ALTER TABLE signal DROP COLUMN IF EXISTS entity_type;
-- =============================================================================
