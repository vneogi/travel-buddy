# Genie brief: SPEC-43 Gap 4 slice 13 -- Supabase export backend (fake client only)

Read this whole file before touching anything. It is the complete job.
If something here conflicts with your memory of an earlier brief, this
file wins. If something here is unclear, stop and ask; do not guess and
do not widen scope.

## 0. Context in one paragraph

Gap 4 is data rights (export, deletion, retention). On main already:
the data-rights inventory, the erase plan and executor, an in-memory
erase backend, `SupabaseEraseBackend` (`54c3c8d`, PR #178), the
`POST /api/v1/me/erase` route, Auth identity delete, the process-local
denylist, in-process cache purge, the export plan (`2fa9074`), the
export executor (`fde1ae6`), and the in-memory export backend
(`0026c76`, PR #192). This slice adds the export counterpart of
`SupabaseEraseBackend`: `SupabaseExportBackend`. It is read-only and is
not wired to any route. A later slice will add the HTTP export route.

## 1. Goal and the one property that matters

`SupabaseExportBackend(client)` implements the three `ExportBackend`
fetch methods through an injected PostgREST-style client (the
supabase-py builder shape: `client.table(t).select(...).eq(...)`,
`.in_(...)`, `.execute()`).

The property that matters most: **a read on a user-data table is never
issued without an owner filter.** A filterless `select("*")` on
`trip_node` would hand every traveller's itinerary to whoever calls the
export. Every fetch carries `eq("user_id", ...)` or a non-empty
`in_(...)` list. When the owned id list is empty, no read of that table
is sent at all and the result is `[]`.

Everything else in this slice is in service of proving that property
with a fake client.

## 2. Preflight (do this first, stop if any check fails)

1. `git fetch origin`. Work from the `origin/main` SHA given in the
   message that sent you this brief. If `origin/main` has moved past
   it, say so and continue from the newer main only if it still
   contains every file in step 2; otherwise stop.
2. Confirm on that main these files exist: this brief,
   `services/data_rights_export.py`,
   `services/data_rights_export_memory.py`,
   `services/data_rights_erase_supabase.py`,
   `tests/test_spec43_g4_erase_supabase.py`,
   `tests/test_spec43_g4_export_memory.py`,
   `docs/ENGINEERING_RULES.md`.
3. Confirm `services/data_rights_export_supabase.py` and
   `tests/test_spec43_g4_export_supabase.py` do NOT exist yet, and
   `origin/feat/spec43-g4-export-supabase` does not exist. If any of
   them exists, this slice may already be done: stop and report.
4. Do not start from a branch you made earlier. Create a fresh branch
   from that main: `feat/spec43-g4-export-supabase`.

Never start work from an older SHA. An earlier Gap 3 branch was built on
a stale base and, if merged, would have deleted most of Gap 4. Check the
base before you write a line.

## 3. Read before editing (read only; these are your patterns)

- `docs/ENGINEERING_RULES.md`: R14 (ASCII), R16 (no hard-coded pytest
  counts in docs), R17 (a guard that cannot fail is not a guard).
- `services/data_rights_export.py`: `EXPORT_STEPS`, `EXPORT_REQUIRED`,
  `EXPORT_METHODS`, the `ExportBackend` protocol (methods take
  `(user_id, table)` and return a list of row dicts), `execute_export`.
- `services/data_rights_export_memory.py`: the join semantics to match,
  and how it validates `user_id` and `table`.
- `services/data_rights_erase_supabase.py`: copy its structure. Same
  `_data` helper, same `_owned_trip_ids` / `_owned_party_ids`, same
  empty-list guard. Mirror it; do not import from it.
- `tests/test_spec43_g4_erase_supabase.py`: the fake client to adapt.

## 4. Files you may touch

Create exactly two files:

- `services/data_rights_export_supabase.py`
- `tests/test_spec43_g4_export_supabase.py`

Nothing else. In particular do NOT change:

- `services/data_rights_export.py`, `services/data_rights_export_memory.py`
- any `services/data_rights_erase*.py`
- `security.py`, `main.py`, `routers/`, `config/data_rights.py`
- `services/supabase_service.py`, any migration under `migrations/`
- any existing test file (do not edit, delete, or loosen a single line
  of an existing test; if one breaks, stop and report)
- any doc, any brief, `PROJECT_STATUS`, `HANDOFF`, `DOCUMENT_MAP`

Do not write a new brief or any doc. Do not start slice 14.

## 5. The module: `services/data_rights_export_supabase.py`

ASCII only. Standard library plus `services.data_rights_export`. No
`logging`, no `print`, no network, no `supabase`, `httpx`, `psycopg`,
`psycopg2`, or `litellm` import. Allowed import roots: `__future__`,
`typing`, `services`.

Module docstring (short): slice number, that it is read-only, the
filter safety rule, that it is not wired to any route or provider, and
two recorded limits: no pagination (PostgREST returns at most its
configured max rows per request, so a very large table could be
truncated silently; a later slice must page), and no retries or RPC.

Structure (mirror the erase backend):

```python
_METHOD_FOR_TABLE = {s["table"]: s["method"] for s in EXPORT_STEPS}

def _data(result) -> list:
    return list(getattr(result, "data", None) or [])

class SupabaseExportBackend:
    def __init__(self, client) -> None: ...
```

Validation runs before any client call, and every failure is a
`ValueError` with a short fixed message that contains no user input:

1. `user_id` must be a `str` and non-blank after `strip()` (None,
   non-str, `""`, `"   "` all rejected).
2. `table` must be in `EXPORT_REQUIRED`. Catalog and `none` tables such
   as `venues_rag` and `cached_responses` are rejected.
3. The method called must equal that table's method in `EXPORT_STEPS`
   (for example `fetch_where_user_id(user, "trip_node")` is rejected).

Methods:

- `fetch_where_user_id(user_id, table)`:
  `client.table(table).select("*").eq("user_id", str(user_id)).execute()`.
  Return `[dict(r) for r in _data(result)]`.
- `fetch_via_trip_states(user_id, table)`:
  1. Owned trips:
     `client.table("trip_states").select("trip_id").eq("user_id", str(user_id)).execute()`.
     Collect `str(trip_id)`, skip nulls, deduplicate, sort.
  2. If that list is empty: return `[]`. Send no further read.
  3. `client.table(table).select("*").in_("trip_id", owned).execute()`.
     Return detached row copies.
- `fetch_via_party(user_id, table)` (only `party_member`):
  1. Owned trips as above. Empty: return `[]`, stop.
  2. Party ids:
     `client.table("trip_party").select("party_id").in_("trip_id", owned).execute()`.
     Collect `str(party_id)`, skip nulls, deduplicate, sort.
  3. Empty party list: return `[]`, stop.
  4. `client.table(table).select("*").in_("party_id", parties).execute()`.
     Return detached row copies.

Hard rules inside the module:

- Never call `.delete()`, `.update()`, `.upsert()`, `.insert()`, `.rpc()`
  or anything that writes.
- Never issue a `select` on a required table without `eq` or a
  non-empty `in_`.
- `trip_states.trip_id` is a uuid and `trip_party.trip_id` is text; always
  compare and send ids as `str`, exactly as the erase backend does.
- Do not catch exceptions. A client error propagates unchanged so that
  `execute_export` can stop and re-raise it.
- Do not log, print, or include row contents in any message.

## 6. The tests: `tests/test_spec43_g4_export_supabase.py`

No network. No `supabase` package. Copy the fake client from
`tests/test_spec43_g4_erase_supabase.py` into the new file (do not import
across test files) and change it as follows:

- Support `select`, `eq`, `in_`, `execute` only. Give the query object
  NO `delete`, `update`, `insert`, `upsert`, or `rpc` method, so any
  write attempt raises `AttributeError` and fails loudly.
- Record every executed read as `(table, op, filters)` in `client.ops`,
  where `op` is `"select"`.
- Add an optional `fail_on_read` table name. Reading that table raises
  `RuntimeError("EXPORT-CANARY-g4-supabase")`.
- Seed users A and B with the same shapes as the erase test (use the
  test-only `seed_owner` marker on every row; the backend never reads it).
  Also seed a user C who has a `user_tiers` row and no trips, and a user D
  who has trips but no `trip_party` rows.

Exact test names (each must exist; add more only if they add proof):

1. `test_supabase_export_returns_only_the_callers_rows`
   Export A with `execute_export(A, SupabaseExportBackend(client))`.
   Every returned row has `seed_owner == A`. Per-table row counts equal
   A's seeded counts (derive them from the seeds; no hard-coded
   numbers). B's rows in the fake store are unchanged.
2. `test_supabase_export_never_reads_without_a_filter`
   Run a full export for A, then for C. For every recorded read
   (including the ownership lookups on `trip_states` and `trip_party`),
   assert at least one filter is present and every `in_` list is
   non-empty. The full export for C is required: it is what makes the
   sabotage in section 7 reachable.
3. `test_supabase_export_empty_owned_trips_sends_no_child_read`
   For user C, `fetch_via_trip_states` for `trip_node`, `trip_edge`,
   `trip_party` and `fetch_via_party` for `party_member` all return
   `[]`, and no read is recorded on `trip_node`, `trip_edge`,
   `trip_party`, or `party_member`.
4. `test_supabase_export_empty_party_list_sends_no_party_member_read`
   For user D, `party_member` returns `[]` and no read on `party_member`
   is recorded.
5. `test_supabase_export_scopes_child_reads_to_owned_ids`
   Assert the exact recorded ops for A's `trip_node` fetch and A's
   `party_member` fetch (owned trip lookup, party lookup, then the child
   read with sorted `str` ids), in the style of the erase test.
6. `test_supabase_export_rejects_blank_user_id_before_any_read`
   Parametrize None, `""`, `"   "`, and a non-str. `client.ops == []`.
7. `test_supabase_export_rejects_method_mismatch_before_any_read`
   For example `fetch_where_user_id(A, "trip_node")` and
   `fetch_via_party(A, "trip_states")`. `client.ops == []`.
8. `test_supabase_export_rejects_non_required_table_before_any_read`
   For example `cached_responses`, `venues_rag`, `nope`. `client.ops == []`.
9. `test_supabase_export_error_stops_later_reads`
   `fail_on_read="trip_node"`. `execute_export` re-raises the same
   `RuntimeError`. No read is recorded for tables after `trip_node` in
   `EXPORT_STEPS`. The canary string is not in any returned value.
10. `test_supabase_export_rows_are_detached_copies`
    Mutate a returned row; the fake store is unchanged.
11. `test_supabase_export_never_writes`
    A full export of A leaves every store row identical to its seed, and
    `client.ops` contains only `"select"` operations.
12. `test_export_supabase_module_has_no_forbidden_imports`
    Use `ast` (not a substring search of the file text, because module
    docstrings legitimately contain words like "supabase"). Roots must be
    a subset of `{"__future__", "typing", "services"}`; none of
    `supabase`, `httpx`, `psycopg`, `psycopg2`, `logging`, `litellm`.
13. `test_supabase_export_does_not_print`
    A full export with `capsys` captures empty stdout and stderr.

Do not hard-code the number of tests or rows anywhere (R16). The
existing export-plan, export-execute, export-memory, and erase tests
must stay green and unedited.

## 7. R17 sabotage (required, and must be reported)

Make this exact temporary edit in the new module: in
`fetch_via_trip_states`, when the owned trip list is empty, skip the
early `return []` and instead issue
`client.table(table).select("*").execute()` with no filter, then return
its rows.

Run the new test file. Exactly these two tests must fail, and no others:

- `test_supabase_export_never_reads_without_a_filter`
- `test_supabase_export_empty_owned_trips_sends_no_child_read`

If a different set fails, your tests do not prove the property: fix the
tests, not the sabotage, and repeat. Then restore the edit and show the
new file is byte-identical to what you committed (`git diff` is empty).

If in-place editing is blocked on the compute, use a throwaway pytest
plugin that wraps `fetch_via_trip_states` only while the test runs. That
is accepted. Delete the plugin afterwards; no sabotage artifact may be
committed.

## 8. Stop rules

Stop and report instead of improvising if:

- any preflight check in section 2 fails;
- an existing test fails for a reason related to this change;
- an existing test fails for any other reason not named in section 9;
- you feel you need to edit a file outside section 4;
- the fake client cannot express a read you need;
- you are about to write a brief, a doc, or a second slice.

Never "fix" an unrelated failure, never skip or xfail a test, never
loosen an assertion, never force-push over another branch.

## 9. Gates

Run from the repo root, with `backend/.venv` if it exists:

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

Known pre-existing failures. These are not yours; do not touch them:

- `test_sparse_create_with_limited_hours_succeeds` (hard-coded date)
- `test_today_tonight_includes_venue_name` (fails near ICT midnight)

Anything else failing is yours until proven otherwise. Also confirm the
two new files are ASCII only.

## 10. Out of scope (record as remainders, do not build)

- Wiring `SupabaseExportBackend` to a provider or any route
- `GET` or `POST /api/v1/me/export` and any document format
- Nesting rows under trips, human-readable output, file download
- Pagination or range headers (see the module docstring note)
- Retries, RPC, caching, auth
- `cached_responses` SQL export (identity `none`, Gap 8 remainder)
- Tombstones, retention jobs, Flutter, a shared denylist
- Armor, Play Integrity, deploy, APK, hosted 0026

## 11. Delivery

1. Commit the two files on `feat/spec43-g4-export-supabase` with the
   message: `SPEC-43 Gap 4 slice 13: SupabaseExportBackend with filter-safe reads`.
2. Push that branch. Verify the pushed SHA from the remote
   (`git ls-remote origin feat/spec43-g4-export-supabase`), not from
   your local clone.
3. Do not merge, do not deploy, do not open or edit any other branch.
   This compute has no `gh`; the reviewer opens the PR from your branch.
   Do not try to work around that.

## 12. Report (exactly these fields, in this order)

1. Base `origin/main` SHA you started from.
2. Branch name and pushed SHA (verified from the remote).
3. `pytest` last line, and the name of every failing test.
4. `ruff check`, `ruff format --check`, `git diff --check` results.
5. Files touched (must be exactly the two in section 4).
6. The recorded read list, one line per read (table, op, filters), for a
   full export of user A.
7. A and B store row counts before and after the export (must match).
8. Confirmation that no write was attempted and `client.ops` has only
   `select`.
9. The two R17 tests that failed under sabotage, by name, and
   confirmation that everything else in the file stayed green, then
   confirmation the sabotage was removed.
10. Anything you were unsure about, or anything you chose not to do.

Do not edit this brief, `PROJECT_STATUS`, or `HANDOFF`.
