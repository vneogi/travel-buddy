# Genie brief: SPEC-43 Gap 4 slice R2, Supabase retention backend

Read this whole file before touching anything. It is the complete job.
If something here conflicts with your memory of an earlier brief, this
file wins. If something here is unclear, stop and ask; do not guess and
do not widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA.

Owning spec: `docs/specs/SPEC-43-security-privacy-and-data-governance.md`
(Gap 4). Parent: SPEC-27 (lifecycle). Previous slice:
`docs/briefs/GENIE_SPEC43_G4_RETENTION.md` (R1, on main as PR #295,
`c566e09`). Scope is backend only. CI is the gate. No phone, no Windows
laptop, no hosted deploy, no hosted migration, no scheduler, no route.

## 0. Context

R1 put a pure retention planner on main in
`services/data_rights_retention.py`: `RetentionPolicy`, `POLICIES` (two
entries), `cutoff_for`, `is_candidate`, `RetentionBackend` (Protocol with
`count_expired` and `delete_expired`), `run_retention` (dry run by
default, batch limit 1..5000), and `InMemoryRetentionBackend`.

R2 adds the second backend: the same two methods over an injected
supabase-py style client, so the planner can one day run against the
real tables. It must behave exactly like the in-memory backend.

### Owner decisions (2026-11-19, recorded on main in PR #297)

- The windows are approved: `cached_responses` rows are deleted once
  `expires_at <= now` (24-hour TTL); `signal` rows are deleted when
  `captured_at` is older than 365 days.
- Whether any retention job runs on hosted is deferred until before
  production, mass user exposure, or a Play/App Store listing. So R2 is
  code and tests only. It is NOT wired to a route, a scheduler, a CLI, a
  settings flag, or `main.py`, and nothing in R2 runs on hosted.

Put this sentence in the new module docstring: "Not wired to any route,
scheduler or CLI; any hosted run is an owner decision before production."

### Verified facts on `main` (re-verify in preflight)

1. `supabase/migrations/0001_initial_schema.sql`: `cached_responses`
   primary key `cache_id UUID`; `expires_at TIMESTAMP WITH TIME ZONE
   DEFAULT (NOW() + INTERVAL '24 hours')`. `expires_at` is nullable (no
   NOT NULL). There is no index on `expires_at`.
2. `supabase/migrations/0002_signals_core.sql`: `signal` primary key
   `signal_id UUID`; `captured_at TIMESTAMP WITH TIME ZONE NOT NULL`.
   Indexes exist on `(signal_type_id, captured_at)`, `user_id`,
   `trip_id`, `place_ref`; none on `captured_at` alone.
3. No migration adds a foreign key to `signal` or `cached_responses`.
4. 0026 enables and forces RLS on both tables. The backend is meant for
   the service-key client (as the erase and tombstone backends are); it
   never builds a client.
5. `services/supabase_service.py` already uses the client shapes this
   brief needs: `select(..., count="exact")`, `.lt(...)`, `.order(...)`,
   `.limit(...)`, `.delete()`, `.in_(...)`, `.eq(...)`.
6. `SupabaseService.clear_expired_cache` exists, is an unbounded delete,
   and is unused (`tests/test_backend_parity.py` marks it DEBT). Do NOT
   call it, change it, or delete it in R2. Gap 8 owns it.
7. `InMemoryRetentionBackend.PRIMARY_KEYS` is
   `{"cached_responses": "cache_id", "signal": "signal_id"}`.

## 1. Goal

`SupabaseRetentionBackend(client)` that implements `RetentionBackend` for
exactly the two policies in `POLICIES`, with these guarantees:

- Same answers as `InMemoryRetentionBackend` for the same rows: same
  candidate count, same skipped count, same rows deleted in the same
  order. Tests prove this with a parity test.
- A delete is never sent without both a non-empty primary-key `in_`
  filter and the policy's time filter.
- At most `limit` rows are deleted per call, oldest first, then by
  primary key.
- Nothing is logged; failures raise a closed error code with no row, id,
  URL, or response body.

## 2. Preflight

1. `git fetch origin`. Work from the base SHA in the message that sent
   this brief.
2. Confirm section 0 facts 1 to 7 on that SHA. If any differs in a way
   that changes the plan, stop and report.
3. Confirm `services/data_rights_retention_supabase.py` does not exist and
   `origin/feat/spec43-g4-retention-supabase` does not exist.
4. Branch: `feat/spec43-g4-retention-supabase`.
5. `pip install -r requirements.txt -r requirements-dev.txt` is approved
   on your compute. Do not install anything else.

## 3. Read before editing

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 4)
- `docs/ENGINEERING_RULES.md` R13, R14, R16, R17
- `services/data_rights_retention.py` (whole file)
- `tests/test_spec43_g4_retention.py` (fixtures and style)
- `services/data_rights_erase_supabase.py` (filter-safe delete pattern)
- `services/data_rights_tombstone_supabase.py` (closed error codes,
  paging, no logging)
- `tests/test_spec43_g4_erase_supabase.py` (the fake client pattern)

## 4. Files you may touch

- `services/data_rights_retention_supabase.py` (new).
- `tests/test_spec43_g4_retention_supabase.py` (new).

Nothing else. Do not edit `services/data_rights_retention.py`,
`config/data_rights.py`, `services/supabase_service.py`, migrations,
`settings.py`, routers, `main.py`, existing tests, Flutter,
`.env.example`, or docs. Do not add a dependency. If you believe the R1
module must change, stop and ask.

## 5. Design

### 5.1 Module shape

- Imports only the standard library and public names from
  `services.data_rights_retention` (`POLICIES`, `RetentionPolicy`,
  `RetentionCount`, `validate_policy`, `MIN_BATCH_LIMIT`,
  `MAX_BATCH_LIMIT`). Do not import underscore names from R1; write the
  small helpers you need locally.
- No `import supabase`, `httpx`, `requests`, `logging`, or `print`.
  ASCII only.
- `PRIMARY_KEYS = {"cached_responses": "cache_id", "signal": "signal_id"}`
  must equal `InMemoryRetentionBackend.PRIMARY_KEYS` (test it).
- `DELETE_CHUNK = 200`: the most primary keys sent in one delete. A
  5000-id `in_` list would make a URL far too long for PostgREST.

### 5.2 Checks (before any client call)

Every public method first:

- calls `validate_policy(policy)`, then requires `policy in POLICIES`
  (value equality). Any other policy raises `ValueError`, even a valid
  one, so this backend can only ever touch the two approved tables and
  columns;
- requires `cutoff` to be a timezone-aware datetime, else `ValueError`;
- `delete_expired` also requires `limit` to be an int (not bool) within
  `MIN_BATCH_LIMIT..MAX_BATCH_LIMIT`, else `ValueError`.

A failed check must make no client call at all (tests prove it).

### 5.3 Cutoff format

Send the cutoff as UTC with a `Z` suffix and microseconds, for example
`2026-11-19T10:00:00.000000Z`
(`cutoff.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")`).
Never send a `+00:00` offset: a `+` in a query string can be read as a
space.

### 5.4 Time filter (must match R1 `is_candidate`)

- Expiry policy (`cached_responses.expires_at`): `.lte(column, cutoff)`.
- Window policy (`signal.captured_at`): `.lt(column, cutoff)`.

One local helper applies the right filter. Both methods use it, so the
boundary cannot drift between counting and deleting.

### 5.5 `count_expired(policy, cutoff) -> RetentionCount`

- Candidates: `table(t).select(pk, count="exact")` plus the time filter,
  plus `.limit(1)` so no full row set is fetched. Use `result.count`.
- Skipped: the same select with `.is_(column, "null")` instead of the time
  filter. A NULL time is never a candidate and never deleted, matching
  the in-memory backend's `skipped_invalid`.
- If `result.count` is missing or not an int, raise the count error
  (section 5.7). Do not fall back to `len(result.data)`.

### 5.6 `delete_expired(policy, cutoff, limit) -> int`

1. Select candidates: `table(t).select(f"{pk},{column}")`, time filter,
   `.order(column)`, `.order(pk)`, `.limit(limit)`.
2. Keep the primary keys in that order, dropping any row without one. If
   the list is empty, return 0 and send no delete.
3. For each chunk of at most `DELETE_CHUNK` keys, in order:
   `table(t).delete().in_(pk, chunk)` plus the same time filter again,
   then `execute()`. The repeated time filter means a row whose time
   changed after the select is not deleted.
4. Return the total number of rows the delete responses returned.

Never call `.delete()` without both filters. Never delete by time filter
alone.

### 5.7 Errors

`RetentionBackendError(Exception)` with closed codes
`retention_count_failed` and `retention_delete_failed`, the same pattern
as `TombstoneStoreError`: the message is the code only. Any exception
from the client during counting raises the count code, and during
selection or deletion raises the delete code (`raise ... from None`, so no
response text is chained). Rows already deleted by an earlier chunk stay
deleted; that is acceptable, because the job is idempotent.

## 6. Tests

`tests/test_spec43_g4_retention_supabase.py`. Build a fake client in the
test file, extending the erase-test fake. It must support `table`,
`select(cols, count=None)`, `delete`, `eq`, `in_`, `lt`, `lte`, `is_`,
`order`, `limit`, `execute`. Store rows with aware `datetime` values or
`None`. Parse filter values with `datetime.fromisoformat`. Record every
executed op with its filters. Like the erase fake, an unfiltered delete
must really delete every row in the fake so a regression is visible.

Use fixed `now` values, never `datetime.now()`. Exact test names:

1. `count for cached_responses uses lte on expires_at`
2. `count for signal uses lt on captured_at`
3. `signal row exactly at the cutoff is kept`
4. `cached_responses row expiring exactly now is a candidate`
5. `null time is counted as skipped and never deleted`
6. `cutoff is sent as UTC with Z suffix and no plus sign`
7. `delete takes oldest first then primary key, at most limit rows`
8. `every delete carries a primary key in filter and the time filter`
9. `no candidates sends no delete`
10. `delete chunks primary keys at DELETE_CHUNK`
11. `row whose time moved after the select is not deleted`
12. `invalid limit, naive cutoff, or unknown policy makes no client call`
    (include the tombstone table, a third table, and a `signal` policy with
    a different window)
13. `client failure raises a closed code with no row data in the message`
14. `parity with the in-memory backend for the same rows`
    (seed identical rows in both, run `run_retention` dry-run then real
    with a small `batch_limit`; reports are equal and deleted primary keys
    match in order)
15. `dry run through run_retention sends no delete`
16. `primary keys match the in-memory backend`
17. `hosted-safe: module does not import supabase, network, or logging`
    (static source scan, ASCII check, and the docstring sentence from
    section 0)
18. `module is not wired to any route, scheduler, or main`
    (scan every `.py` file outside `tests/` and the module itself; none
    may mention `data_rights_retention_supabase`)

Report two sabotage checks: change `.lt` to `.lte` for the window policy
and show test 3 fails; remove the time filter from the delete and show
test 11 fails. Revert and show green.

## 7. Stop and ask

Stop and report (do not guess) if:

- Any section 0 fact is false on the base SHA, especially a foreign key
  to `signal` or `cached_responses`, or a primary key name change.
- supabase-py on the pinned version lacks `lt`, `lte`, `is_`, `order`,
  `limit`, or `count="exact"`.
- You think the R1 module, `config/data_rights.py`, or
  `clear_expired_cache` must change.
- You are tempted to add a route, scheduler, CLI, settings flag,
  migration, or index. Indexes for a hosted run are a later,
  owner-gated slice.
- You want to touch any table other than `cached_responses` and `signal`.

## 8. Done when

- `pytest -q tests/test_spec43_g4_retention_supabase.py` green in CI.
- Full `pytest` green in CI, including R1's tests (unchanged).
- `ruff check` and `ruff format --check` clean on the new files. If ruff
  is not installed on your compute, say so; CI is the check.
- Branch `feat/spec43-g4-retention-supabase` pushed as one commit. Report
  the SHA, both sabotage results, and any test you could not run.

Do not open the PR; the planning agent reviews and opens it.

Later, owner-gated (not R2): an admin or scheduled entry point, indexes on
`expires_at` and `captured_at` for a hosted run, and the decision to run
on hosted before production, mass user exposure, or a store listing.
