# Genie brief: test clock hygiene -- two clock-dependent tests

Read this whole file before touching anything. It is the complete job.
If something here conflicts with your memory of an earlier brief, this
file wins. If something here is unclear, stop and ask; do not guess and
do not widen scope.

## 0. Context in one paragraph

The CI `test` and `pytest` jobs are red on every PR because of one
test, and sometimes two. Both are test defects, not product defects:

1. `tests/test_spec41_window_packing.py::TestAPIAtomicity::test_sparse_create_with_limited_hours_succeeds`
   posts a range create with the literal date `date(2026, 11, 2)`.
   The range-create path in `routers/trip_router.py` rejects a
   `start_date` before today in the destination timezone
   (`past_dates`, 422). Since 2026-11-03 this test fails every run.
2. `tests/test_spec25_field_intents.py::TestHTTPTodayTonight::test_today_tonight_includes_venue_name`
   schedules its node at real now plus 30 minutes and asserts, as a
   fixture precondition, that now and the node share the same
   Luang Prabang (UTC+7) date. Between 16:30 and 17:00 UTC that is
   false, so the fixture fails.

Because these are always or often red, a real regression hides behind
"the known failure". This slice makes both tests clock-independent.
It changes test code only.

## 1. Goal and the properties that matter

1. `test_sparse_create_with_limited_hours_succeeds` uses a start and
   end date derived from today in the destination timezone of `GEO`,
   a fixed number of days ahead, so it can never be in the past. It
   keeps its single-day range, its venue pool, its mock, and its
   assertion (`status_code == 200`) exactly.
2. `test_today_tonight_includes_venue_name` keeps its meaning (a
   pending node that is still running today appears in the
   today/tonight answer) but no longer depends on the wall clock not
   being near Luang Prabang midnight.
3. No product code changes. No assertion is loosened, skipped, or
   xfailed. No other test changes.
4. After this slice, the full suite has no expected failures. The
   "known failures" list in future briefs becomes empty.

## 2. Preflight (do this first, stop if any check fails)

1. `git fetch origin`. Work from the `origin/main` SHA given in the
   message that sent you this brief. If `origin/main` has moved past
   it, say so and continue from the newer main only if it still
   contains every file in step 2; otherwise stop.
2. Confirm on that main these files exist: this brief,
   `tests/test_spec41_window_packing.py`,
   `tests/test_spec25_field_intents.py`, `routers/trip_router.py`,
   `services/ask_service.py`, `docs/ENGINEERING_RULES.md`.
3. Confirm `origin/fix/test-clock-hygiene` does not exist. If it
   does, stop and report.
4. Confirm the two tests are still written as described in section 0
   (literal `date(2026, 11, 2)` for the first; `real_now +
   timedelta(minutes=30)` plus the same-ICT-date precondition for the
   second). If either has already changed, stop and report.
5. Create a fresh branch from that main: `fix/test-clock-hygiene`.

Never start work from an older SHA. Check the base before you write a
line.

## 3. Read before editing (read only)

- `docs/ENGINEERING_RULES.md`: R14 (ASCII), R16, R17.
- `routers/trip_router.py`: the range-create date validation
  (`reversed_dates`, `past_dates`, the 90-day sanity bound). Note that
  "today" is computed with `datetime.now(tz=ZoneInfo(REGIONS[geo_region].timezone)).date()`.
- `services/ask_service.py`: `format_today_tonight`. Note the two
  rules it applies: the node's destination-local date must equal
  now's destination-local date, and the node counts as remaining
  while `now_utc < scheduled_start + duration`. Also the
  `TODAY_TONIGHT` branch of `handle_ask`, which uses
  `kwargs.get("now_utc") or datetime.now(tz=timezone.utc)`.
- `tests/test_spec40_guided_create.py::_future_date` and
  `tests/test_spec44_phase_a.py` `_FUTURE_START`: existing patterns
  for relative dates. Match their style.

## 4. Files you may touch

- `tests/test_spec41_window_packing.py` (only the one test in 5.1,
  plus an import line if needed)
- `tests/test_spec25_field_intents.py` (only the `TestHTTPTodayTonight`
  fixture in 5.2, plus an import line if needed)

Nothing else. In particular do NOT change:

- any product code (`routers/**`, `services/**`, `agents/**`,
  `config/**`, `monitoring/**`, `models/**`)
- any other test in those two files, or any other test file
- `tests/conftest.py`, `.github/**`, requirements, docs, briefs,
  `mobile/**`, `data/**`

Do not add a freezegun or time-machine dependency. Do not write a new
brief or any doc. Do not start another slice.

## 5. The changes

ASCII only. Keep each change small and readable.

### 5.1 `test_sparse_create_with_limited_hours_succeeds`

Replace the literal date with a date computed from today in the
destination timezone of `GEO`, 7 days ahead:

    trip_day = datetime.now(ZoneInfo(REGIONS[GEO].timezone)).date() + timedelta(days=7)

and use `trip_day.isoformat()` for both `start_date` and `end_date`.
The file already imports `datetime`, `timedelta`, `ZoneInfo`, and
`REGIONS`; reuse those imports. Do not change anything else in the
test: same rows, same mock, same headers, same assertion and message.

Why 7 days: far enough that a slow run near midnight cannot make it
"past", and well inside the 90-day sanity bound.

### 5.2 `TestHTTPTodayTonight._setup`

Schedule the node at real now itself, not 30 minutes ahead:

    real_now = datetime.now(tz=timezone.utc)
    node_start = real_now

Keep `duration_minutes=60`, `status=PENDING`, and everything else in
the `TripNode`. Keep the same-ICT-date precondition assertion (it now
holds by construction, and it documents the property). Update the
fixture comment to say why: the node is in progress (started at now,
ends one hour later), so `format_today_tonight` counts it as
remaining, and because it starts at the same instant as now it always
shares now's Luang Prabang date. The only remaining window is the
milliseconds between the fixture and the request crossing Luang
Prabang midnight; say that in one line of the comment.

Do not change `test_today_tonight_includes_venue_name` itself.

## 6. Proof (required, and must be reported)

These tests are about the clock, so prove the fix against the clock
without waiting for midnight. Use throwaway scripts or in-memory
pytest plugins only; no repo file may keep them.

A. Sparse create. Run the test with `routers.trip_router`'s clock
   seen as 2026-12-31 (for example a throwaway plugin that patches
   the `datetime` the route module uses so `now()` returns a fixed
   aware instant). Show that the OLD literal-date body gets 422
   `past_dates` and the NEW relative body gets 200. If patching the
   route's clock is not possible without editing product code, say so
   and instead show the new date is `>= today` in the destination
   timezone plus the normal green run.

B. Today/tonight. With a throwaway script (no network, no DB), call
   `format_today_tonight` directly with:
   - `real_now = 2026-11-14 16:45:00 UTC` (23:45 in Luang Prabang)
   - a node built the OLD way (`real_now + 30 min`) and a node built
     the NEW way (`real_now`), each `duration_minutes=60`,
     `status="pending"`, `geo_region="luang_prabang_laos"`,
     `venue_name` distinct
   - `now_utc = real_now + 2 seconds` (the request a moment later)
   Show the OLD node is excluded and the NEW node is included. Repeat
   at `real_now = 2026-11-14 08:00:00 UTC` and show both are included
   (control).

Report the outputs of A and B.

## 7. Stop rules

Stop and report instead of improvising if:

- any preflight check in section 2 fails;
- a test other than these two fails, for any reason;
- you feel you need to edit product code, `conftest.py`, CI config,
  or any file outside section 4;
- you are tempted to skip, xfail, or loosen either test, or to add a
  time-mocking dependency;
- you find a third clock-dependent test failing. Name it in the
  report; do not fix it in this slice.

Never "fix" an unrelated failure, never force-push over another
branch.

## 8. Gates

Run from the repo root, with `backend/.venv` if it exists. Use
`ruff==0.16.3` (CI pin).

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

Expected result: zero failures. There are no known failures for this
slice; the two that used to be known are the ones you are fixing. If
`ruff format --check .` fails on a file you are not allowed to edit,
stop and report; do not reformat it. Confirm touched files are ASCII.

Dart / Flutter checks are not part of this slice. Do not run them.

## 9. Out of scope (record as remainders, do not build)

- The `postgres-proof` CI job (its pgvector install step fails)
- Other tests with literal past dates on paths that do not validate
  past dates (they pass today; leave them)
- Any product change to past-date validation or today/tonight logic
- A shared test clock helper or a time-mocking dependency
- Frontend findings F1-F4, Gap 4 remainders, deploy, APK

## 10. Delivery

1. Commit on `fix/test-clock-hygiene` with the message:
   `tests: make sparse-create and today-tonight tests clock-independent`.
2. Push that branch. Verify the pushed SHA from the remote
   (`git ls-remote origin fix/test-clock-hygiene`), not from your
   local clone.
3. Do not merge, do not deploy, do not open or edit any other branch.
   This compute has no `gh`; the reviewer opens the PR from your
   branch.

## 11. Report (exactly these fields, in this order)

1. Base `origin/main` SHA you started from.
2. Branch name and pushed SHA (verified from the remote).
3. `pytest` last line, and the name of every failing test (expected:
   none).
4. `ruff check`, `ruff format --check`, `git diff --check` results
   (name the ruff version).
5. Files touched (must be only those in section 4), with the diff
   line counts.
6. The exact new lines in each test (paste them).
7. Proof A output.
8. Proof B output (both the 16:45 UTC case and the 08:00 UTC
   control).
9. Confirmation no product file, no other test, and no CI file has a
   diff.
10. Anything you were unsure about, or anything you chose not to do.

Do not edit this brief, `PROJECT_STATUS`, or `HANDOFF`.
