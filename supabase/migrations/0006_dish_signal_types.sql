-- =============================================================================
-- Migration: 0006_dish_signal_types.sql
-- Description: Register dish-level signal types (§28/§29). Requires 0005
--              (entity_type generalization) to be meaningful at ingest.
-- Depends on: 0002_signals_core.sql (signal_type table)
-- =============================================================================

INSERT INTO signal_type (key, category, value_kind, enum_values, decay_policy, description) VALUES
    ('dish_loved', 'explicit_user', 'enum', ARRAY['loved'], 'exp_180d',
     'User loved a specific dish (requires entity_type=dish)'),
    ('dish_ordered', 'behavioral', 'boolean', NULL, 'none',
     'User ordered/consumed a dish (ground truth for food recommendations)')
ON CONFLICT (key) DO NOTHING;

-- =============================================================================
-- ROLLBACK (manual):
-- DELETE FROM signal_type WHERE key IN ('dish_loved', 'dish_ordered');
-- =============================================================================
