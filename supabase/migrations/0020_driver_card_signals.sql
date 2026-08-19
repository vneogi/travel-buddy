-- =============================================================================
-- Migration: 0020_driver_card_signals.sql
-- Description: Register driver_card_shown and name_confirmed signal types
--              (SPEC-12 decisions 10 and 11).
-- Depends on: 0002_signals_core.sql (signal_type table)
-- =============================================================================

INSERT INTO signal_type (key, category, value_kind, enum_values, decay_policy, description) VALUES
    ('driver_card_shown', 'behavioral', 'json', NULL, 'none',
     'Traveller opened a driver card for a venue (offline or online)'),
    ('name_confirmed', 'explicit_user', 'json', NULL, 'none',
     'Traveller verified or rejected local-script venue signage (verdict=confirmed|rejected)')
ON CONFLICT (key) DO NOTHING;
