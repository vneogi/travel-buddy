-- =============================================================================
-- Migration: 0026_spec43_g2_rls.sql
-- Description: SPEC-43 Gap 2 -- close the PostgREST surface on personal rows.
--
--   Personal tables: ENABLE + FORCE RLS, REVOKE ALL from PUBLIC/anon/
--   authenticated, GRANT ALL to service_role, owner-only policies for
--   authenticated keyed on auth.uid(). Ownership of trip-scoped rows is
--   proven through trip_states.user_id, never through "a signal exists".
--
--   Catalog / reference tables: RLS enabled, SELECT-only for anon and
--   authenticated, no INSERT/UPDATE/DELETE for those roles.
--
--   The FastAPI backend keeps using service_role, which has BYPASSRLS and is
--   unaffected by FORCE RLS. Do not switch the API to the anon key.
--
--   Owner policies are defence in depth: with privileges revoked, anon and
--   authenticated cannot reach these tables at all. If a later slice grants
--   authenticated table privileges, the owner policies below are what bound
--   them. None of them use WITH CHECK (true).
--
--   cached_responses has no owner column (shared semantic cache). It gets
--   FORCE RLS and service_role only; no authenticated policy is created.
--
--   Additive only. 0007 is not edited; its signal-based party policies and
--   WITH CHECK (true) insert policies are dropped and replaced here.
--
-- Depends on: 0001, 0002, 0003, 0005, 0007, 0010, 0012, 0013, 0014, 0025
-- =============================================================================

-- =============================================================================
-- 1. Personal tables: ENABLE + FORCE RLS
-- =============================================================================
ALTER TABLE user_tiers ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_tiers FORCE ROW LEVEL SECURITY;

ALTER TABLE trip_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE trip_states FORCE ROW LEVEL SECURITY;

ALTER TABLE event_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_log FORCE ROW LEVEL SECURITY;

ALTER TABLE cached_responses ENABLE ROW LEVEL SECURITY;
ALTER TABLE cached_responses FORCE ROW LEVEL SECURITY;

ALTER TABLE trip_node ENABLE ROW LEVEL SECURITY;
ALTER TABLE trip_node FORCE ROW LEVEL SECURITY;

ALTER TABLE trip_edge ENABLE ROW LEVEL SECURITY;
ALTER TABLE trip_edge FORCE ROW LEVEL SECURITY;

ALTER TABLE trip_command ENABLE ROW LEVEL SECURITY;
ALTER TABLE trip_command FORCE ROW LEVEL SECURITY;

ALTER TABLE trip_party ENABLE ROW LEVEL SECURITY;
ALTER TABLE trip_party FORCE ROW LEVEL SECURITY;

ALTER TABLE party_member ENABLE ROW LEVEL SECURITY;
ALTER TABLE party_member FORCE ROW LEVEL SECURITY;

ALTER TABLE signal ENABLE ROW LEVEL SECURITY;
ALTER TABLE signal FORCE ROW LEVEL SECURITY;

-- =============================================================================
-- 2. Personal tables: privileges (service_role only)
-- =============================================================================
REVOKE ALL ON TABLE user_tiers FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE user_tiers TO service_role;

REVOKE ALL ON TABLE trip_states FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE trip_states TO service_role;

REVOKE ALL ON TABLE event_log FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE event_log TO service_role;

REVOKE ALL ON TABLE cached_responses FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE cached_responses TO service_role;

REVOKE ALL ON TABLE trip_node FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE trip_node TO service_role;

REVOKE ALL ON TABLE trip_edge FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE trip_edge TO service_role;

REVOKE ALL ON TABLE trip_command FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE trip_command TO service_role;

REVOKE ALL ON TABLE trip_party FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE trip_party TO service_role;

REVOKE ALL ON TABLE party_member FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE party_member TO service_role;

REVOKE ALL ON TABLE signal FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE signal TO service_role;

-- =============================================================================
-- 3. Owner policies: direct user_id ownership (UUID columns)
-- =============================================================================
DROP POLICY IF EXISTS user_tiers_select_own ON user_tiers;
CREATE POLICY user_tiers_select_own ON user_tiers
    FOR SELECT TO authenticated
    USING (user_id = auth.uid());

DROP POLICY IF EXISTS trip_states_select_own ON trip_states;
CREATE POLICY trip_states_select_own ON trip_states
    FOR SELECT TO authenticated
    USING (user_id = auth.uid());

DROP POLICY IF EXISTS trip_states_insert_own ON trip_states;
CREATE POLICY trip_states_insert_own ON trip_states
    FOR INSERT TO authenticated
    WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS event_log_select_own ON event_log;
CREATE POLICY event_log_select_own ON event_log
    FOR SELECT TO authenticated
    USING (user_id = auth.uid());

DROP POLICY IF EXISTS event_log_insert_own ON event_log;
CREATE POLICY event_log_insert_own ON event_log
    FOR INSERT TO authenticated
    WITH CHECK (user_id = auth.uid());

-- signal.user_id is TEXT. 0007 signal_select_own / signal_insert_own already
-- key on user_id = auth.uid()::text; they are kept unchanged.

-- cached_responses: no owner column. No authenticated policy (deny).

-- =============================================================================
-- 4. Owner policies: trip-scoped rows, owned via trip_states
-- =============================================================================
DROP POLICY IF EXISTS trip_node_select_own ON trip_node;
CREATE POLICY trip_node_select_own ON trip_node
    FOR SELECT TO authenticated
    USING (EXISTS (
        SELECT 1 FROM trip_states ts
         WHERE ts.trip_id = trip_node.trip_id
           AND ts.user_id = auth.uid()
    ));

DROP POLICY IF EXISTS trip_node_insert_own ON trip_node;
CREATE POLICY trip_node_insert_own ON trip_node
    FOR INSERT TO authenticated
    WITH CHECK (EXISTS (
        SELECT 1 FROM trip_states ts
         WHERE ts.trip_id = trip_node.trip_id
           AND ts.user_id = auth.uid()
    ));

DROP POLICY IF EXISTS trip_edge_select_own ON trip_edge;
CREATE POLICY trip_edge_select_own ON trip_edge
    FOR SELECT TO authenticated
    USING (EXISTS (
        SELECT 1 FROM trip_states ts
         WHERE ts.trip_id = trip_edge.trip_id
           AND ts.user_id = auth.uid()
    ));

DROP POLICY IF EXISTS trip_edge_insert_own ON trip_edge;
CREATE POLICY trip_edge_insert_own ON trip_edge
    FOR INSERT TO authenticated
    WITH CHECK (EXISTS (
        SELECT 1 FROM trip_states ts
         WHERE ts.trip_id = trip_edge.trip_id
           AND ts.user_id = auth.uid()
    ));

DROP POLICY IF EXISTS trip_command_select_own ON trip_command;
CREATE POLICY trip_command_select_own ON trip_command
    FOR SELECT TO authenticated
    USING (EXISTS (
        SELECT 1 FROM trip_states ts
         WHERE ts.trip_id = trip_command.trip_id
           AND ts.user_id = auth.uid()
    ));

-- trip_party.trip_id is TEXT; trip_states.trip_id is UUID.
-- Replaces 0007 signal-based select and WITH CHECK (true) insert.
DROP POLICY IF EXISTS trip_party_select_own ON trip_party;
CREATE POLICY trip_party_select_own ON trip_party
    FOR SELECT TO authenticated
    USING (EXISTS (
        SELECT 1 FROM trip_states ts
         WHERE ts.trip_id::text = trip_party.trip_id
           AND ts.user_id = auth.uid()
    ));

DROP POLICY IF EXISTS trip_party_insert_own ON trip_party;
CREATE POLICY trip_party_insert_own ON trip_party
    FOR INSERT TO authenticated
    WITH CHECK (EXISTS (
        SELECT 1 FROM trip_states ts
         WHERE ts.trip_id::text = trip_party.trip_id
           AND ts.user_id = auth.uid()
    ));

-- party_member: owned via trip_party then trip_states.
DROP POLICY IF EXISTS party_member_select_own ON party_member;
CREATE POLICY party_member_select_own ON party_member
    FOR SELECT TO authenticated
    USING (EXISTS (
        SELECT 1 FROM trip_party tp
          JOIN trip_states ts ON ts.trip_id::text = tp.trip_id
         WHERE tp.party_id = party_member.party_id
           AND ts.user_id = auth.uid()
    ));

DROP POLICY IF EXISTS party_member_insert_own ON party_member;
CREATE POLICY party_member_insert_own ON party_member
    FOR INSERT TO authenticated
    WITH CHECK (EXISTS (
        SELECT 1 FROM trip_party tp
          JOIN trip_states ts ON ts.trip_id::text = tp.trip_id
         WHERE tp.party_id = party_member.party_id
           AND ts.user_id = auth.uid()
    ));

-- =============================================================================
-- 5. Catalog / reference tables: SELECT-only for anon and authenticated
-- =============================================================================
ALTER TABLE venues_rag ENABLE ROW LEVEL SECURITY;
ALTER TABLE venue_dish ENABLE ROW LEVEL SECURITY;
ALTER TABLE signal_type ENABLE ROW LEVEL SECURITY;
ALTER TABLE source ENABLE ROW LEVEL SECURITY;
ALTER TABLE taxonomy_term ENABLE ROW LEVEL SECURITY;
ALTER TABLE dish_glossary ENABLE ROW LEVEL SECURITY;
ALTER TABLE venue_external_id ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE venues_rag FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE venues_rag TO anon, authenticated;
GRANT ALL ON TABLE venues_rag TO service_role;

REVOKE ALL ON TABLE venue_dish FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE venue_dish TO anon, authenticated;
GRANT ALL ON TABLE venue_dish TO service_role;

REVOKE ALL ON TABLE signal_type FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE signal_type TO anon, authenticated;
GRANT ALL ON TABLE signal_type TO service_role;

REVOKE ALL ON TABLE source FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE source TO anon, authenticated;
GRANT ALL ON TABLE source TO service_role;

REVOKE ALL ON TABLE taxonomy_term FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE taxonomy_term TO anon, authenticated;
GRANT ALL ON TABLE taxonomy_term TO service_role;

REVOKE ALL ON TABLE dish_glossary FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE dish_glossary TO anon, authenticated;
GRANT ALL ON TABLE dish_glossary TO service_role;

REVOKE ALL ON TABLE venue_external_id FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE venue_external_id TO anon, authenticated;
GRANT ALL ON TABLE venue_external_id TO service_role;

-- Replace 0007 authenticated-only read policies with anon + authenticated.
DROP POLICY IF EXISTS venues_rag_read ON venues_rag;
DROP POLICY IF EXISTS venue_dish_read ON venue_dish;
DROP POLICY IF EXISTS signal_type_read ON signal_type;
DROP POLICY IF EXISTS source_read ON source;

DROP POLICY IF EXISTS venues_rag_select_catalog ON venues_rag;
CREATE POLICY venues_rag_select_catalog ON venues_rag
    FOR SELECT TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS venue_dish_select_catalog ON venue_dish;
CREATE POLICY venue_dish_select_catalog ON venue_dish
    FOR SELECT TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS signal_type_select_catalog ON signal_type;
CREATE POLICY signal_type_select_catalog ON signal_type
    FOR SELECT TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS source_select_catalog ON source;
CREATE POLICY source_select_catalog ON source
    FOR SELECT TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS taxonomy_term_select_catalog ON taxonomy_term;
CREATE POLICY taxonomy_term_select_catalog ON taxonomy_term
    FOR SELECT TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS dish_glossary_select_catalog ON dish_glossary;
CREATE POLICY dish_glossary_select_catalog ON dish_glossary
    FOR SELECT TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS venue_external_id_select_catalog ON venue_external_id;
CREATE POLICY venue_external_id_select_catalog ON venue_external_id
    FOR SELECT TO anon, authenticated
    USING (true);

-- =============================================================================
-- ROLLBACK (manual):
-- Re-create 0007 policies (signal_type_read, source_read, venue_dish_read,
-- venues_rag_read, trip_party_select_own, trip_party_insert_own,
-- party_member_select_own, party_member_insert_own) from 0007 if needed.
-- DROP POLICY IF EXISTS user_tiers_select_own ON user_tiers;
-- DROP POLICY IF EXISTS trip_states_select_own ON trip_states;
-- DROP POLICY IF EXISTS trip_states_insert_own ON trip_states;
-- DROP POLICY IF EXISTS event_log_select_own ON event_log;
-- DROP POLICY IF EXISTS event_log_insert_own ON event_log;
-- DROP POLICY IF EXISTS trip_node_select_own ON trip_node;
-- DROP POLICY IF EXISTS trip_node_insert_own ON trip_node;
-- DROP POLICY IF EXISTS trip_edge_select_own ON trip_edge;
-- DROP POLICY IF EXISTS trip_edge_insert_own ON trip_edge;
-- DROP POLICY IF EXISTS trip_command_select_own ON trip_command;
-- DROP POLICY IF EXISTS venues_rag_select_catalog ON venues_rag;
-- DROP POLICY IF EXISTS venue_dish_select_catalog ON venue_dish;
-- DROP POLICY IF EXISTS signal_type_select_catalog ON signal_type;
-- DROP POLICY IF EXISTS source_select_catalog ON source;
-- DROP POLICY IF EXISTS taxonomy_term_select_catalog ON taxonomy_term;
-- DROP POLICY IF EXISTS dish_glossary_select_catalog ON dish_glossary;
-- DROP POLICY IF EXISTS venue_external_id_select_catalog ON venue_external_id;
-- ALTER TABLE <personal table> NO FORCE ROW LEVEL SECURITY;
-- (Grants: restore per-environment defaults; do not GRANT ALL to anon.)
-- =============================================================================
