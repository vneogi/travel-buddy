# Genie brief: SPEC-43 Gap 4 durable tombstone

Read this whole file before touching anything. It is the complete job.
If something here conflicts with your memory of an earlier brief, this
file wins. If something here is unclear, stop and ask; do not guess and
do not widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA.

## 0. Context

Gap 4 erase is live: `POST /api/v1/me/erase` (`routers/me_router.py`)
runs `execute_erase` over the Supabase backend, then the Auth delete,
the token denylist and the in-process cache purge.

The tombstone module, `services/data_rights_tombstone.py`, is process
memory only. Its own docstring lists the remainders: a durable
tombstone table, recording the tombstone from the erase route, the
vendor backup window, and a hosted restore drill. Nothing on `main`
calls `record_tombstone` yet, so a backup restore can bring a deleted
user's rows back and nothing re-erases them.

This slice closes the first two remainders only:

1. a durable `data_rights_tombstone` table (migration 0027);
2. a durable store that the erase route writes on success, and that
   `honor_tombstones` can read back for a restore re-erase.

Out of scope: any request-path block on tombstoned users, the vendor
backup window, the restore drill, Flutter, and applying the migration
to the hosted project (owner-gated).

## 1. Goal

1. Migration `supabase/migrations/0027_spec43_g4_tombstone.sql`
   creates `data_rights_tombstone`, with RLS enabled and forced, and
   every privilege revoked from PUBLIC, anon and authenticated, following
   the 0026 pattern. service_role only.
2. `services/data_rights_tombstone.py` keeps its public functions and
   gains a durable path behind the same interface, so the in-memory
   tests keep passing unchanged.
3. `/me/erase` records a durable tombstone after the row erase succeeds.
   If that write fails, the response is the existing generic
   `500 {"detail": "erase_incomplete"}`. The erase is repeatable, so the
   client retries.
4. `honor_tombstones(backend)` with no `user_ids` reads the durable set
   when a durable store is configured, and otherwise the in-memory set.

## 2. Preflight

1. `git fetch origin`. Work from the base SHA in the message that sent
   this brief.
2. Confirm these exist on that SHA:
   `services/data_rights_tombstone.py`, `services/data_rights_erase.py`,
   `routers/me_router.py`, `supabase/migrations/0026_spec43_g2_rls.sql`,
   `tests/test_spec43_g4_tombstone_memory.py`. If any is missing, stop.
3. Confirm `supabase/migrations/0027_spec43_g4_tombstone.sql` and
   `origin/feat/spec43-g4-durable-tombstone` do not exist.
4. Branch: `feat/spec43-g4-durable-tombstone`.

## 3. Read before editing

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 4
  and Gap 2)
- `docs/ENGINEERING_RULES.md` R14, R16, R17
- `docs/briefs/GENIE_SPEC_43_G4_TOMBSTONE_MEMORY.md` and
  `docs/briefs/GENIE_SPEC_43_G4_ERASE_ROUTE.md`
- `services/data_rights_tombstone.py` (whole file)
- `services/data_rights_erase.py` (`execute_erase`, the backend protocol)
- `services/data_rights_erase_supabase.py` (how the Supabase backend
  calls PostgREST with the service key; reuse that client, do not build
  a second one)
- `routers/me_router.py` (the 500 `erase_incomplete` path and the order
  of steps)
- `supabase/migrations/0026_spec43_g2_rls.sql` (privilege pattern)
- `tests/test_spec43_g4_tombstone_memory.py`

## 4. Files you may touch

- `supabase/migrations/0027_spec43_g4_tombstone.sql` (new)
- `services/data_rights_tombstone.py` (durable path added; existing
  functions keep their behaviour)
- `services/data_rights_tombstone_supabase.py` (new; the durable store)
- `routers/me_router.py` (one call after a successful row erase, and the
  failure mapping)
- `tests/test_spec43_g4_durable_tombstone.py` (new)
- `tests/test_spec43_g4_tombstone_memory.py` only if an import needs it;
  no assertion changes

Nothing else. No What Now, no reachability code, no `agents/`, no
Flutter, no `requirements*.txt`, no docs (the planning agent owns docs),
no hosted deploy, no migration apply.

## 5. The change

### 5.1 Migration 0027

Table `public.data_rights_tombstone`:

- `user_id text primary key` (stored after strip; non-blank)
- `recorded_at timestamptz not null default now()`
- `source text not null default 'me_erase'` (closed: `me_erase` only)

Then, following 0026: `ENABLE ROW LEVEL SECURITY`,
`FORCE ROW LEVEL SECURITY`, `REVOKE ALL ... FROM PUBLIC, anon,
authenticated`, `GRANT ALL ... TO service_role`. No policies for
anon or authenticated. Include a header comment with the purpose and
the owner-gated apply note. ASCII only.

### 5.2 Durable store (`services/data_rights_tombstone_supabase.py`)

- `SupabaseTombstoneStore(client)` with two methods:
  - `put(user_id)`: upsert on `user_id`, idempotent.
  - `list_ids()`: returns the sorted stored `user_id` values.
- The client is the existing Supabase service-key client. Never log the
  key, URL, or any response body.
- Failures raise a closed exception `TombstoneStoreError`. Its message
  is a fixed code, never a row or key.

### 5.3 `services/data_rights_tombstone.py`

- Keep `record_tombstone`, `is_tombstoned`, `honor_tombstones` and
  `reset_tombstones` with their current signatures and behaviour for
  the in-memory set.
- Add `record_tombstone_durable(user_id, store)`: calls
  `store.put(cleaned)` and then the in-memory `record_tombstone`. If
  `store.put` raises, let `TombstoneStoreError` propagate. Do not add to
  the in-memory set on failure.
- Extend `honor_tombstones(backend, user_ids=None, store=None)`: when
  `user_ids is None` and `store` is given, the target set is
  `store.list_ids()` union the in-memory set. Otherwise behaviour is
  exactly as today. A `TombstoneStoreError` from `list_ids` propagates.

### 5.4 Erase route (`routers/me_router.py`)

After the row erase succeeds and before the Auth delete:

- Call `record_tombstone_durable(user_id, store)` where `store` is
  built from the same Supabase client the erase backend uses. No second
  client.
- If it raises `TombstoneStoreError`, return
  `500 {"detail": "erase_incomplete"}` with the same body shape as the
  other failure paths. Do not run the Auth delete or the denylist step
  in that case, so the user can retry the whole erase.
- The 422 confirmation check and the debug-mode behaviour are unchanged.
- Test-mode in-memory backend (`DatabaseService`, not wired for erase):
  no durable store, so the route does not call the store. Document that
  in a code comment. Do not add a fake Supabase.

## 6. Tests

No test may open a real socket or call Supabase. Use a fake client or
fake store object in memory.

`tests/test_spec43_g4_durable_tombstone.py`, exact names:

1. `test_migration_0027_enables_and_forces_rls`: text check of the SQL
   file for ENABLE, FORCE, REVOKE from anon and authenticated, GRANT to
   service_role; and no `CREATE POLICY` for anon or authenticated.
2. `test_migration_0027_is_ascii`
3. `test_store_put_is_idempotent`
4. `test_store_put_failure_raises_closed_code`: the message is exactly
   the closed code and contains no user id or key.
5. `test_record_durable_writes_store_then_memory`
6. `test_record_durable_failure_leaves_memory_unchanged`
7. `test_honor_reads_durable_ids_when_store_given`
8. `test_honor_without_store_is_unchanged`: existing semantics.
9. `test_honor_store_failure_propagates`
10. `test_erase_route_records_tombstone_after_row_erase`: call order
    recorded by fakes is row erase, then store put, then Auth delete.
11. `test_erase_route_store_failure_returns_erase_incomplete`: 500 body
    is exactly `{"detail": "erase_incomplete"}`; Auth delete never
    called.
12. `test_erase_route_store_failure_logs_no_user_id` (caplog).
13. `test_blank_user_id_rejected_before_store` (ValueError; store.put
    never called).
14. `test_touched_files_are_ascii`

## 7. R17

Run each, confirm the named test fails, then restore:

A. Make `record_tombstone_durable` skip `store.put`:
   `test_record_durable_writes_store_then_memory` fails.
B. Swallow `TombstoneStoreError` in the erase route:
   `test_erase_route_store_failure_returns_erase_incomplete` fails.
C. Remove `ENABLE ROW LEVEL SECURITY` from the migration text:
   `test_migration_0027_enables_and_forces_rls` fails.

## 8. Stop rules

Stop and ask if:

- you need a new dependency;
- you are tempted to block tombstoned users on any request path. That
  is a later slice;
- you need to apply the migration to any hosted database;
- the erase order on `main` differs from section 5.4 in a way that
  would change which step runs first;
- an existing erase test needs an assertion changed rather than only
  an import added.

## 9. Gates

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

ruff 0.16.3. Zero failures expected. ASCII only. Do not add
`SPEC-NN` references to any file unless a spec file with that number
exists under `docs/specs/` (the docs hygiene test enforces this).

## 10. Delivery

One commit on `feat/spec43-g4-durable-tombstone`:
`feat: durable Gap 4 tombstone recorded from erase route`.
Push and verify the remote SHA. Do not merge. No `gh`. Do not apply
the migration.

## 11. Report

1. Base SHA.
2. Branch and remote SHA.
3. pytest last line.
4. ruff, format, and diff-check results.
5. Files touched, with +/- counts.
6. R17 A, B and C results.
7. Confirmation that no route other than `/me/erase` changed.
8. Confirmation that the migration was not applied anywhere.
9. Anything you were unsure about.
