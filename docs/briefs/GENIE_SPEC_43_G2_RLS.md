# Genie brief: SPEC-43 Gap 2 -- RLS and public grants

Landed on `main` as `0b8125f` (PR #80). Do not re-implement this slice.
Gap 12 navigation privacy landed through `f486079`. Gap 9 closed
schemas `fb72545`. Next:
`docs/briefs/GENIE_SPEC_43_G5_SQLCIPHER.md`.
Do not apply 0026 on hosted until `rolbypassrls` is true for `postgres`
and `service_role`.

## Goal

Stop PostgREST (anon / authenticated JWT) from reading or mutating another
identity's personal rows.

Migration 0007 enabled RLS on seven tables and left core personal tables
open. Party insert policies use `WITH CHECK (true)`. Catalog tables may
stay readable. The FastAPI backend keeps using `service_role`, which
bypasses RLS -- do not switch the API to the anon key.

This is SPEC-43 Gap 2 only. It is not Gap 1 (already on main), Gap 6
(already on main), Gap 9 (signal ownership in FastAPI), Gap 5, Gap 11,
hosted two-JWT proof on the live project (owner SQL after merge),
deploy, or an APK.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 2)
- `supabase/migrations/0007_enable_rls.sql`
- `supabase/migrations/0001_initial_schema.sql`
- `supabase/migrations/0014_itinerary_normalisation.sql`
- `supabase/migrations/0025_trip_command_integrity.sql`
- `docs/ENGINEERING_RULES.md`
- `docs/WAYS_OF_WORKING.md`

Base branch: latest `main`, including Gap 6 `c65261c` (PR #79).

Create and push:

`feat/spec43-g2-rls`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Anyone with the publishable anon key can hit PostgREST. Without FORCE RLS
and owner policies, `trip_states`, `trip_node`, `event_log`, and friends
are world-readable. 0007's `trip_party_insert_own` / `party_member_insert_own`
`WITH CHECK (true)` is an insert hole even on tables that have RLS.

The app's FastAPI path is unchanged: it still uses service_role. This
slice closes the PostgREST surface.

## Scope

### 1. One new migration

Next number after 0025: `0026_spec43_g2_rls.sql`.

Do not edit 0007 in place. Additive SQL only.

Personal tables (FORCE RLS + no anon/authenticated DML except owner
policies below):

- `user_tiers`
- `trip_states`
- `event_log`
- `cached_responses`
- `trip_node`
- `trip_edge`
- `trip_command` (0025)
- `trip_party`
- `party_member`
- `signal` (already RLS; keep owner policies, drop nothing needed)

For each personal table:

1. `ALTER TABLE ... ENABLE ROW LEVEL SECURITY;`
2. `ALTER TABLE ... FORCE ROW LEVEL SECURITY;`
3. `REVOKE ALL ON TABLE ... FROM PUBLIC, anon, authenticated;`
4. `GRANT ALL ON TABLE ... TO service_role;`
5. Owner policies for `authenticated` only, keyed on `auth.uid()`, never
   `WITH CHECK (true)`.

Ownership keys (use the real column names in each table):

- `user_tiers`, `trip_states`, `event_log`, `cached_responses`, `signal`:
  `user_id = auth.uid()::text` (or uuid if the column is uuid -- match
  the schema, do not guess).
- `trip_node`, `trip_edge`, `trip_command`, `trip_party`: trip is owned
  when `trip_states.user_id = auth.uid()::text` for that `trip_id`.
  Do not use "a signal exists for this trip" as ownership (0007 did;
  replace party policies).
- `party_member`: via `trip_party` then `trip_states`.

Replace 0007 party insert policies: `DROP POLICY IF EXISTS
trip_party_insert_own` and `party_member_insert_own`, then recreate with
the trip_states ownership check.

Catalog / reference tables stay readable by `authenticated` and `anon`
SELECT only: `venues_rag`, `venue_dish`, `signal_type`, `source`,
`taxonomy_term`, `dish_glossary`, `venue_external_id`. No INSERT/UPDATE/
DELETE for those roles. ENABLE RLS if missing; SELECT policy `USING
(true)` is OK here.

If a later migration added another personal table, include it. Parse
`supabase/migrations/*.sql` for `CREATE TABLE`. When unsure, treat it as
personal (deny) not catalog (allow).

Do not drop the database. Do not rewrite FastAPI. Do not put the
service_role key in Flutter.

### 2. Tests (Python, no Flutter)

`tests/test_spec43_g2_rls.py`.

Parse `0026_spec43_g2_rls.sql` as text (no live Postgres required).
Must include:

- every personal table listed above appears with `ENABLE ROW LEVEL
  SECURITY` and `FORCE ROW LEVEL SECURITY`
- no `WITH CHECK (true)` remains on `trip_party` or `party_member`
- `REVOKE` of `anon` and `authenticated` appears for each personal table
- `GRANT` to `service_role` appears for each personal table
- catalog tables are not granted INSERT to `anon`

Named R17 test:
`test_trip_states_force_rls_is_present_in_0026`

Do not add a hosted two-JWT PostgREST client in this PR. That proof is
owner SQL after merge. Do not mark postgres-proof CI as in-scope.

### 3. R17 sabotage

1. Temporarily delete the `FORCE ROW LEVEL SECURITY` line for
   `trip_states` from 0026.
2. Run the named test `test_trip_states_force_rls_is_present_in_0026`.
3. Confirm that exact test fails.
4. Restore.
5. Re-run the focused file green.

Report the test name that failed. A generally red file is not proof.

## Non-goals

- switching FastAPI off service_role
- Gap 9 FastAPI signal ownership
- Gap 5 SQLCipher
- Gap 11 IP / account-creation limits
- minting two hosted JWTs / live PostgREST (owner after merge)
- fixing `postgres-proof` apt baseline
- hosted deploy, Cloud Run env, APK
- Flutter
- production LLM

## Gates

```bash
ruff check .
ruff format --check .
pytest -q -ra --strict-markers
pytest -q tests/test_spec43_g2_rls.py
git diff --check
```

No Flutter in this slice.

If you add a CREATE TABLE (you should not), grant `service_role` only.
