-- Migration 0011: venues_rag missing columns
-- Purpose: Close the schema drift between scripts/load_venues.py and the
--          migration-defined DDL.  The loader writes these columns, and the
--          live database already has them -- likely added by hand via the
--          Supabase dashboard, since PostgREST rejects writes to columns
--          absent from its schema cache.  The exact origin is unknown; the
--          live schema should be dumped and diffed against the migration set
--          before this file is applied.
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

-- has_aircon: whether the venue has air conditioning.  Used with indoor_outdoor
-- to identify cooled-indoor reroute options during heat fatigue (Laos Oct).
ALTER TABLE venues_rag
  ADD COLUMN IF NOT EXISTS has_aircon BOOLEAN DEFAULT NULL;

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

ALTER TABLE venues_rag
  ADD COLUMN IF NOT EXISTS nearest_landmark_local TEXT DEFAULT NULL;

-- wheelchair_notes is the sole evidence behind the mobility_limited audience
-- flag.  Without this column the reroute feature for wheelchair users is
-- ungrounded.
ALTER TABLE venues_rag
  ADD COLUMN IF NOT EXISTS wheelchair_notes TEXT DEFAULT NULL;
