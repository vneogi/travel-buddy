-- =============================================================================
-- Migration: 0027_spec43_g4_tombstone.sql
-- Description: SPEC-43 Gap 4 -- durable erase tombstone.
--
--   One row per erased account, written by POST /api/v1/me/erase after the
--   row erase succeeds. After a backup restore, the restore re-erase reads
--   these ids and erases them again, so a restore cannot bring a deleted
--   traveller's rows back.
--
--   Holds the account id only: no name, email, trip or location data.
--   user_id is stored stripped and non-blank. source is a closed set
--   ('me_erase' only). config/data_rights.py classifies this table
--   erase_exempt: erase and export skip it, so erasing an account never
--   deletes its own tombstone.
--
--   Privileges follow 0026: ENABLE + FORCE RLS, REVOKE ALL from PUBLIC,
--   anon and authenticated, GRANT ALL to service_role. No policies are
--   created for anon or authenticated, so those roles cannot reach the
--   table at all. The FastAPI backend uses service_role (BYPASSRLS).
--
--   Additive only. Owner-gated apply: this file is not applied to the hosted
--   project by the execution agent. The owner applies it after review.
--
-- Depends on: 0026
-- =============================================================================

CREATE TABLE IF NOT EXISTS data_rights_tombstone (
    user_id text PRIMARY KEY CHECK (length(btrim(user_id)) > 0 AND user_id = btrim(user_id)),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    source text NOT NULL DEFAULT 'me_erase' CHECK (source IN ('me_erase'))
);

ALTER TABLE data_rights_tombstone ENABLE ROW LEVEL SECURITY;
ALTER TABLE data_rights_tombstone FORCE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE data_rights_tombstone FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE data_rights_tombstone TO service_role;
