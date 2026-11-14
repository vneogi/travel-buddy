# Genie brief: SPEC-43 Gap 4 slice 17 -- in-memory deletion tombstone and restore proof

Read this whole file before touching anything. It is the complete job.
If something here conflicts with your memory of an earlier brief, this
file wins. If something here is unclear, stop and ask; do not guess and
do not widen scope.

## 0. Context in one paragraph

Gap 4 erase is on main: ordered plan, executor, in-memory and Supabase
backends, `POST /api/v1/me/erase`, Auth delete, a 1-hour process-local
denylist, and in-process cache purge. Export is on main through a flat
HTTP GET that is now rate-limited. What is still missing is the SPEC-27
and SPEC-43 requirement that a backup restore must not make a deleted
account active again. Today's denylist is process-local and expires in
one hour. A Postgres restore (or another Cloud Run instance after TTL)
can resurrect the wiped rows with no record that the user asked to be
deleted. This slice is the first vertical of that proof: an in-memory
tombstone plus a restore-then-honor walk that leaves the deleted user
at zero rows. No SQL, no HTTP, no durable table.

## 1. Goal and the properties that matter

1. After `execute_erase(A)` and `record_tombstone(A)`, a simulated
   restore of A's wiped rows followed by `honor_tombstones` leaves A
   with zero identity rows.
2. User B, never tombstoned, is byte-identical across restore and honor.
3. The same restore without `honor_tombstones` must bring A back. That
   is the control: if the snapshot re-seed is fake, this test fails.
4. Tombstone matching is exact on `user_id`. Prefix match is forbidden
   (`user-A` must not erase `user-A-extra`).
5. `honor_tombstones` re-uses `execute_erase` against the injected
   erase backend. It is not a second delete implementation.

## 2. Preflight (do this first, stop if any check fails)

1. `git fetch origin`. Work from the `origin/main` SHA given in the
   message that sent you this brief. If `origin/main` has moved past
   it, say so and continue from the newer main only if it still
   contains every file in step 2; otherwise stop.
2. Confirm on that main these files exist: this brief,
   `services/data_rights_erase.py`,
   `services/data_rights_erase_memory.py`,
   `tests/test_spec43_g4_erase_memory.py`,
   `config/data_rights.py`, `docs/ENGINEERING_RULES.md`.
3. Confirm `services/data_rights_tombstone.py` does NOT exist,
   `tests/test_spec43_g4_tombstone_memory.py` does NOT exist, and
   `origin/feat/spec43-g4-tombstone-memory` does not exist. If any
   exist, stop and report.
4. Create a fresh branch from that main:
   `feat/spec43-g4-tombstone-memory`.

Never start work from an older SHA. Check the base before you write a
line.

## 3. Read before editing (read only; these are your patterns)

- `docs/ENGINEERING_RULES.md`: R14 (ASCII), R16 (no hard-coded pytest
  totals in docs; this slice writes no docs), R17 (a guard that cannot
  fail is not a guard).
- `services/data_rights_erase.py`: `execute_erase`, `plan_erase`,
  `ERASE_REQUIRED`, `ERASE_STEPS`. Honor must call `execute_erase`,
  not re-implement the walk.
- `services/data_rights_erase_memory.py`: `InMemoryEraseBackend.seed`,
  `rows`, `rows_for_user`. Restore in the tests is re-seeding copies
  of previously captured rows. Do not add a `restore()` method to
  the backend unless a test cannot be written without it -- prefer
  re-seed in the test file.
- `tests/test_spec43_g4_erase_memory.py`: two-user seed, `_counts`,
  `rows_for_user`. Copy the seed helper into the new test file; do
  not import across test files.

## 4. Files you may touch

- `services/data_rights_tombstone.py` (new)
- `tests/test_spec43_g4_tombstone_memory.py` (new)

Nothing else. In particular do NOT change:

- `services/data_rights_erase.py`, `services/data_rights_erase_memory.py`,
  any `services/data_rights_erase_supabase.py`,
  `services/data_rights_auth_delete.py`,
  `services/data_rights_token_deny.py`,
  `services/data_rights_cache_purge.py`
- any `services/data_rights_export*.py`
- `routers/me_router.py`, `monitoring/rate_limit.py`, `main.py`,
  `security.py`, `config/data_rights.py`, `tests/conftest.py`
- any existing test file
- any SQL or `supabase/migrations/**` (no 0026, no 0027)
- `mobile/**`, requirements files, any doc, any brief

Do not write a new brief or any doc. Do not start slice 18 (durable
table, erase-route hook, nested export, retention).

## 5. The module: `services/data_rights_tombstone.py`

ASCII only. Standard library plus `services.data_rights_erase`. No
SQL, no files, no sockets, no logging, no time-based expiry in this
slice (TTL is a later durable-store decision).

### 5.1 Store

Process-local, like the denylist. A private set of user ids is enough.
Do not persist to disk.

### 5.2 API

- `record_tombstone(user_id: str) -> None`
  Raise `ValueError` on a blank or whitespace-only `user_id` before
  mutating the set. Store the stripped id. Recording the same id twice
  is a no-op (idempotent).

- `is_tombstoned(user_id: str) -> bool`
  Exact match after strip. Unknown / blank -> False. Must not treat
  `"user-A-extra"` as tombstoned because `"user-A"` is.

- `honor_tombstones(backend, user_ids: Optional[Iterable[str]] = None) -> List[dict]`
  For each tombstoned id (or, if `user_ids` is given, the intersection
  of that list with the tombstone set), call
  `execute_erase(user_id, backend)` in a stable order (sorted ids).
  Collect the per-user result as
  `{"user_id": ..., "tables": <execute_erase return>}`.
  Skip ids that are not tombstoned. Do not erase an id that is not in
  the set.
  If `execute_erase` raises, stop and re-raise the same exception;
  later ids are not honored. Partial honor is visible, same as
  partial erase.
  An empty tombstone set, or a `user_ids` list that intersects none,
  returns `[]` and must not call `execute_erase`.

- `reset_tombstones() -> None`
  Clears the set. Tests use this; production later slices may too.
  Keep it.

Do not call Auth delete, denylist, or cache purge from this module.
Those belong to the HTTP erase path, which this slice does not touch.

Module docstring: in-memory tombstone so a simulated restore can be
re-erased; durable table, vendor backup window, hosted restore, and
the erase-route hook are remainders.

## 6. Tests: `tests/test_spec43_g4_tombstone_memory.py`

No network. No `supabase` package. Two users, A and B, seeded the
same way as `tests/test_spec43_g4_erase_memory.py` (copy the seed
helper; do not import it). Use `InMemoryEraseBackend`.

Exact test names (each must exist; add more only if they add proof):

1. `test_restore_without_honor_reactivates_deleted_user`
   Seed A and B. Snapshot every row (deep copies). `execute_erase(A)`.
   Assert A has zero `rows_for_user` rows. Re-seed the snapshot (the
   simulated restore). Assert A has rows again and B is unchanged.
   Do not record a tombstone and do not call `honor_tombstones`.
   This is the R17 control: a fake snapshot that never restores A
   makes this test fail.

2. `test_erase_record_restore_honor_leaves_zero_rows_for_tombstoned_user`
   Seed A and B. Snapshot. `execute_erase(A)`. `record_tombstone(A)`.
   Re-seed the snapshot. `honor_tombstones(backend)`.
   A's `rows_for_user` is empty for every `ERASE_REQUIRED` table.
   B's `rows_for_user` equals the snapshot of B (compare as counts
   per table, or as sorted row copies; derive expected counts from
   the snapshot, no hard-coded numbers).
   `is_tombstoned(A)` is True; `is_tombstoned(B)` is False.

3. `test_honor_tombstones_does_not_touch_other_user`
   Same setup as 2. After honor, every B row from the snapshot is
   still present. A is empty. If you capture backend delete calls,
   none may target B's user id.

4. `test_tombstone_does_not_prefix_match`
   Seed `user-A` and `user-A-extra` as two full users. Erase and
   tombstone `user-A` only. Restore both from snapshot.
   `honor_tombstones(backend)`. `user-A` is empty;
   `user-A-extra` still has rows. `is_tombstoned("user-A-extra")`
   is False.

5. `test_honor_with_empty_store_does_not_delete`
   Record a tombstone for A. Do not seed any rows. Honor returns a
   result list (A may appear with zero rows per table, which is
   `execute_erase` on an empty store) and must not raise. A second
   user with no tombstone is never passed to `execute_erase`.

6. `test_record_rejects_blank_user_id`
   `record_tombstone("")` and `record_tombstone("   ")` raise
   `ValueError`. The set stays empty (`is_tombstoned` False for
   those strings).

7. `test_honor_skips_ids_that_are_not_tombstoned`
   Seed A and B. Tombstone only A. Call
   `honor_tombstones(backend, user_ids=[A, B])`.
   A is erased; B still has rows. Passing B in `user_ids` is not
   enough to erase B.

8. `test_tombstone_module_is_ascii`
   Read `services/data_rights_tombstone.py` and assert `.isascii()`.

Use an autouse fixture that calls `reset_tombstones()` so tests do
not leak set membership.

## 7. R17 sabotage (required, and must be reported)

Two sabotage runs, each restored before the next. No repo file may
keep the sabotage.

A. Make `honor_tombstones` a no-op (`return []` as the first line,
   or a plugin that patches it to return `[]`). Under that sabotage:

   - `test_erase_record_restore_honor_leaves_zero_rows_for_tombstoned_user`
     must fail.
   - `test_honor_tombstones_does_not_touch_other_user` may stay green
     (B was never at risk).
   - `test_restore_without_honor_reactivates_deleted_user` must stay
     green (it never calls honor).

B. Make the snapshot re-seed in test 1 a no-op (plugin or in-place
   edit of the test's restore loop so it does not write rows back).
   `test_restore_without_honor_reactivates_deleted_user` must fail.
   Restore the test file hash after this run.

If in-place editing of production code is blocked, an in-memory
pytest plugin is the accepted substitute. Drop every plugin before
the PR. Confirm `services/data_rights_tombstone.py` hash is identical
before A and after the last restore.

## 8. Stop rules

Stop and report instead of improvising if:

- any preflight check in section 2 fails;
- an existing test fails for a reason related to this change;
- an existing test fails for any other reason not named in section 9;
- you feel you need to edit a file outside section 4;
- you are about to add SQL, a migration, an HTTP hook, Auth delete,
  denylist, cache purge, nested export, zip, or a retention job;
- you are about to apply or edit `0026`;
- you are about to write a brief, a doc, or a second slice.

Never "fix" an unrelated failure, never skip or xfail a test, never
loosen an assertion, never force-push over another branch.

## 9. Gates

Run from the repo root, with `backend/.venv` if it exists. Use
`ruff==0.16.3` (CI pin). A newer ruff is not the gate.

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

Known pre-existing failures. These are not yours; do not touch them:

- `test_sparse_create_with_limited_hours_succeeds` (hard-coded date;
  failed CI on PR #211 and #214)
- `test_today_tonight_includes_venue_name` (fails near ICT midnight)

Anything else failing is yours until proven otherwise. Confirm touched
files are ASCII only. If `ruff format --check .` fails on a file you
are not allowed to edit, stop and report; do not reformat it.

Dart / Flutter checks are not part of this slice. Do not run them.

## 10. Out of scope (record as remainders, do not build)

- Durable tombstone table / new migration (slice 18 candidate)
- Hooking `record_tombstone` into `POST /api/v1/me/erase`
- Vendor backup expiry window and a hosted restore drill
- Nested / human-readable / downloadable export
- Pagination; in-memory DatabaseService export wiring
- Retention jobs and completion metrics
- Flutter leave / local SQLCipher wipe
- Shared or cross-instance denylist
- Armor, Play Integrity, deploy, APK, hosted 0026
- Frontend findings F1-F4 in `UX_BACKLOG.md`

## 11. Delivery

1. Commit on `feat/spec43-g4-tombstone-memory` with the message:
   `SPEC-43 Gap 4 slice 17: in-memory deletion tombstone and restore proof`.
2. Push that branch. Verify the pushed SHA from the remote
   (`git ls-remote origin feat/spec43-g4-tombstone-memory`), not from
   your local clone.
3. Do not merge, do not deploy, do not open or edit any other branch.
   This compute has no `gh`; the reviewer opens the PR from your
   branch. Do not try to work around that.

## 12. Report (exactly these fields, in this order)

1. Base `origin/main` SHA you started from.
2. Branch name and pushed SHA (verified from the remote).
3. `pytest` last line, and the name of every failing test.
4. `ruff check`, `ruff format --check`, `git diff --check` results
   (name the ruff version).
5. Files touched (must be only those in section 4).
6. After honor: A's per-table row counts (all zero) and B's per-table
   counts equal to the snapshot.
7. Confirmation that restore without honor brings A back (test 1).
8. Confirmation that `user-A-extra` survived when only `user-A` was
   tombstoned.
9. The R17 tests that failed under sabotage A and B, by name, and
   confirmation the sabotage was removed and the tombstone-module
   hash matches the pre-sabotage hash.
10. Anything you were unsure about, or anything you chose not to do.

Do not edit this brief, `PROJECT_STATUS`, or `HANDOFF`.
