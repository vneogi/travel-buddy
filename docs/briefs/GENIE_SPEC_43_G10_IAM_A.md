# Genie brief: Gap 10 IAM part A -- how we work, then fail-closed unset token

Landed on `main` as `56ebc00` (PR #148). Do not re-implement this
slice. Part B landed as `17fb0e4` (PR #150). Remainder: retention.
Do not start SSO, retention, Armor, Play Integrity, SQL cache,
`derived_feature`, hosted 0026, Flutter, deploy, or an APK.

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
   -- **Gap 10 only**.
4. `docs/specs/SPEC-05-observability.md` -- B.3 and the security
   note.
5. `routers/debug_router.py`.
6. `config/settings.py` -- `debug` and `debug_admin_token`.
7. `tests/test_observability.py`.
8. `tests/conftest.py` -- `TB_DEBUG=true`. Do not add
   `TB_DEBUG_ADMIN_TOKEN` there.

## Part A on main

Unset/short `TB_DEBUG_ADMIN_TOKEN` -> GET/DELETE
`/api/v1/debug/errors` 404 even when debug is on. Configured
token (>= 16 chars after strip) still dumped without a header
until part B.
