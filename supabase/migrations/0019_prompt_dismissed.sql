-- =============================================================================
-- Migration: 0019_prompt_dismissed.sql
-- Description: Register prompt_dismissed signal type (SPEC-22 decision 9).
--              Dismissal is data -- the client emits this when an ask/defer
--              FactView is dismissed so analytics can measure interruption
--              fatigue and tune the budget.
-- Depends on: 0002_signals_core.sql (signal_type table)
-- =============================================================================

INSERT INTO signal_type (key, category, value_kind, enum_values, decay_policy, description) VALUES
    ('prompt_dismissed', 'explicit_user', 'json', NULL, 'exp_180d',
     'User dismissed an interruptive fact prompt (ask/defer FactView)')
ON CONFLICT (key) DO NOTHING;

-- =============================================================================
-- ROLLBACK (manual):
-- DELETE FROM signal_type WHERE key = 'prompt_dismissed';
-- =============================================================================
