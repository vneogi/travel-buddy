# Genie brief: Gap 10 IAM part A -- how we work, then fail-closed unset token

This is the open job. Stop when part A gates are green. Do not
start part B, SSO, retention, Armor, Play Integrity, SQL cache,
`derived_feature`, hosted 0026, Flutter, deploy, or an APK.

If a later chat pastes part B, ignore it until planning says
part A landed on `main`.

## Who you are

You are the **execution agent** (Genie Code, Databricks). You
write application code and tests. You run pytest and ruff. You
open a pull request. You do not merge. You do not deploy. You
do not build an APK. You do not apply hosted SQL.

You are not the planning agent. You are not the project owner.

## Who else is

**Planning** (Cursor agent on the owner's machine) writes specs,
briefs, sequence, and living docs. It reviews your **diff**, not
your summary. It must not claim pytest passed unless it watched
pytest. After you open the PR, stop and wait.

**Owner** (Vikrant) owns the laptop, phone, Flutter, live
Postgres, Cloud Run, and GitHub merge. Laptop results and hosted
SQL are owner-only. Do not invent them.

## How a slice moves

1. Planning writes a brief under `docs/briefs/`.
2. You implement on a new branch from the SHA in this brief.
3. You run the gates, sabotage the named test, restore, push, open
   one PR.
4. Planning reviews the diff. Owner says merge, or planning squash-
   merges Python-only work after that.
5. Planning updates living docs. You do not edit HANDOFF,
   PROJECT_STATUS, DOCUMENT_MAP, RELEASE_READINESS, this brief, or
   part B.

Chat is not storage. If this window dies, the brief still is.

## Documents to read (only these)

Read in this order. Do not repo-walk. Do not load SPEC-43
end-to-end. Do not load Flutter.

1. `docs/WAYS_OF_WORKING.md` -- sections 1, 2, 5, 8 (roles,
   evidence, proving a guard, scope).
2. `docs/ENGINEERING_RULES.md` -- R3, R14, R16, R17.
3. `docs/specs/SPEC-43-security-privacy-and-data-governance.md`
   -- **Gap 10 only** (status, solution bullets on administrator
   IAM, acceptance "unreachable without administrator
   authorization"). Skip other gaps.
4. `docs/specs/SPEC-05-observability.md` -- B.3 and the security
   note that the ring is currently debug-gated with no token.
5. `routers/debug_router.py` (whole file, short).
6. `config/settings.py` -- `debug` field and `env_prefix`.
7. `tests/test_observability.py` --
   `test_debug_errors_returns_200_when_debug_on` and
   `test_debug_errors_returns_404_when_debug_off`.
8. `tests/conftest.py` -- it sets `TB_DEBUG=true`. Do not add
   `TB_DEBUG_ADMIN_TOKEN` there.

Do not read `security.py` this part (part B). Do not edit
`monitoring/error_log.py` or `monitoring/redact.py`.

## Hard stops

- Python only. No Dart, no Gradle, no APK.
- No CREATE TABLE. No live Postgres. Do not apply 0026.
- Hosted `TB_DEBUG` stays off (`K_SERVICE` refuse already on
  `main`). Do not change `_lifespan`.
- ASCII in new `.py` comments and docstrings (R14). Markdown you
  do not touch.
- Do not report a test count (R16). Last pytest line only.
- Do not merge. Do not force-push `main`.
- Databricks pre-push may false-positive on ancient postgres
  strings. Still push; planning uses GitHub. Never print a PAT.
- Do not "fix" `test_today_tonight_includes_venue_name`.
- If pytest is red on a named test you did not mean to change,
  stop. Do not weaken the test to go green.

## Goal of part A only

Today GET/DELETE `/api/v1/debug/errors` return the ring whenever
`settings.debug` is True, including pytest (`TB_DEBUG=true`) with
no extra secret.

Part A does **not** add the admin header. Part B will.

Part A adds `TB_DEBUG_ADMIN_TOKEN` and **fail-closes when it is
unset**: even with debug on, GET/DELETE return 404 and no
`"errors"` key.

When the token **is** configured (length >= 16), keep today's
unauthenticated dump. That is deliberate. Part B will require
`X-Debug-Admin-Token`. Do not add that header now.

## Scope

Base branch: latest `main` (`c7b9b5a`).

Create and push: `feat/spec43-g10-iam-a`

### 1. Setting

`debug_admin_token: Optional[str] = None` on Settings
(`TB_DEBUG_ADMIN_TOKEN`). Default empty.

A token is **configured** only when it is a string of length
>= 16 after strip. None, `""`, whitespace, and `"x" * 8` are
unset.

`.env.example`: empty `TB_DEBUG_ADMIN_TOKEN=` plus one ASCII
comment: required to expose the debug ring; never set on Cloud
Run. Do not commit a real token.

Add a tiny helper (debug_router or `monitoring/debug_admin.py`)
`admin_token_configured(token: Optional[str]) -> bool`. Router
and tests must call that helper, not copy the length check.

### 2. Router

Keep 404 when `settings.debug` is False.

When debug is True and `admin_token_configured` is False: 404
`{"detail": "Not found"}`. Do not return the ring.

When debug is True and configured: existing GET/DELETE bodies,
still no admin header.

Do not log the setting. Do not accept query `token=`.

### 3. Named test

Add `tests/test_spec43_g10_iam.py`. No widgets. No live Postgres.

Exact name:

`test_debug_errors_404_when_admin_token_unset`

Monkeypatch `settings.debug` True and
`settings.debug_admin_token` to `None`. GET
`/api/v1/debug/errors` is 404. JSON has no `"errors"` key.
Repeat with `""` and with `"xxxxxxxx"` (8 x). Then monkeypatch
token to `g10-admin-canary-token` (exact 22 chars). GET with no
admin header is 200 and has `"errors"` (old dump; part B will
change this).

Also: DELETE with unset token is 404.

Update `test_debug_errors_returns_200_when_debug_on`:
monkeypatch `settings.debug_admin_token` to
`g10-admin-canary-token` so it still gets 200 with no admin
header (part A still dumps when configured). Do not leave a
200 assertion on an unset token. Keep
`test_debug_errors_returns_404_when_debug_off`.

### 4. R17 sabotage

Exact edit: treat unset as configured (skip the new 404).

`test_debug_errors_404_when_admin_token_unset` must fail (GET
returns 200 with `"errors"`). Restore before the PR. Do not
delete the test. Do not sabotage redaction or Cloud Run refuse.

## Gates

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

If `backend/.venv` exists, use that interpreter. No Flutter.

## Report

SHA, branch, pytest last line, files touched. Named test in the
report must be `test_debug_errors_404_when_admin_token_unset`.
Do not merge. Do not edit living docs or this brief.
