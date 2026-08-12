-- Migration 0011: venues_rag missing columns
-- Purpose: Close the schema drift between scripts/load_venues.py and the
--          migration-defined DDL.  The loader already writes these columns,
--          and the live database accepted them (Supabase allows writes to
--          undefined columns via the REST API), but a fresh database built
--          from 0001 upward would reject the load.
--
-- CHECK constraints are intentionally deferred.  The vocabulary sets in
-- load_venues.py are mid-repair (task G3), and no one can inspect the
-- value distribution in the live table until the test laptop returns
-- (~Aug 17).  Adding a CHECK now would be a guess that either fails on
-- apply or silently locks in the wrong vocabulary.
--
-- Depends on: 0001 (venues_rag table)

-- =============================================================================
-- Section 1: Drift repair
-- These columns are already written by load_venues.py (lines 365-367 and
-- 386-388).  Without this migration a database rebuilt from scratch rejects
-- the loader.
-- =============================================================================

ALTER TABLE venues_rag
  ADD COLUMN IF NOT EXISTS typical_dwell_minutes INTEGER DEFAULT NULL;

ALTER TABLE venues_rag
  ADD COLUMN IF NOT EXISTS indoor_outdoor TEXT DEFAULT NULL;

ALTER TABLE venues_rag
  ADD COLUMN IF NOT EXISTS price_band TEXT DEFAULT NULL;

-- =============================================================================
-- Section 2: SPEC-12 groundwork (show-driver-cards)
-- These columns carry curated data in the venue JSONs.  G3b adds the writer
-- so they are no longer silently dropped on load.
--
-- Note: micro_location is intentionally absent here -- it is defined in 0001
-- (TEXT NOT NULL) and has been written by the loader since day one.
-- =============================================================================

ALTER TABLE venues_rag
  ADD COLUMN IF NOT EXISTS name_local TEXT DEFAULT NULL;

ALTER TABLE venues_rag
  ADD COLUMN IF NOT EXISTS nearest_landmark TEXT DEFAULT NULL;

ALTER TABLE venues_rag
  ADD COLUMN IF NOT EXISTS nearest_landmark_local TEXT DEFAULT NULL;

-- wheelchair_notes: free-text description of accessibility (ramps, steps,
-- narrow doorways, etc).  This is the only concrete evidence behind the
-- mobility_limited audience flag, which is set on ~2/3 of venues and
-- currently useless as a discriminator because the notes field has never
-- been persisted.
ALTER TABLE venues_rag
  ADD COLUMN IF NOT EXISTS wheelchair_notes TEXT DEFAULT NULL;
