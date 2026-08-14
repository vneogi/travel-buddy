-- Migration 0018: Anonymous device identity (SPEC-09, server half).
--
-- Adds identity_kind column to user_tiers so the system can distinguish
-- anonymous device-generated identities from Supabase-authenticated users.

ALTER TABLE user_tiers
    ADD COLUMN IF NOT EXISTS identity_kind TEXT NOT NULL DEFAULT 'anonymous'
    CHECK (identity_kind IN ('anonymous', 'supabase'));

COMMENT ON COLUMN user_tiers.identity_kind IS
    'How the user was identified: anonymous (device UUID v4) or supabase (JWT-verified). Default anonymous for existing rows.';
