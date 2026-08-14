-- Migration 0018: Anonymous device identity (SPEC-09, server half).
--
-- Adds identity_kind column to user_tiers so the system can distinguish
-- anonymous device-generated identities from Supabase-authenticated users.
-- Default is 'unknown' because existing rows predate this concept and we
-- cannot assert what they are (compare 0015 names_local backfill lesson).

ALTER TABLE user_tiers
    ADD COLUMN IF NOT EXISTS identity_kind TEXT NOT NULL DEFAULT 'unknown'
    CHECK (identity_kind IN ('anonymous', 'supabase', 'unknown'));

COMMENT ON COLUMN user_tiers.identity_kind IS
    'How the user was identified: anonymous (device UUID v4), supabase (JWT-verified), or unknown (predates column). New rows written by the auth layer with the resolved kind.';
