-- =============================================================================
-- Migration: 0022_trip_node_local_names.sql
-- Description: Add local script and landmark columns to trip_node (SPEC-12)
-- Depends on: 0014_itinerary_normalisation.sql (trip_node table)
-- =============================================================================

ALTER TABLE trip_node
    ADD COLUMN IF NOT EXISTS names_local JSONB DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS landmarks_local JSONB DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS nearest_landmark TEXT DEFAULT NULL;
