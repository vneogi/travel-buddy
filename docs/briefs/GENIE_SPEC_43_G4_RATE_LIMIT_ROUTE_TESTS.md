# Genie brief: SPEC-43 Gap 4 slice 15 -- fix erase/export rate-limit route tests

Read this whole file before touching anything. It is the complete job.
If something here conflicts with your memory of an earlier brief, this
file wins. If something here is unclear, stop and ask; do not guess and
do not widen scope.

## 0. Context in one paragraph

Gap 4 erase (`POST /api/v1/me/erase`) and flat export
(`GET /api/v1/me/export`) are on main. Two tests that prove those
paths are registered and not rate-limit-exempt fail on CI:

- `test_erase_route_counts_toward_the_rate_limit`
- `test_export_route_is_not_exempt_from_the_rate_limiter`

Root cause (verified): the tests flatten `app.routes` as if every entry
were a prefixed `APIRoute` with an iterable `.methods`. CI installs
unpinned `fastapi>=0.115.0` (current releases are 0.16x). Recent FastAPI
keeps included routers as wrapper nodes; `.methods` can be `None`, and
inner paths are unprefixed. The product is fine: erase POST is counted
by Gap 11, neither path is in `_EXEMPT_PATHS`, and sibling HTTP tests in
the same files still pass. This slice only fixes the two tests so they
enumerate routes through a FastAPI-stable mechanism.

## 1. Goal and the one property that matters

The two named tests must prove, without depending on FastAPI's private
route-tree shape:

1. Erase and export paths are not in `rate_limit._EXEMPT_PATHS`.
2. Erase is registered as POST and export as GET at their full
   `/api/v1/me/...` paths.
3. Erase still asserts `"POST" in rate_limit._COUNTED_METHODS` (product
   fact today).

Do not change the limiter. Do not start counting GET. Do not pin FastAPI.

## 2. Preflight (do this first, stop if any check fails)

1. `git fetch origin`. Work from the `origin/main` SHA given in the
   message that sent you this brief. If `origin/main` has moved past
   it, say so and continue from the newer main only if it still
   contains every file in step 2; otherwise stop.
2. Confirm on that main these files exist: this brief,
   `monitoring/rate_limit.py`, `routers/me_router.py`,
   `tests/test_spec43_g4_erase_route.py`,
   `tests/test_spec43_g4_export_route.py`,
   `docs/ENGINEERING_RULES.md`.
3. Confirm `origin/feat/spec43-g4-rate-limit-route-tests` does not
   exist. If it exists, this slice may already be done: stop and report.
4. Create a fresh branch from that main:
   `feat/spec43-g4-rate-limit-route-tests`.

Never start work from an older SHA. Check the base before you write a
line.

## 3. Read before editing (read only; these are your patterns)

- `docs/ENGINEERING_RULES.md`: R14 (ASCII), R16 (no hard-coded pytest
  totals in docs; this slice writes no docs), R17 (a guard that cannot
  fail is not a guard).
- `monitoring/rate_limit.py`: `_COUNTED_METHODS` is
  POST/PUT/PATCH/DELETE only; `_EXEMPT_PATHS` is the two payment
  webhooks only. Module docstring: GETs are not counted. Leave this
  file untouched.
- The two failing tests as they stand on main (quote for orientation):

      # erase
      routes = {(r.path, m) for r in app.routes
                for m in getattr(r, "methods", set())}
      assert (ERASE_PATH, "POST") in routes

      # export
      routes = {(r.path, m) for r in app.routes
                for m in getattr(r, "methods", set())}
      assert (EXPORT_PATH, "GET") in routes

  `getattr(r, "methods", set())` still returns `None` when the
  attribute exists and is `None`, so the comprehension raises
  `TypeError` or misses the prefixed path.

## 4. Files you may touch

- `tests/test_spec43_g4_erase_route.py`
- `tests/test_spec43_g4_export_route.py`

Nothing else. In particular do NOT change:

- `monitoring/rate_limit.py`, `tests/conftest.py`, `main.py`
- `routers/me_router.py` or any `services/data_rights_*` file
- `requirements.txt`, `requirements-dev.txt`, `requirements-prod.txt`,
  `pyproject.toml` (no FastAPI pin in this slice)
- any other test file
- any doc, any brief, `PROJECT_STATUS`, `HANDOFF`, `DOCUMENT_MAP`

Do not write a new brief or any doc. Do not start a GET-export
rate-limit product slice.

## 5. The fix

### 5.1 Shared enumeration (copy into both test files; do not create a
shared test helper module)

Add a small helper in each of the two test modules (duplicate is fine;
do not add a new shared test util file):

```python
def _registered_http_routes(application) -> set[tuple[str, str]]:
    """Return {(path, METHOD), ...} via OpenAPI, not app.routes shape."""
    paths = application.openapi().get("paths") or {}
    out: set[tuple[str, str]] = set()
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method in item:
            m = str(method).upper()
            if m in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
                out.add((path, m))
    return out
```

Why OpenAPI: it is FastAPI's public surface, returns full mounted
paths, and does not depend on whether `include_router` flattens
`APIRoute` nodes. Do not use `app.routes` flattening. Do not use
`iter_route_contexts` unless OpenAPI is unavailable in this pin and
you stop and report first (it should be available).

### 5.2 Rewrite only the two failing tests

Keep every other test in both files byte-identical in behaviour. No
drive-by refactors, renames, or assertion loosens elsewhere.

**`test_erase_route_counts_toward_the_rate_limit`** must still assert,
in this order:

1. `ERASE_PATH.rstrip("/")` is not in
   `{p.rstrip("/") for p in rate_limit._EXEMPT_PATHS}`.
2. `"POST" in rate_limit._COUNTED_METHODS`.
3. `(ERASE_PATH, "POST")` is in `_registered_http_routes(app)`.

**`test_export_route_is_not_exempt_from_the_rate_limiter`** must still
assert, in this order:

1. `EXPORT_PATH.rstrip("/")` is not in the same exempt set.
2. `(EXPORT_PATH, "GET")` is in `_registered_http_routes(app)`.

Hard rules for the export test (unchanged from slice 14):

- Do NOT assert that GET is counted.
- Do NOT assert that GET is uncounted.
- Do NOT edit `monitoring/rate_limit.py` or `tests/conftest.py` to
  make a stronger assertion pass.

Do not add new test names. Do not delete other tests. Do not mark
anything xfail or skip.

## 6. R17 sabotage (required, and must be reported)

Exact temporary edit: in both test files, change
`_registered_http_routes` so it always returns an empty set (for
example `return set()` as the first line of the body).

Under that sabotage:

- `test_erase_route_counts_toward_the_rate_limit` must fail on the
  `(ERASE_PATH, "POST")` assertion.
- `test_export_route_is_not_exempt_from_the_rate_limiter` must fail on
  the `(EXPORT_PATH, "GET")` assertion.

The exempt / `_COUNTED_METHODS` asserts may still pass; that is fine.
Restore the real helper body before the PR. No sabotage artifact may
be committed. If in-place editing is blocked, an in-memory pytest
plugin that patches `_registered_http_routes` to return `set()` is the
accepted substitute; drop the plugin before the PR.

## 7. Stop rules

Stop and report instead of improvising if:

- any preflight check in section 2 fails;
- an existing test outside these two fails for a reason related to
  this change;
- an existing test fails for any other reason not named in section 8;
- you feel you need to edit a file outside section 4;
- you are about to count GET in the limiter, pin FastAPI, or add a
  path to `_EXEMPT_PATHS`;
- OpenAPI does not list `/api/v1/me/erase` or `/api/v1/me/export`
  (that would be a product registration bug; stop);
- you are about to write a brief, a doc, or a second slice.

Never "fix" an unrelated failure, never skip or xfail a test, never
loosen an assertion, never force-push over another branch.

## 8. Gates

Run from the repo root, with `backend/.venv` if it exists. Use
`ruff==0.16.3` (CI pin). A newer ruff is not the gate.

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

Known pre-existing failures. These are not yours; do not touch them:

- `test_sparse_create_with_limited_hours_succeeds` (hard-coded date)
- `test_today_tonight_includes_venue_name` (fails near ICT midnight)

After this slice, the two rate-limit route tests named in section 0
must be green. Anything else failing is yours until proven otherwise.
Confirm touched files are ASCII only. If `ruff format --check .` fails
on a file you are not allowed to edit, stop and report; do not
reformat it.

Dart / Flutter checks are not part of this slice. Do not run them.

## 9. Out of scope (record as remainders, do not build)

- Counting GET (or specifically GET export) in
  `monitoring/rate_limit.py` -- separate Gap 4 / Gap 11 product slice
- Pinning FastAPI in requirements files
- Nested / human-readable / downloadable export
- Tombstones, retention jobs, Flutter leave / local wipe
- Pagination, in-memory DatabaseService export wiring
- Armor, Play Integrity, deploy, APK, hosted 0026
- Frontend findings F1-F4 in `UX_BACKLOG.md`

## 10. Delivery

1. Commit on `feat/spec43-g4-rate-limit-route-tests` with the message:
   `SPEC-43 Gap 4 slice 15: stable OpenAPI route checks for erase/export rate-limit tests`.
2. Push that branch. Verify the pushed SHA from the remote
   (`git ls-remote origin feat/spec43-g4-rate-limit-route-tests`),
   not from your local clone.
3. Do not merge, do not deploy, do not open or edit any other branch.
   This compute has no `gh`; the reviewer opens the PR from your
   branch. Do not try to work around that.

## 11. Report (exactly these fields, in this order)

1. Base `origin/main` SHA you started from.
2. Branch name and pushed SHA (verified from the remote).
3. `pytest` last line, and the name of every failing test.
4. `ruff check`, `ruff format --check`, `git diff --check` results
   (name the ruff version).
5. Files touched (must be only those in section 4).
6. Confirmation both named tests pass, and that OpenAPI listed
   `(ERASE_PATH, POST)` and `(EXPORT_PATH, GET)`.
7. Confirmation `monitoring/rate_limit.py` was not modified (diff
   empty for that path).
8. Confirmation no FastAPI pin was added.
9. The R17 tests that failed under sabotage, by name, and
   confirmation the sabotage was removed.
10. Anything you were unsure about, or anything you chose not to do.

Do not edit this brief, `PROJECT_STATUS`, or `HANDOFF`.
