-- =============================================================================
-- Migration: 0007_enable_rls.sql
-- Description: Enable Row Level Security on all tables created by 0002-0006,
--              plus venues_rag (created by 0001 without RLS).
--
--              The backend uses the service_role key, which BYPASSES RLS entirely.
--              These policies protect against direct access with the anon/publishable
--              key (e.g., from the Flutter app or a leaked key).
--
-- IMPORTANT: service_role bypasses RLS. Do NOT "fix" this by switching the backend
--            to use the anon key — that would break all writes.
--
-- Depends on: 0001 (venues_rag), 0002 (source, signal_type, signal),
--             0003 (trip_party, party_member), 0005 (venue_dish)
-- =============================================================================

-- =============================================================================
-- 1. Enable RLS on all tables
-- =============================================================================
ALTER TABLE signal ENABLE ROW LEVEL SECURITY;
ALTER TABLE source ENABLE ROW LEVEL SECURITY;
ALTER TABLE signal_type ENABLE ROW LEVEL SECURITY;
ALTER TABLE trip_party ENABLE ROW LEVEL SECURITY;
ALTER TABLE party_member ENABLE ROW LEVEL SECURITY;
ALTER TABLE venue_dish ENABLE ROW LEVEL SECURITY;
ALTER TABLE venues_rag ENABLE ROW LEVEL SECURITY;

-- =============================================================================
-- 2. signal — users may only access their own signals
-- =============================================================================
CREATE POLICY signal_select_own ON signal
    FOR SELECT TO authenticated
    USING (user_id = auth.uid()::text);

CREATE POLICY signal_insert_own ON signal
    FOR INSERT TO authenticated
    WITH CHECK (user_id = auth.uid()::text);

-- =============================================================================
-- 3. trip_party / party_member — scoped to owning user via trip ownership
--    trip_party.trip_id links to the user's trips (trip ownership is validated
--    at the application layer; RLS ensures row-level isolation).
-- =============================================================================
CREATE POLICY trip_party_select_own ON trip_party
    FOR SELECT TO authenticated
    USING (trip_id IN (
        SELECT trip_id FROM signal WHERE user_id = auth.uid()::text
    ));

CREATE POLICY trip_party_insert_own ON trip_party
    FOR INSERT TO authenticated
    WITH CHECK (true);  -- service_role handles party creation; this is a fallback

CREATE POLICY party_member_select_own ON party_member
    FOR SELECT TO authenticated
    USING (party_id IN (
        SELECT party_id FROM trip_party
        WHERE trip_id IN (SELECT trip_id FROM signal WHERE user_id = auth.uid()::text)
    ));

CREATE POLICY party_member_insert_own ON party_member
    FOR INSERT TO authenticated
    WITH CHECK (true);  -- service_role handles; fallback only

-- =============================================================================
-- 4. signal_type / source — read-only reference data
-- =============================================================================
CREATE POLICY signal_type_read ON signal_type
    FOR SELECT TO authenticated
    USING (true);

CREATE POLICY source_read ON source
    FOR SELECT TO authenticated
    USING (true);

-- =============================================================================
-- 5. venue_dish — read-only to authenticated; writes via service_role only
-- =============================================================================
CREATE POLICY venue_dish_read ON venue_dish
    FOR SELECT TO authenticated
    USING (true);

-- =============================================================================
-- 6. venues_rag — read-only to authenticated (0001 didn't enable RLS)
-- =============================================================================
CREATE POLICY venues_rag_read ON venues_rag
    FOR SELECT TO authenticated
    USING (true);

-- =============================================================================
-- ROLLBACK (manual):
-- DROP POLICY IF EXISTS signal_select_own ON signal;
-- DROP POLICY IF EXISTS signal_insert_own ON signal;
-- DROP POLICY IF EXISTS trip_party_select_own ON trip_party;
-- DROP POLICY IF EXISTS trip_party_insert_own ON trip_party;
-- DROP POLICY IF EXISTS party_member_select_own ON party_member;
-- DROP POLICY IF EXISTS party_member_insert_own ON party_member;
-- DROP POLICY IF EXISTS signal_type_read ON signal_type;
-- DROP POLICY IF EXISTS source_read ON source;
-- DROP POLICY IF EXISTS venue_dish_read ON venue_dish;
-- DROP POLICY IF EXISTS venues_rag_read ON venues_rag;
-- ALTER TABLE signal DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE source DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE signal_type DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE trip_party DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE party_member DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE venue_dish DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE venues_rag DISABLE ROW LEVEL SECURITY;
-- =============================================================================
