# Genie brief: SPEC-43 Gap 4 slice R1, retention planner and bounded delete

Read this whole file before touching anything. It is the complete job.
If something here conflicts with your memory of an earlier brief, this
file wins. If something here is unclear, stop and ask; do not guess and
do not widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA.

Owning spec: `docs/specs/SPEC-43-security-privacy-and-data-governance.md`
(Gap 4 "Current fact" and the proposed-defaults table). Parent: SPEC-27
(lifecycle). Scope is backend only. CI is the gate. No phone, no Windows
laptop, no hosted deploy, no hosted migration, no scheduler.

## 0. Context

Gap 4 is partly on main: inventory, erase plan and executor, in-memory and
Supabase erase backends, the erase route, Auth delete, the 1-hour token
denylist, in-process cache purge, export plan and backends, the nested
export document, and the durable tombstone (`5c5c2b3`, migration 0027
applied on hosted 2026-11-15). What is still missing is the retention job:
expired data is not physically removed. SPEC-43 says "a cache expiry
predicate does not delete an expired row".

Verified facts on `main` (re-verify in preflight):

1. `config/settings.py`: `cache_ttl_hours: int = 24`.
2. `services/cache_service.py`: the in-memory semantic cache already drops
   expired entries on `check_cache` and `store_response`
   (`clear_expired`). That is process-local only.
3. `supabase/migrations/0001_initial_schema.sql`: `cached_responses` has
   `created_at` and `expires_at` (default now + 24 hours). No delete job
   touches it.
4. `supabase/migrations/0002_signals_core.sql`: `signal` has `captured_at`
   (client time, NOT NULL), `ingested_at` (server time), `user_id` (TEXT,
   pseudonymous), `trip_id`. No other table has a foreign key to
   `signal`. `signal` references `signal_type` and `source` only.
5. `config/data_rights.py`: `RIGHTS_MAP` lists every identity-bearing
   table with a `retention` value. Current values are `planned` for
   identity tables. `data_rights_tombstone` is `erase_exempt`. Its
   retention must never be deleted.
6. Tests already enforce the schema walk. A new identity table without a
   RIGHTS_MAP entry fails them. Do not weaken those tests.
7. `event_log` (`0001_initial_schema.sql`) has `user_id` and `created_at`,
   and no retention window is proposed for it in SPEC-43. Treat as
   reported, not deleted (see section 4).

### Owner note on windows

The SPEC-43 proposed defaults are "subject to counsel". Slice R1 encodes
them as code constants, dry-run by default. Enabling real deletion on
hosted is an owner decision and is NOT part of this slice. Put this
sentence in the module docstring: "Windows are proposals subject to
counsel review; hosted enablement is owner-only."

## 1. Goal

A pure, testable retention planner plus a bounded, dry-run-first delete
executor with an in-memory backend. Nothing runs against hosted Supabase.

Slice R1 implements exactly these windows, from SPEC-43 proposed defaults:

| Store | Column used | Window | Action in R1 |
|---|---|---|---|
| `cached_responses` (SQL private semantic cache) | `expires_at` | row is expired when `expires_at <= now` | delete expired rows |
| `signal` (identifiable behavioural signals) | `captured_at` | older than 365 days | delete rows |

Not in R1 (do not implement, do not delete, list in the report):

- `trip_states`, `trip_node`, `trip_edge`, `trip_party`, `party_member`,
  `trip_command`: trip-history 24-month inactive default needs counsel and
  advance-notice design. Stop and ask if you think they must be touched.
- Booking reference and private notes 30-day rule: needs a trip end-date
  source. Stop and ask.
- `event_log`: no window proposed. Report it as unclassified for retention
  in your summary. Do not delete it.
- Client outbox (Flutter), error ring (already done in G10), and any
  aggregate that might single out a contributor.
- The `data_rights_tombstone` table, under any circumstance.

## 2. Preflight

1. `git fetch origin`. Work from the base SHA in the message that sent
   this brief.
2. Confirm section 0 items 1 to 6 on that SHA. If any differs in a way
   that changes the plan, stop and report.
3. Confirm `services/data_rights_retention.py` does not exist and
   `origin/feat/spec43-g4-retention` does not exist.
4. Confirm no other migration in `supabase/migrations/` adds a foreign key
   to `signal` or `cached_responses`. If one does, stop and report.
5. Branch: `feat/spec43-g4-retention`.

## 3. Read before editing

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 4)
- `docs/specs/SPEC-27-app-lifecycle.md` (deletion and export context)
- `docs/ENGINEERING_RULES.md` R14, R16, R17
- `config/data_rights.py` (whole file)
- `services/data_rights_erase.py` (required tables and the executor shape)
- `services/data_rights_cache_purge.py` (in-process purge pattern)
- `services/cache_service.py` (`CacheEntry`, `clear_expired`)
- `tests/test_spec43_g4_cache_purge.py` (fixtures and style)
- Existing schema-walk tests under `tests/` (find with `rg RIGHTS_MAP tests`)

## 4. Files you may touch

- `services/data_rights_retention.py` (new). Pure planner plus executor.
  No Supabase import, no network, no logging of identifiers, ASCII only.
- `tests/test_spec43_g4_retention.py` (new).

Nothing else. Do not edit `config/data_rights.py`, `RIGHTS_MAP`,
migrations, `settings.py`, routers, existing tests, Flutter, `.env.example`,
or docs. Do not add a new dependency.

## 5. Design

### 5.1 Planner (pure)

```python
@dataclass(frozen=True)
class RetentionPolicy:
    table: str  # "cached_responses" or "signal"
    time_column: str  # "expires_at" or "captured_at"
    window: timedelta | None  # None means "delete when time_column <= now"
    expiry_column: bool  # True for expires_at semantics
```

- `POLICIES` is a module-level tuple with exactly the two entries in
  section 1. No dynamic registration.
- `cutoff_for(policy, now)`: for `captured_at`, `now - window`. For
  `expires_at`, `now`. `now` must be timezone-aware UTC; a naive datetime
  raises `ValueError`.
- A row is a candidate when `row_time < cutoff` for the window policies,
  and `row_time <= now` for the expiry policy. Be exact about the boundary
  and test it.

### 5.2 Executor

```python
def run_retention(backend, *, now, dry_run=True, batch_limit=500,
                  policies=POLICIES) -> RetentionReport
```

- `dry_run=True` by default. Dry run counts candidates per policy and
  deletes nothing.
- `batch_limit` is required to be between 1 and 5000. Outside that range
  raises `ValueError`. Each policy deletes at most `batch_limit` rows per
  call and reports `remaining` (boolean) when more are left.
- Order is deterministic (oldest time first, then primary key).
- The executor only calls `backend.count_expired(policy, cutoff)` and
  `backend.delete_expired(policy, cutoff, limit)`. No other backend method.
  No SQL string is built here.
- Returns `RetentionReport` with per-table counts, `dry_run`, `remaining`
  per table, and `now` as ISO UTC. The report carries NO user ids, no row
  ids, no text.

### 5.3 Backend protocol and in-memory backend

- `RetentionBackend` Protocol with the two methods above.
- `InMemoryRetentionBackend` in the same module: holds rows as dicts with
  the time column and an id. Used only by tests and as the reference shape
  for a later Supabase backend.
- Do NOT write a Supabase backend in this slice. It is brief R2.

### 5.4 Safety rules (these are the point; tests must prove them)

- A policy whose table is `data_rights_tombstone` is rejected at import
  time. Test it by constructing a bad policy and asserting the validator
  raises.
- Every `POLICIES` entry's table must appear in `RIGHTS_MAP` with identity
  other than `none` and `erase_exempt`. Add a test that asserts this.
- A missing or non-datetime time value on a row is skipped and counted as
  `skipped_invalid`, never deleted.
- `now` in the future is accepted, but a test shows nothing is deleted when
  `now` is far in the past (cutoff in the past).

## 6. Tests

`tests/test_spec43_g4_retention.py`. Exact test names:

1. `cutoff for captured_at policy is now minus 365 days`
2. `cutoff for expires_at policy is now`
3. `naive datetime raises ValueError`
4. `row exactly at captured_at cutoff is kept`
5. `row one second older than captured_at cutoff is a candidate`
6. `expired cached_responses row is a candidate, unexpired is kept`
7. `dry run deletes nothing and reports counts`
8. `batch_limit caps deletes per policy and reports remaining`
9. `batch_limit outside 1..5000 raises ValueError`
10. `deletion order is oldest first then primary key`
11. `invalid time value is skipped and counted, never deleted`
12. `report carries no user ids or row ids`
13. `policy on data_rights_tombstone is rejected`
14. `every POLICIES table is classified in RIGHTS_MAP with a deletable identity`
15. `executor calls only count_expired and delete_expired on the backend`
    (use a spy backend that raises on any other attribute access)
16. `hosted-safe: module does not import supabase or network libraries`
    (static check: scan the module source for `import supabase`,
    `import httpx`, `import requests`, `from supabase`)

Use fixed `now` values, never `datetime.now()`, so tests are deterministic
(R17 spirit). Put one sabotage check in your report: temporarily change
the `<` boundary to `<=` and show test 4 fails. Revert and show green.

## 7. Stop and ask

Stop and report (do not guess) if:

- Any migration adds a foreign key to `signal` or `cached_responses`.
- `cache_ttl_hours` is not 24 on the base SHA.
- A proposed window conflicts with an existing test.
- You think `trip_states`, `event_log`, or any trip table must be touched.
- The schema-walk test fails for a reason outside this slice.
- You are tempted to add a migration, a scheduler, a route, or a Supabase
  call. Those are later slices.

## 8. Done when

- `pytest -q tests/test_spec43_g4_retention.py` green in CI.
- Full `pytest` green in CI, including the schema-walk and RIGHTS_MAP
  tests (unchanged).
- `ruff` clean on the new files.
- Branch `feat/spec43-g4-retention` pushed. Report the SHA, the sabotage
  result, and the list of tables reported but not deleted (section 1).

Do not open the PR; the planning agent reviews and opens it.

Owner decisions that remain (not Genie's): confirm the 365-day signal and
24-hour cache windows with counsel; choose whether a hosted job runs at all;
choose the trip-history and booking-note rules before R3.
