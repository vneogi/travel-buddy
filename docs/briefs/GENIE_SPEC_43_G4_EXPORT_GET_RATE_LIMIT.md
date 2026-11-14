# Genie brief: SPEC-43 Gap 4 slice 16 -- rate-limit GET /api/v1/me/export

Read this whole file before touching anything. It is the complete job.
If something here conflicts with your memory of an earlier brief, this
file wins. If something here is unclear, stop and ask; do not guess and
do not widen scope.

## 0. Context in one paragraph

Gap 4 data rights are on main: erase (`POST /api/v1/me/erase`) and flat
export (`GET /api/v1/me/export`, caller-only). Gap 11 added an
in-process sliding-window limiter (`monitoring/rate_limit.py`) that
counts only POST/PUT/PATCH/DELETE, so the export GET is unthrottled.
Export reads every identity table for the caller, so it is the most
expensive read a user can trigger. This slice counts that one GET path
in the limiter and nothing else. Every other GET stays uncounted, as
Gap 11 designed.

## 1. Goal and the properties that matter

1. `GET /api/v1/me/export` is counted by the limiter, per identity and
   per IP, using the same caps and window the limiter already uses.
2. Every other GET is still uncounted. In particular `/api/v1/health`
   and every trip read are unaffected.
3. The path match is exact after trailing-slash stripping, the same
   way `_EXEMPT_PATHS` is matched. Do not match by prefix.
4. The exempt list is unchanged. Export is still not exempt.
5. A 429 on export has the same body shape as any other 429:
   `{"detail": "rate_limited"}` plus `request_id` when present.

## 2. Preflight (do this first, stop if any check fails)

1. `git fetch origin`. Work from the `origin/main` SHA given in the
   message that sent you this brief. If `origin/main` has moved past
   it, say so and continue from the newer main only if it still
   contains every file in step 2; otherwise stop.
2. Confirm on that main these files exist: this brief,
   `monitoring/rate_limit.py`, `routers/me_router.py`,
   `tests/test_spec43_g11_rate.py`, `tests/test_spec43_g4_export_route.py`,
   `tests/conftest.py`, `docs/ENGINEERING_RULES.md`.
3. Confirm `tests/test_spec43_g4_export_get_rate.py` does NOT exist, and
   `origin/feat/spec43-g4-export-get-rate-limit` does not exist. If
   either exists, stop and report.
4. Create a fresh branch from that main:
   `feat/spec43-g4-export-get-rate-limit`.

Never start work from an older SHA. Check the base before you write a
line.

## 3. Read before editing (read only; these are your patterns)

- `docs/ENGINEERING_RULES.md`: R14 (ASCII), R16 (no hard-coded pytest
  totals in docs), R17 (a guard that cannot fail is not a guard).
- `monitoring/rate_limit.py` in full. Note:
  - `_COUNTED_METHODS` = POST/PUT/PATCH/DELETE.
  - `_EXEMPT_PATHS` = the two payment webhooks.
  - `RateLimitMiddleware.__call__` returns early for any method not in
    `_COUNTED_METHODS`. That early return is the only place GET is
    skipped; your change must keep every other GET on that early
    return.
  - The module docstring says "GETs and payment webhooks are not
    counted". Update that sentence to name the one exception.
- `tests/test_spec43_g11_rate.py`: the private-middleware test pattern
  (`_scope`, `_drive`, `RateLimitMiddleware(lambda s, r, t: None, ...)`).
  Copy the pattern into your new file; do not import helpers across
  test files.
- `tests/test_spec43_g4_export_route.py`: how export tests call
  `GET /api/v1/me/export` through the shared `TestClient`.
- `tests/conftest.py`: how the suite raises the limiter caps so shared
  tests do not hit 429. Understand it before you add any export GET
  test that uses the shared app.

## 4. Files you may touch

- `monitoring/rate_limit.py` (the export GET path counting only; module
  docstring sentence only)
- `tests/test_spec43_g4_export_get_rate.py` (new)

Nothing else. In particular do NOT change:

- any existing test file (do not edit, delete, or loosen a line)
- `tests/conftest.py`, `main.py`, `security.py`
- `routers/me_router.py` or any `services/data_rights_*` file
- `requirements*.txt`, `pyproject.toml` (no pins)
- any doc, any brief, `PROJECT_STATUS`, `HANDOFF`, `DOCUMENT_MAP`

Do not write a new brief or any doc. Do not start slice 17.

## 5. The change: `monitoring/rate_limit.py`

### 5.1 Constant

Add one module-level set next to `_COUNTED_METHODS` and `_EXEMPT_PATHS`:

    _COUNTED_GET_PATHS = frozenset({"/api/v1/me/export"})

Use the same trailing-slash-stripped comparison as `_EXEMPT_PATHS`.
Do not add any other path.

### 5.2 Counting rule

In `RateLimitMiddleware.__call__`, the current early return is:

    method = scope.get("method") or ""
    if method not in _COUNTED_METHODS:
        await self.app(scope, receive, send)
        return

Change the decision so the request is counted when EITHER:

- the method is in `_COUNTED_METHODS`, OR
- the method is `GET` AND the trailing-slash-stripped path is in
  `_COUNTED_GET_PATHS`.

Then keep the existing exempt check, the existing identity and IP
caps, the existing `_over_cap` calls, and the existing `_reject`
response, unchanged.

Write it as a small helper, for example `_is_counted(method, path)`,
so the rule can be tested directly. Keep the helper private.

### 5.3 Caps and window

Use the existing `MAX_REQUESTS_PER_IDENTITY`, `MAX_REQUESTS_PER_IP`, and
`RATE_WINDOW_S`. Do not add a new cap number in this slice.

Note for the report: the shared app's suite caps are set in
`conftest.py`. If an existing export test now hits 429 because of
shared app state, stop and report with the test name and the request
count; do not edit `conftest.py` and do not loosen any test.

### 5.4 Module docstring

Change the sentence "GETs and payment webhooks are not counted." to:

    GETs are not counted except GET /api/v1/me/export (Gap 4 slice 16),
    and payment webhooks are not counted.

Keep the rest of the docstring as it is. ASCII only.

## 6. Tests: `tests/test_spec43_g4_export_get_rate.py`

No network. Use a private `RateLimitMiddleware` with a stub inner app
for every limiter-level test (`max_identity=3, max_ip=100,
window_s=60` or similar), so the shared app is not poisoned. Copy the
`_scope` and `_drive` helpers from `tests/test_spec43_g11_rate.py` into
this file (do not import across test files).

Exact test names (each must exist; add more only if they add proof):

1. `test_export_get_is_counted_per_identity`
   Drive four GET `/api/v1/me/export` requests as the same debug
   identity with a cap of 3. Expect statuses `[200, 200, 200, 429]`
   and body `detail == "rate_limited"`.

2. `test_export_get_is_counted_per_ip`
   Same as 1 but rotate the debug identity on each call and keep one
   IP with a cap of 3. Expect `[200, 200, 200, 429]`.

3. `test_export_get_429_includes_request_id`
   The 429 body includes `request_id` when the scope carries one, the
   same as the existing POST 429 test does.

4. `test_other_gets_are_still_not_counted`
   Drive more GETs than the cap against `/api/v1/health`,
   `/api/v1/me/status` if it exists on main (otherwise any existing
   trip GET path from the suite), and `/api/v1/me/exportx`. Expect all
   200 (not counted), and the inner app called for each.
   Check the path exists on main before you use it; if none is
   suitable, use `/api/v1/health` and `/api/v1/me/exportx` only.

5. `test_export_path_with_trailing_slash_is_counted`
   `/api/v1/me/export/` with the same cap expects the 429 on the fourth
   request.

6. `test_export_get_is_not_exempt`
   `"/api/v1/me/export"` is not in `_EXEMPT_PATHS` after rstrip.

7. `test_stripe_webhook_still_not_counted`
   Mirror the existing webhook test, to prove slice 16 did not change
   the exempt behaviour. Five POSTs to the Stripe webhook with cap 1
   all return 200.

8. `test_is_counted_rule_table`
   Direct check of the helper: `(POST, /api/v1/x)` true; `(PUT, ...)`,
   `(PATCH, ...)`, `(DELETE, ...)` true; `(GET, /api/v1/me/export)` true;
   `(GET, /api/v1/me/export/)` true; `(GET, /api/v1/health)` false;
   `(GET, /api/v1/me/exportx)` false; `(HEAD, /api/v1/me/export)` false
   (HEAD is not counted by design; say so in the test comment).

9. `test_rate_limit_module_changes_are_ascii`
   Read `monitoring/rate_limit.py` and assert `.isascii()`.

Do not edit or delete any existing test, including the two in the
export and erase route files.

## 7. R17 sabotage (required, and must be reported)

Two sabotage runs, each restored before the next:

A. In the helper, make it return `False` for GET export (for example
   drop the GET branch). Under that sabotage these must fail:
   `test_export_get_is_counted_per_identity`,
   `test_export_get_is_counted_per_ip`,
   `test_export_path_with_trailing_slash_is_counted`,
   `test_is_counted_rule_table`.
   `test_other_gets_are_still_not_counted` must stay green.

B. In the helper, make it return `True` for every GET (drop the path
   check). Under that sabotage `test_other_gets_are_still_not_counted`
   and `test_is_counted_rule_table` must fail.

Restore the real code after each run. Confirm the file hash of
`monitoring/rate_limit.py` is identical before the first sabotage and
after the last restore. No sabotage artifact may be committed. If
in-place editing is blocked, an in-memory pytest plugin that patches the
helper is the accepted substitute; drop the plugin before the PR.

## 8. Stop rules

Stop and report instead of improvising if:

- any preflight check in section 2 fails;
- an existing test fails for a reason related to this change (for
  example a shared-app export test now gets 429);
- an existing test fails for any other reason not named in section 9;
- you feel you need to edit a file outside section 4, including
  `conftest.py`;
- you are about to count any GET other than the export path, add a
  new cap number, pin FastAPI, or add anything to `_EXEMPT_PATHS`;
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
  it failed on CI for PR #211)
- `test_today_tonight_includes_venue_name` (fails near ICT midnight)

Anything else failing is yours until proven otherwise. Confirm touched
files are ASCII only. If `ruff format --check .` fails on a file you are
not allowed to edit, stop and report; do not reformat it.

Dart / Flutter checks are not part of this slice. Do not run them.

## 10. Out of scope (record as remainders, do not build)

- Counting other GETs (trip reads, health, Ask) in the limiter
- Per-route caps or a separate export cap number
- Nested / human-readable / downloadable export
- Tombstones, retention jobs, Flutter leave / local wipe
- Pagination, in-memory `DatabaseService` export wiring
- Shared or cross-instance limiter state (process-local by design)
- Armor, Play Integrity, deploy, APK, hosted 0026
- Frontend findings F1-F4 in `UX_BACKLOG.md`

## 11. Delivery

1. Commit on `feat/spec43-g4-export-get-rate-limit` with the message:
   `SPEC-43 Gap 4 slice 16: rate-limit GET /api/v1/me/export`.
2. Push that branch. Verify the pushed SHA from the remote
   (`git ls-remote origin feat/spec43-g4-export-get-rate-limit`), not
   from your local clone.
3. Do not merge, do not deploy, do not open or edit any other branch.
   This compute has no `gh`; the reviewer opens the PR from your branch.
   Do not try to work around that.

## 12. Report (exactly these fields, in this order)

1. Base `origin/main` SHA you started from.
2. Branch name and pushed SHA (verified from the remote).
3. `pytest` last line, and the name of every failing test.
4. `ruff check`, `ruff format --check`, `git diff --check` results
   (name the ruff version).
5. Files touched (must be only those in section 4).
6. Proof the export GET is counted: the status sequence from test 1
   and test 2, and the 429 body.
7. Proof other GETs are not counted: the statuses from test 4.
8. Confirmation the exempt list and the POST/PUT/PATCH/DELETE behaviour
   are unchanged (diff of those lines).
9. The R17 tests that failed under sabotage A and B, by name, and
   confirmation the sabotage was removed and the file hash matches the
   pre-sabotage hash.
10. Anything you were unsure about, or anything you chose not to do.

Do not edit this brief, `PROJECT_STATUS`, or `HANDOFF`.
