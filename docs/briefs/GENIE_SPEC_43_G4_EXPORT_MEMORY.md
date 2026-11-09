# Genie brief: SPEC-43 Gap 4 slice 12 -- in-memory export backend

This is the open job. Roles, hard stops, and R17 ritual are in
`docs/briefs/GENIE_SPEC_43_G10_IAM_A.md`. Do not re-read all of
SPEC-43 or SPEC-27.

## Goal

Slice 11 landed `execute_export` against an injected Protocol
(`fde1ae6`, PR #190). Slice 12 adds a concrete in-memory
`ExportBackend` that stores rows for every export-required table,
implements the three fetch methods with the join shapes from the
plan, and proves that `execute_export` returns only the caller's
rows while another identity's rows stay in the store and out of
the result.

No SQL. No FastAPI route. No live Postgres. Read-only: fetch never
mutates the store.

Acceptance: seed two users; export one; every result table's rows
belong only to that user (via `seed_owner`); the other user's store
counts are unchanged; a second export of the other user still
returns their rows.

## Base

Latest `main` (`fde1ae6`), including Gap 4 slice 11 (PR #190).

Create and push: `feat/spec43-g4-export-memory`

Do not merge. Do not deploy. Open one PR after gates are green.

## Read before editing

- `docs/ENGINEERING_RULES.md` (R14, R17)
- `services/data_rights_export.py` (`EXPORT_STEPS`,
  `EXPORT_REQUIRED`, `ExportBackend`, `execute_export`)
- `services/data_rights_erase_memory.py` (store / seed / join
  shapes to mirror; fetch instead of delete)
- `tests/test_spec43_g4_erase_memory.py` (seed helper shape)
- `tests/test_spec43_g4_export_execute.py` (must stay green)
- `tests/test_spec43_g4_export_plan.py` (must stay green)

No new migration. No Flutter. No live Postgres. No network.
Do not import litellm, supabase, httpx, psycopg, or psycopg2.
Do not add a router. Do not change RIGHTS_MAP, the erase modules,
or `execute_export`.

## Scope

### 1. Module `services/data_rights_export_memory.py`

Stdlib + `services.data_rights_export` only. ASCII only.

`InMemoryExportBackend`:

- Internal store: `dict[str, list[dict]]` keyed by table name.
  Only `EXPORT_REQUIRED` tables may hold rows. Catalog /
  `cached_responses` are never stored.
- `seed(table: str, row: dict) -> None`:
  - Reject tables not in `EXPORT_REQUIRED` with `ValueError`.
  - Required keys by method (same as erase-memory):
    - `fetch_where_user_id` tables: `"user_id"`.
    - `fetch_via_trip_states` tables: `"trip_id"`.
    - `fetch_via_party` (`party_member`): `"party_id"`.
  - Extra keys: `trip_states` also needs `"trip_id"`;
    `trip_party` also needs `"party_id"`.
  - Append a shallow copy of the row.
- `rows(table: str) -> list[dict]`: shallow copies; empty list
  if none.
- Implement `ExportBackend` (read-only; never mutate `_store`):
  - `fetch_where_user_id`: return shallow copies of rows where
    `row["user_id"] == user_id`.
  - `fetch_via_trip_states`: let `owned` be the set of
    `str(trip_id)` from current `trip_states` rows with that
    `user_id`; return shallow copies of rows in `table` whose
    `str(trip_id)` is in `owned`.
  - `fetch_via_party`: let `owned_parties` be party_ids from
    `trip_party` whose `str(trip_id)` is in the user's current
    trip_ids; return shallow copies of `party_member` rows
    whose `party_id` is in `owned_parties`.
  - Method/table mismatch (calling `fetch_where_user_id` on
    `trip_node`, etc.): raise `ValueError` before reading.
  - Unknown / non-required table: raise `ValueError`.
  - Blank / non-string `user_id`: raise `ValueError` before
    reading.

Do not log. Do not print. Do not open sockets or files.
Do not implement a delete method.

### 2. Named tests

New file `tests/test_spec43_g4_export_memory.py`. No network.

Seed helper (mirror erase-memory): for user A and user B,
`user_tiers`, `trip_states` (2 trips), `event_log` / `signal` /
`trip_command`, `trip_node` (2 per trip), `trip_edge`,
`trip_party` (`trip_id` as text), `party_member` (lead +
companion). Every seeded row carries test-only `"seed_owner"`.

Exact names:

- `test_seed_covers_every_export_required_table`
- `test_execute_export_returns_only_the_callers_rows`
  Seed A and B. `results = execute_export(A, backend)`.
  Result tables match `EXPORT_STEPS`. Every returned row has
  `seed_owner == A`. Total returned row count equals A's store
  count. B's store counts are unchanged. Store still holds A's
  rows (fetch does not delete).
- `test_other_users_rows_survive_and_export_separately`
  After exporting A, export B: B's results are non-empty and
  only B's `seed_owner`; A's store counts unchanged by B's
  export.
- `test_fetch_via_trip_states_resolves_through_trip_states`
  Call only `fetch_via_trip_states(A, "trip_node")`; returned
  nodes are A's; B's nodes remain in the store.
- `test_seed_rejects_catalog_or_cached_responses`
- `test_fetch_rejects_blank_user_id_and_method_mismatch`
- `test_exported_rows_are_detached_from_the_store`
  Mutating a result row must not change `backend.rows(...)`.

Plan / execute / erase-memory tests stay green.

### 3. R17 sabotage

Exact edit: in `fetch_where_user_id`, when `table ==
"user_tiers"`, also return B's `user_tiers` rows (or every
`user_tiers` row) alongside A's.

`test_execute_export_returns_only_the_callers_rows` and
`test_other_users_rows_survive_and_export_separately` must fail
(B's seed_owner appears in A's export, or cross-talk on the
second export). Restore before the PR. If Databricks blocks
in-place sabotage, an in-memory pytest plugin that wraps the
method is the accepted substitute. Drop the plugin before the
PR.

## Out of scope (record as remainders, do not build)

- Supabase / PostgREST export backend
- HTTP `GET`/`POST /api/v1/me/export`
- Nesting / human-readable document formatting
- `cached_responses` SQL export
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

SHA, branch, pytest last line, files touched, and for the named
caller-only export test: A/B store counts before, returned row
total for A, and A/B store counts after. Name the two R17 tests
that failed. Named tests in the report must include
`test_execute_export_returns_only_the_callers_rows` and
`test_other_users_rows_survive_and_export_separately`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
