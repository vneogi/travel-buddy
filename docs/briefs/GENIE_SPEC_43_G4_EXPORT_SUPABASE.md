# Genie brief: SPEC-43 Gap 4 slice 13 -- Supabase export backend (fake client only)

## Goal

Slices 10-12 are on main: export plan, `execute_export` against an
injected `ExportBackend`, and an in-memory export backend that proves
caller-only fetches (`0026c76`, PR #192). Slice 13 adds the backend the
hosted app would use: `SupabaseExportBackend`, which implements the three
fetch methods through an injected PostgREST-style client, mirroring
`SupabaseEraseBackend` (`54c3c8d`, PR #178).

The client is injected. Tests use a fake client that stores rows and
evaluates filters. Nothing is wired to a route or to the hosted project.
No live Supabase. No network.

The safety property that matters most: **a read is never issued without
an owner filter.** A filterless `select` on `trip_node` would return every
traveller's itinerary to whoever calls the export. Every fetch carries
`eq("user_id", ...)` or a non-empty `in_(...)` list. When the owned id
list is empty, no table read is sent at all and the result is `[]`.

## Base

Latest `main` (`0026c76`), including Gap 4 slice 12 (PR #192).

Create and push: `feat/spec43-g4-export-supabase`

Do not merge. Do not deploy. Open one PR after gates are green.

## Read before editing

- `docs/ENGINEERING_RULES.md` (R14, R17)
- `services/data_rights_export.py` (`EXPORT_STEPS`, `EXPORT_REQUIRED`,
  `ExportBackend`, `execute_export`)
- `services/data_rights_export_memory.py` (join rules to mirror)
- `services/data_rights_erase_supabase.py` (client call shape, `_data`,
  the owned-id lookups, the empty-list guard; mirror it, do not import
  it for shared code)
- `services/supabase_service.py` (client call shape only)
- `tests/test_spec43_g4_erase_supabase.py` (fake-client shape to copy)
- `tests/test_spec43_g4_export_memory.py` (must stay green)

No new migration. No Flutter. No route. No change to
`services/data_rights_export.py`, `services/data_rights_export_memory.py`,
`services/data_rights_erase*.py`, `security.py`, `supabase_service.py`,
or `routers/`. No network. Do not import `supabase`, `httpx`,
`psycopg`, or `psycopg2` in the new module.

## Scope

### 1. Module `services/data_rights_export_supabase.py`

ASCII only. Standard library plus `services.data_rights_export`.
No logging, no print.

`SupabaseExportBackend(client)`:

- Constructor takes the injected client only.
- Checks run before any client call, in this order:
  1. `user_id` must be a non-blank string (else `ValueError`).
  2. `table` must be in `EXPORT_REQUIRED` (else `ValueError`).
  3. The method must match the table's `EXPORT_STEPS` method (else
     `ValueError`, e.g. `fetch_where_user_id` on `trip_node`).
- `fetch_where_user_id(user_id, table)`:
  `client.table(table).select("*").eq("user_id", str(user_id)).execute()`;
  return `[dict(r) for r in _data(result)]`.
- `fetch_via_trip_states(user_id, table)`:
  1. Owned trips:
     `client.table("trip_states").select("trip_id").eq("user_id", str(user_id)).execute()`,
     collect `str(trip_id)` values, sorted, deduplicated, skipping nulls.
  2. If the owned list is empty, return `[]` and send no further read.
  3. `client.table(table).select("*").in_("trip_id", owned).execute()`.
- `fetch_via_party(user_id, table)` (only `party_member`):
  1. Owned trips as above; empty -> `[]`, stop.
  2. Party ids:
     `client.table("trip_party").select("party_id").in_("trip_id", owned).execute()`,
     collect `str(party_id)`, sorted, deduplicated, skipping nulls.
  3. Empty party list -> `[]`, stop.
  4. `client.table(table).select("*").in_("party_id", parties).execute()`.
- Never issue a `select` without a filter on a required table. Never
  call `.delete()`, `.update()`, `.upsert()`, `.insert()`, or any RPC.
- `_data(result)` helper: `list(getattr(result, "data", None) or [])`.

### 2. Named tests

New file `tests/test_spec43_g4_export_supabase.py`. No network.

Build a `FakeClient` modelled on
`tests/test_spec43_g4_erase_supabase.py` (copy it, do not import across
test files), with:

- A `table(name)` query object supporting `select(cols)`, `eq`, `in_`,
  and `execute()`.
- A `reads` log recording `(table, cols, filters)` for every
  `execute()`, and a `writes` log that must stay empty.
- A `fail_on_read` hook: a table name whose read raises
  `RuntimeError("EXPORT-CANARY-g4-supabase")`.
- Seeding helper for users A and B (same shape as the memory export
  tests, with a test-only owner marker).

Exact test names:

- `test_supabase_export_returns_only_the_callers_rows`
  Export A through `execute_export(A, SupabaseExportBackend(fake))`.
  Every returned row belongs to A. Per-table counts equal A's seeded
  counts. B's rows in the fake store are unchanged.
- `test_supabase_export_never_reads_without_a_filter`
  Every recorded read on a required table carries an `eq("user_id", ...)`
  or `in_(...)` filter. `writes` is empty.
- `test_supabase_export_empty_owned_trips_sends_no_child_read`
  A user with no `trip_states` rows: `fetch_via_trip_states` and
  `fetch_via_party` return `[]` and no read is recorded for
  `trip_node`, `trip_edge`, `trip_party`, or `party_member`.
- `test_supabase_export_empty_party_list_sends_no_party_member_read`
  A user with trips but no `trip_party`: `party_member` returns `[]`
  and no `party_member` read is recorded.
- `test_supabase_export_rejects_blank_user_id_before_any_read`
- `test_supabase_export_rejects_method_mismatch_before_any_read`
  e.g. `fetch_where_user_id(A, "trip_node")`.
- `test_supabase_export_rejects_non_required_table_before_any_read`
  e.g. `cached_responses`, `venues_rag`.
- `test_supabase_export_error_stops_later_reads`
  `fail_on_read="trip_node"` with the canary; `execute_export` re-raises
  the same exception; no read for later tables; canary not in any
  returned value.
- `test_supabase_export_rows_are_detached_copies`
  Mutating a returned row does not change the fake store.
- `test_export_supabase_module_has_no_forbidden_imports`
  Only `__future__`, `typing`, `services`, and `config` may be imported;
  no `supabase`, `httpx`, `psycopg`, `psycopg2`, `logging`; no `print(`.

The export-plan, export-execute, and export-memory tests stay green.

### 3. R17 sabotage

Exact edit: in `fetch_via_trip_states`, when the owned trip list is
empty, skip the early return and issue
`client.table(table).select("*").execute()` with no filter.

`test_supabase_export_never_reads_without_a_filter` and
`test_supabase_export_empty_owned_trips_sends_no_child_read` must fail.
Restore before the PR. If in-place sabotage is blocked, an in-memory
pytest plugin that wraps the method is the accepted substitute. Drop
the plugin before the PR.

## Out of scope (record as remainders, do not build)

- Wiring `SupabaseExportBackend` to the database provider or any route
- HTTP `GET`/`POST /api/v1/me/export`
- Nesting or human-readable document formatting
- Pagination, retries, RPC, or PostgREST range headers
- `cached_responses` SQL export (identity `none`, Gap 8 remainder)
- Tombstones, retention jobs, Flutter, shared denylist
- Armor, Play Integrity, deploy, APK, hosted 0026

## Gates

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

If `backend/.venv` exists, use that interpreter. No Flutter. Do not
"fix" `test_today_tonight_includes_venue_name` (fails near ICT
midnight on main) or `test_sparse_create_with_limited_hours_succeeds`.

## Report

SHA, branch, pytest last line, files touched, the recorded read list
(table and filter columns) for a full export of A, the A/B store counts
before and after, and confirmation that the recorded write list is
empty. Name the two R17 tests that failed. The named report must
include `test_supabase_export_never_reads_without_a_filter` and
`test_supabase_export_empty_owned_trips_sends_no_child_read`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
