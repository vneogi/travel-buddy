-- =============================================================================
-- pg_bootstrap.sql
-- Ephemeral PostgreSQL bootstrap for SPEC-44 transaction proofs.
--
-- Creates the Supabase-compatible roles and auth schema stubs that the
-- production migrations (0001-0025) expect. Run once per ephemeral
-- database BEFORE applying supabase/migrations/*.sql.
-- =============================================================================

-- Roles that Supabase creates automatically but vanilla Postgres lacks.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role NOLOGIN;
    END IF;
END
$$;

-- Grant service_role the ability to SET session variables (for JWT stubs).
GRANT ALL ON SCHEMA public TO service_role;

-- Supabase auth schema stub: only auth.uid() is referenced by RLS policies.
CREATE SCHEMA IF NOT EXISTS auth;
CREATE OR REPLACE FUNCTION auth.uid()
RETURNS UUID
LANGUAGE sql STABLE
AS $$ SELECT COALESCE(
    NULLIF(current_setting('request.jwt.claim.sub', true), ''),
    '00000000-0000-0000-0000-000000000000'
)::UUID; $$;
