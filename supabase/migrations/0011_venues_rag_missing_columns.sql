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
-- No writer exists yet.  Added now because this migration is applied by hand
-- and Lao-script venue curation is the longest-lead item remaining before
-- the Oct 2 field test.  When a writer lands (G3 or later), it will target
-- these columns.
-- =============================================================================

ALTER TABLE venues_rag
  ADD COLUMN IF NOT EXISTS name_local TEXT DEFAULT NULL;

ALTER TABLE venues_rag
  ADD COLUMN IF NOT EXISTS nearest_landmark TEXT DEFAULT NULL;
