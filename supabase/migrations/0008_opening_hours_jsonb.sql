-- Migration 0008: opening_hours TEXT -> JSONB
-- Reason: TEXT '09:00-23:00' cannot express per-day variation, split hours
-- (many Asian restaurants close 14:00-17:00), or closed days. CSP scheduler
-- needs all three. Must be decided BEFORE curating Laos venues.
--
-- Shape (per venue):
-- {
--   "mon": [["09:00","14:00"],["17:00","22:00"]],  -- split hours
--   "tue": [["09:00","22:00"]],                     -- single span
--   "wed": [],                                       -- closed
--   "thu": [["09:00","22:00"]],
--   "fri": [["09:00","23:00"]],
--   "sat": [["10:00","23:00"]],
--   "sun": [["10:00","21:00"]]
-- }
--
-- Rules:
-- - Each day key maps to an array of [open, close] pairs (24h format)
-- - Empty array = closed that day
-- - Missing key = unknown (treat as open for scheduling, flag for curation)
-- - Multiple pairs = split hours (lunch break, etc.)

-- Step 1: Add new JSONB column with a permissive default
ALTER TABLE venues_rag
  ADD COLUMN IF NOT EXISTS opening_hours_structured JSONB DEFAULT NULL;

-- Step 2: Migrate existing TEXT data to JSONB (all-days same hours)
-- Assumes format 'HH:MM-HH:MM' in the existing TEXT column.
UPDATE venues_rag
SET opening_hours_structured = jsonb_build_object(
  'mon', jsonb_build_array(jsonb_build_array(
    split_part(opening_hours, '-', 1),
    split_part(opening_hours, '-', 2)
  )),
  'tue', jsonb_build_array(jsonb_build_array(
    split_part(opening_hours, '-', 1),
    split_part(opening_hours, '-', 2)
  )),
  'wed', jsonb_build_array(jsonb_build_array(
    split_part(opening_hours, '-', 1),
    split_part(opening_hours, '-', 2)
  )),
  'thu', jsonb_build_array(jsonb_build_array(
    split_part(opening_hours, '-', 1),
    split_part(opening_hours, '-', 2)
  )),
  'fri', jsonb_build_array(jsonb_build_array(
    split_part(opening_hours, '-', 1),
    split_part(opening_hours, '-', 2)
  )),
  'sat', jsonb_build_array(jsonb_build_array(
    split_part(opening_hours, '-', 1),
    split_part(opening_hours, '-', 2)
  )),
  'sun', jsonb_build_array(jsonb_build_array(
    split_part(opening_hours, '-', 1),
    split_part(opening_hours, '-', 2)
  ))
)
WHERE opening_hours IS NOT NULL
  AND opening_hours LIKE '%-%';

-- Step 3: Add geo_region column to venues_rag for multi-city filtering
ALTER TABLE venues_rag
  ADD COLUMN IF NOT EXISTS geo_region TEXT NOT NULL DEFAULT 'dubai_uae';

CREATE INDEX IF NOT EXISTS idx_venues_rag_geo_region
  ON venues_rag(geo_region);

-- Step 4: Add geo_region to trip_states (if trip_states exists)
-- This is stored in state_json so no schema change needed for the JSON field,
-- but we add a computed index for querying trips by region.

COMMENT ON COLUMN venues_rag.opening_hours_structured IS
  'Per-day hours as JSONB. Shape: {"mon": [["09:00","22:00"]], ...}. Empty array = closed.';
COMMENT ON COLUMN venues_rag.geo_region IS
  'Region code (e.g. dubai_uae, luang_prabang_laos). Filters venue search per-trip.';

-- ROLLBACK:
-- ALTER TABLE venues_rag DROP COLUMN IF EXISTS opening_hours_structured;
-- ALTER TABLE venues_rag DROP COLUMN IF EXISTS geo_region;
-- DROP INDEX IF EXISTS idx_venues_rag_geo_region;
