# Genie brief: SPEC-43 Gap 4 slice 5 -- Supabase erase backend (fake client only)

This is the open job. Roles, hard stops, and R17 ritual are in
`docs/briefs/GENIE_SPEC_43_G10_IAM_A.md`. Do not re-read all of
SPEC-43 or SPEC-27.

## Goal

Slices 1-4 are on main: inventory, ordered plan, `execute_erase`,
and an in-memory wipe proof (`7ceab2e`, PR #176). Slice 5 adds the
backend the hosted app would use: `SupabaseEraseBackend`, which
implements the three `EraseBackend` methods through the PostgREST
client already used by `services/supabase_service.py`
(`client.table(t).select(...)/.delete().eq(...)/.in_(...).execute()`).

The client is injected. Tests use a fake client that stores rows
and evaluates filters. Nothing is wired to a route, `db_provider`,
or the hosted project. No live Supabase. No network.

The one safety property that matters most: **a delete is never
executed without a row filter.** A filterless PostgREST delete
on `trip_node` would erase every traveller's itinerary.

## Base

Latest `main` (`7ceab2e`), including Gap 4 slice 4 (PR #176).

Create and push: `feat/spec43-g4-erase-supabase`

Do not merge. Open one PR after gates are green.

## Read before editing

- `docs/ENGINEERING_RULES.md` (R14, R17)
- `services/data_rights_erase.py` (`ERASE_STEPS`, `EraseBackend`,
  `execute_erase`)
- `services/data_rights_erase_memory.py` (join rules to mirror;
  method/table mismatch check)
- `services/supabase_service.py` (client call shape only: see
  `save_trip_nodes`, `clear_expired_cache`, the `.in_(` use)
- `tests/test_spec43_g4_erase_memory.py` and the other Gap 4
  tests (must stay green)

No new migration. No Flutter. No router. No change to
`db_provider.py` or `supabase_service.py`. Do not import the
`supabase` package in the new module (the client is injected).
Do not import litellm, httpx, psycopg, or psycopg2.

## Scope

### 1. Module `services/data_rights_erase_supabase.py`

Stdlib + `services.data_rights_erase` only. ASCII only. No logging,
no print.

`SupabaseEraseBackend(client)`:

- `delete_where_user_id(user_id, table)`:
  `client.table(table).delete().eq("user_id", str(user_id)).execute()`.
  Return `len(result.data or [])`.
- `delete_via_trip_states(user_id, table)`:
  1. `owned = select("trip_id")` from `trip_states` with
     `.eq("user_id", str(user_id))`; collect `str(trip_id)`.
  2. If `owned` is empty: issue **no** delete; return 0.
  3. Else `client.table(table).delete().in_("trip_id", sorted(owned)).execute()`.
- `delete_via_party(user_id, table)`:
  1. Owned trip ids as above. If empty: no further calls; return 0.
  2. `party_ids = select("party_id")` from `trip_party` with
     `.in_("trip_id", sorted(owned))`. If empty: no delete; return 0.
  3. `client.table(table).delete().in_("party_id", sorted(party_ids)).execute()`.
- Each delete method only accepts tables whose `ERASE_STEPS` method
  is that method (same `ValueError` rule as the in-memory backend).
  Tables outside `ERASE_REQUIRED` raise `ValueError` before any
  client call.
- Compare and send ids as `str` (`trip_party.trip_id` is text,
  `trip_states.trip_id` is uuid; 0026 compares as text).

Do not add pagination, batching, retries, or RPC calls this slice.
Do not wire this backend into any route or provider.

### 2. Named tests

New file `tests/test_spec43_g4_erase_supabase.py`. No network.

Build a small fake client in the test file:
`table(name)` returns a query builder; `select(cols)`, `delete()`,
`eq(col, val)`, `in_(col, vals)`, `execute()`. It stores rows per
table, applies filters on `execute()`, returns an object with
`.data` (matching rows; deleted rows for delete), and records every
executed op as `(table, op, filters)`. A delete with zero filters
must still execute in the fake (that is what lets the sabotage be
caught) -- it removes every row in that table.

Seed users A and B across all nine `ERASE_REQUIRED` tables (two
trips each, parties and members), in the same shape as the memory
tests.

Exact names:

- `test_supabase_erase_never_deletes_without_a_filter`
  Run `execute_erase(A, SupabaseEraseBackend(fake))`. Every recorded
  delete op has at least one filter.
- `test_supabase_backend_wipes_target_and_keeps_other_user`
  After the erase, no A-owned row remains in any table (count by a
  test-only owner tag); B's per-table counts are unchanged.
- `test_supabase_erase_skips_delete_when_user_has_no_trips`
  A user with only a `user_tiers` row: via-trip and via-party
  methods issue no delete ops; `execute_erase` still succeeds.
- `test_supabase_erase_scopes_via_tables_to_owned_trip_ids`
  The delete on `trip_node` carries an `in_("trip_id", ...)` filter
  whose values are exactly A's trip ids as strings.
- `test_supabase_erase_party_member_scoped_via_trip_party`
- `test_supabase_erase_rows_affected_match_deleted_rows`
  `execute_erase` results' `rows` per table equal the A-owned row
  counts seeded for that table.
- `test_supabase_erase_rejects_mismatched_or_catalog_table`
  e.g. `delete_via_trip_states(A, "trip_states")`,
  `delete_where_user_id(A, "venues_rag")`,
  `delete_where_user_id(A, "cached_responses")` raise `ValueError`
  with zero client ops recorded.

Also assert in one test that the module does not import `supabase`
(ast scan, like the plan test's import check).

### 3. R17 sabotage

Exact edit: in `delete_where_user_id`, drop the `.eq("user_id", ...)`
call (delete with no filter).

`test_supabase_erase_never_deletes_without_a_filter` and
`test_supabase_backend_wipes_target_and_keeps_other_user` must both
fail (B's rows vanish). Restore before the PR. If Databricks blocks
in-place sabotage, an in-memory pytest plugin that swaps in an
unfiltered `delete_where_user_id` is the accepted substitute. Drop
the plugin before the PR.

## Out of scope

- Wiring into a route, `db_provider`, or the hosted project
- Any `DELETE /me` endpoint or auth
- Export, tombstones, retention jobs, local SQLCipher wipe
- `cached_responses` (identity `none`; Gap 8 remainder)
- Armor, Play Integrity, Flutter, deploy, APK, hosted 0026

## Gates

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

If `backend/.venv` exists, use that interpreter. No Flutter.
Do not "fix" `test_today_tonight_includes_venue_name` (it fails near
ICT midnight on main) or `test_sparse_create_with_limited_hours_succeeds`.

## Report

SHA, branch, pytest last line, files touched, the recorded op list
for user A's erase (table, op, filter column), and A/B row totals
before and after. Named tests in the report must include
`test_supabase_erase_never_deletes_without_a_filter` and
`test_supabase_backend_wipes_target_and_keeps_other_user`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
