-- =============================================================================
-- Migration: 0021_booking_anchors.sql
-- Description: Add booking metadata columns to trip_node (SPEC-10)
--              and register booking_added signal type.
-- Depends on: 0014_itinerary_normalisation.sql (trip_node table),
--             0002_signals_core.sql (signal_type table)
-- =============================================================================

-- Add booking anchor columns to trip_node (all nullable or defaulted)
ALTER TABLE trip_node
    ADD COLUMN IF NOT EXISTS node_kind TEXT NOT NULL DEFAULT 'activity',
    ADD COLUMN IF NOT EXISTS booking_type TEXT NULL,
    ADD COLUMN IF NOT EXISTS confirmation_code TEXT NULL,
    ADD COLUMN IF NOT EXISTS booking_notes TEXT NULL,
    ADD COLUMN IF NOT EXISTS import_source TEXT NULL;

-- Register booking_added signal type
INSERT INTO signal_type (key, category, value_kind, enum_values, decay_policy, description) VALUES
    ('booking_added', 'explicit_user', 'json', NULL, 'none',
     'Traveller recorded a booking anchor (flight, hotel, train, tour)')
ON CONFLICT (key) DO NOTHING;
