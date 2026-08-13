-- Migration 0011: venues_rag missing columns
-- Purpose: Close the schema drift between scripts/load_venues.py and the
--          migration-defined DDL.  The loader writes these columns, and the
--          live database already has them -- likely added by hand via the
--          Supabase dashboard, since PostgREST rejects writes to columns
--          absent from its schema cache.  The exact origin is unknown.
--
-- PREREQUISITE: Dump the live schema and diff it against the migration set
-- BEFORE applying this file.  If a hand-made name_local TEXT column already
-- exists, ADD COLUMN IF NOT EXISTS names_local JSONB adds a second empty
-- column and silently leaves the populated one unread.  The backfill that
-- migrates name_local -> names_local can only be written after the dump
-- reveals what actually exists.
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
-- These columns are already written by load_venues.py.  Without this migration
-- a database rebuilt from scratch rejects the loader.
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
-- Language-keyed JSONB for localized names and landmarks, per SPEC-12
-- design decisions 1 and 2.  nearest_landmark stays TEXT because it is the
-- English landmark for the traveller, not a localization.
-- =============================================================================

-- names_local: JSONB keyed by BCP-47 language tag.
-- Shape: {"lo": {"value": "<Lao script>", "source": "generated"}}
-- source vocabulary: wikidata, osm, official, manual, generated
ALTER TABLE venues_rag
  ADD COLUMN IF NOT EXISTS names_local JSONB DEFAULT NULL;

ALTER TABLE venues_rag
  ADD COLUMN IF NOT EXISTS nearest_landmark TEXT DEFAULT NULL;

-- landmarks_local: same shape as names_local, for localized landmark text.
-- The English landmark (nearest_landmark TEXT) is what the traveller reads;
-- landmarks_local holds the same landmark in local script for the driver.
ALTER TABLE venues_rag
  ADD COLUMN IF NOT EXISTS landmarks_local JSONB DEFAULT NULL;

-- wheelchair_notes is the sole evidence behind the mobility_limited audience
-- flag.  Without this column the reroute feature for wheelchair users is
-- ungrounded.
ALTER TABLE venues_rag
  ADD COLUMN IF NOT EXISTS wheelchair_notes TEXT DEFAULT NULL;
