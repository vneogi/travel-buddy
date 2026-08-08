-- =============================================================================
-- Migration: 0004_behavioral_signal_types.sql
-- Description: SPEC-06 — register behavioral signal types. Must stay in sync
--              with models/signal_types.py. tests/test_signal_types.py enforces
--              this (drift = CI failure). See docs/ENGINEERING_RULES.md R5.
-- Depends on: 0002_signals_core.sql (creates signal_type table + user_loved)
-- =============================================================================

INSERT INTO signal_type (key, category, value_kind, enum_values, decay_policy, description) VALUES
    ('reroute_accepted', 'behavioral', 'json', NULL, 'none',
     'User accepted a suggested replacement activity'),
    ('reroute_rejected', 'behavioral', 'json', NULL, 'none',
     'User opened swap suggestions and declined all'),
    ('visited_confirmed', 'behavioral', 'boolean', NULL, 'none',
     'User confirmed they visited a planned node'),
    ('node_skipped', 'behavioral', 'json',
     ARRAY['too_far', 'too_tired', 'closed', 'crowded', 'not_interested', 'ran_out_of_time', 'weather'],
     'none',
     'User skipped a planned node — reason from closed enum'),
    ('arrival_delta', 'behavioral', 'numeric', NULL, 'none',
     'Minutes between planned and actual arrival (server-derived)')
ON CONFLICT (key) DO NOTHING;

-- =============================================================================
-- ROLLBACK (manual):
-- DELETE FROM signal_type WHERE key IN (
--     'reroute_accepted', 'reroute_rejected', 'visited_confirmed',
--     'node_skipped', 'arrival_delta'
-- );
-- =============================================================================
