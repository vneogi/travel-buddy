# Genie brief: SPEC-43 Gap 4 slice 4 -- in-memory erase backend proves wipe

This is the open job. Roles, hard stops, and R17 ritual are in
`docs/briefs/GENIE_SPEC_43_G10_IAM_A.md`. Do not re-read all of
SPEC-43 or SPEC-27. Read Gap 4 of
`docs/specs/SPEC-43-security-privacy-and-data-governance.md`
only as needed.

## Goal

Slice 3 landed `execute_erase` against an injected Protocol
(`4d85cd7`, PR #174). Slice 4 adds a concrete in-memory
`EraseBackend` that stores rows for every erase-required table,
implements the three delete methods with the join shapes from
the plan, and proves that after `execute_erase` the target
identity has zero remaining rows while another identity is
untouched.

No SQL. No FastAPI route. No live Postgres.

Acceptance: seed two users; erase one; leftover rows for the
erased user are empty across every `ERASE_REQUIRED` table;
the other user's rows remain.

## Base

Latest `main` (`4d85cd7`), including Gap 4 slice 3
`4d85cd7` (PR #174).

Create and push: `feat/spec43-g4-erase-memory`

Do not merge. Open one PR after gates are green.

## Read before editing

- `docs/ENGINEERING_RULES.md` (R14, R17)
- `services/data_rights_erase.py` (`ERASE_STEPS`, `ERASE_REQUIRED`,
  `EraseBackend`, `execute_erase`, `METHOD_FOR_IDENTITY`)
- `config/data_rights.py` (`RIGHTS_MAP`)
- `tests/test_spec43_g4_erase_execute.py` (must stay green)
- `tests/test_spec43_g4_erase_plan.py` (must stay green)
- `tests/test_spec43_g4_rights_inventory.py` (must stay green)

No new migration. No Flutter. No live Postgres. No network.
Do not import litellm, supabase, httpx, psycopg, or psycopg2.
Do not add a router.

## Scope

### 1. Module `services/data_rights_erase_memory.py`

Stdlib + `services.data_rights_erase` (+ `config.data_rights` if
needed). ASCII only.

`InMemoryEraseBackend`:

- Internal store: `dict[str, list[dict]]` keyed by table name.
  Only `ERASE_REQUIRED` tables may hold rows. Catalog /
  `cached_responses` are never stored.
- `seed(table: str, row: dict) -> None`:
  - Reject tables not in `ERASE_REQUIRED` with `ValueError`.
  - Row shape by method (asserted by tests):
    - `delete_where_user_id` tables: row must include
      `"user_id"`.
    - `delete_via_trip_states` tables: row must include
      `"trip_id"`. Ownership is resolved through
      `trip_states` rows that have the same `"trip_id"` and
      the target `"user_id"`.
    - `delete_via_party` (`party_member`): row must include
      `"party_id"`. Ownership is resolved through
      `trip_party` rows with that `"party_id"` whose
      `"trip_id"` belongs to the user in `trip_states`.
  - Append a shallow copy of the row.
- `rows(table: str) -> list[dict]`: shallow copies; empty list
  if none.
- `rows_for_user(user_id: str) -> dict[str, list[dict]]`:
  for every table in `ERASE_REQUIRED`, the rows that the three
  delete methods would remove for that user (same join rules).
  Do not mutate the store.
- Implement `EraseBackend`:
  - `delete_where_user_id`: remove rows where
    `row["user_id"] == user_id`; return count removed.
  - `delete_via_trip_states`: let `owned` be the set of
    `trip_id` from current `trip_states` rows with that
    `user_id`; remove rows in `table` whose `trip_id` is in
    `owned`; return count. Must still work when called
    *before* `trip_states` is deleted (children first).
  - `delete_via_party`: let `owned_parties` be party_ids from
    `trip_party` whose `trip_id` is in the user's current
    `trip_states` trip_ids; remove `party_member` rows whose
    `party_id` is in `owned_parties`; return count.
- Unknown table on delete methods: raise `ValueError` (do not
  silently no-op).

Do not log. Do not print. Do not open sockets or files.

Keep `execute_erase` unchanged except if a tiny re-export is
needed; prefer importing from the new module in tests.

### 2. Named tests

New file `tests/test_spec43_g4_erase_memory.py`. No network.

Helper that seeds, for user A and user B separately:

- `user_tiers` (user_id)
- `trip_states` (user_id, trip_id)
- `event_log`, `signal`, `trip_command` (user_id)
- `trip_node`, `trip_edge`, `trip_party` (trip_id; party also
  party_id)
- `party_member` (party_id)

Exact names:

- `test_execute_erase_leaves_zero_rows_for_target_user`
  Seed A and B. `execute_erase(A, backend)`. Assert
  `rows_for_user(A)` is empty for every `ERASE_REQUIRED`
  table. Assert B still has at least one row in `trip_states`
  and `party_member`.
- `test_delete_via_trip_states_uses_trip_states_before_parent_delete`
  Seed A with trip_node. Call only
  `backend.delete_via_trip_states(A, "trip_node")` while
  `trip_states` still holds A's trip. Assert trip_node for A
  is gone and trip_states for A remains.
- `test_other_users_rows_survive_full_erase`
  After erasing A, B's counts across all required tables are
  unchanged from a snapshot taken before erase.
- `test_seed_rejects_catalog_table`
  Seeding `venues_rag` or `cached_responses` raises ValueError.
- `test_memory_backend_satisfies_erase_backend_protocol`
  `isinstance` is not required; instead call
  `execute_erase` successfully (already covered) and assert
  the three method names are callable.

Plan / execute / inventory tests stay green. Do not edit
migrations.

### 3. R17 sabotage

Exact edit: in `delete_where_user_id`, when `table ==
"trip_states"`, return 0 without removing rows.

`test_execute_erase_leaves_zero_rows_for_target_user` must fail
(A still has trip_states rows). Restore before the PR. If
Databricks blocks in-place sabotage, an in-memory pytest
plugin that wraps that method is the accepted substitute.
Drop the plugin before the PR.

## Out of scope

- Any DELETE SQL, Supabase client, or FastAPI route
- Export document / endpoint
- Tombstones, backup restore, retention jobs
- Local SQLCipher wipe
- Armor, Play Integrity, Flutter, deploy, APK, hosted 0026

## Gates

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

If `backend/.venv` exists, use that interpreter. No Flutter.
Do not "fix" `test_today_tonight_includes_venue_name` or
`test_sparse_create_with_limited_hours_succeeds`.

## Report

SHA, branch, pytest last line, files touched, and for the
named wipe test: row counts for A before and after (sum across
tables) and confirmation B survived. Named tests in the report
must include
`test_execute_erase_leaves_zero_rows_for_target_user` and
`test_other_users_rows_survive_full_erase`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
