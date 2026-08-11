# Engineering Rules

Hard-won rules. Each one exists because the corresponding bug reached a commit.

## R1. Never escape Dart string interpolation

Writing `\$variable` instead of `$variable` inside a Dart string produces a
literal `$variable` and silently breaks the value. This has happened THREE
times in this repo:

1. `core/api_client.dart` — broke the base URL and the `Bearer` token.
   Every authenticated API call failed.
2. `features/itinerary/itinerary_screen.dart:128` — broke the `ValueKey`,
   so every row got an identical key and the heart never filled in.
3. `offline/sync_engine.dart` — caught pre-commit.

**After ANY write to a `.dart` file, run:**

    grep -rn '\\\$' mobile/lib

Expected output: only the two price strings in `upgrade_screen.dart`.
Anything else is a bug — fix before committing.

**The Python tell:** if a tool emits `SyntaxWarning: invalid escape
sequence '\$'` while writing Dart, you have already introduced this bug.
Never dismiss that warning.

## R2. Grep for what you claim you added

Twice, an edit was reported as landed when it was not:

- `home_screen.dart` FIX 1: only the `api_exception.dart` import was added
  (left unused); the try/catch was never written. Caught by noticing the
  diff was `+1 line`.
- The `$$` dollar-quoting fix in the SQL migration did not land on the
  first attempt.

**Before claiming a change is complete, grep the file for the new code and
paste the matching line(s) with line numbers.** A diff stat that looks too
small is a red flag, not a coincidence.

## R3. Tests passing is not verification

Two of the worst defects in this repo shipped with a green test suite:

- **Auth bypass:** `get_current_user_id` checked `X-Debug-User-Id` before
  the JWT secret, with `debug=True` by default — one header impersonated
  any user. Tests passed.
- **Error classification:** `sync_engine` matched on `errorStr.contains('401')`,
  which never matched `ApiClient`'s typed exceptions, so 401/422 retried
  forever. Tests passed because the tests threw `Exception('401 ...')`
  instead of the real exception type.

**Tests must throw/construct the same types production throws.** When a
test fails against real configuration, suspect the test before "fixing"
the application. The auth bypass was introduced precisely by fixing the
app to satisfy a test that was failing for a legitimate reason.

## R4. In-memory tests do not prove the Supabase path

`database_service` (in-memory) and `supabase_service` are separate
implementations of the same interface. A green suite against in-memory
says nothing about Supabase. This is how SPEC-03 shipped without its
migration, and how `supabase_service` was once missing `record_signal`
entirely.

**Any change touching persistence must change BOTH backends, and any new
table needs a migration in the same commit.**

## R5. One registry, one source of truth

Never mirror a registry by hand across two files. If a list must exist in
both Python and SQL, define it once in Python and add a test that asserts
the migration file contains exactly those values.

## R6. Never initialize a service with placeholder credentials

Calling `Supabase.initialize` with dummy values to silence an assertion
converts a loud startup failure into a silent runtime one. Guard on
config presence instead (`Env.supabaseUrl`/`supabaseAnonKey`) and degrade
explicitly.

## R7. Verify the test actually tests the thing

The first airplane-mode durability drill was meaningless: the build was
using `adb reverse` over USB, and airplane mode does not disable USB.
Four hearts posted instantly to a "disconnected" server. The drill only
became valid after rebuilding against the laptop's LAN IP.

**For any offline/failure drill, first confirm the failure mode is real** —
e.g. see requests actually stop — before trusting a pass.

## R8. Report passed AND skipped, with a reason per skip

A skip asserts nothing. "All green" is only true when the skip count is
expected and every skip has a named `skipif`. Eight tests once degraded
from passing to skipped because a test dependency (`pytest-asyncio`)
vanished from the ephemeral environment — the summary line still read as
healthy, and the affected tests covered the riskiest code in the repo
(SPEC-03 party_context stamping).

**Rules:**
- Never report "all green" without stating the skip count and reason.
- Use `--strict-markers` so unknown markers error instead of silently
  becoming no-ops.
- Set `filterwarnings = error::pytest.PytestUnhandledCoroutineWarning`
  so an async test without a runner fails loudly.
- Use `-ra` to always print skip/xfail reasons in the summary.
- Pin test deps in `requirements-dev.txt` so ephemeral computes
  reproduce the same environment.

## R9. A schema that cannot express a fact will never error

The `signal` table referenced venues only. A dish-level observation was
not "unsupported" — it was unrepresentable, and nothing failed to say so.
Missing data looks identical to absent behavior.

Before building a capture flow, verify the schema can represent the fact
you intend to capture. Prefer generalizing a subject reference
(`entity_type` + `entity_id`) over adding a parallel table per subject.

## R10. Verify from the remote ref, not the workspace working copy

The workspace edit tool (`editAsset`) has shown a pattern of reporting
success while silently reverting writes. In commit #62 and #64, three
separate edits were reported as applied but did not persist:

1. The `value_kind` drift guard replacement — reported done, file unchanged
2. A `DISH_SIGNAL_TYPES` import addition — reported done, reverted by next read
3. Appended test functions — reported done, lost on next edit cycle

The failure mode is uniquely dangerous: the tool reports success →
verification reads the (unchanged) file → content passes because it
matched *before* the edit → false confidence that the edit landed.

**Rules:**
- After `commit_and_push`, verify critical changes from the pushed tree:
  `git show origin/main:<path> | grep <expected_string>`
  (or in Databricks: `pull` then filesystem `grep`, confirming `isClean=true`)
- Never rely on `editAsset` success status alone for multi-line replacements
- When `editAsset` fails silently, fall back to direct filesystem writes
  (`executeCode` with `open(path, 'w')` or `sed -i`)
- The pattern is: old_text match succeeds, replacement write is discarded,
  file content after call == file content before call
- If a file read shows content you just "replaced," assume reversion and
  re-apply through the filesystem

**Amendment: local working copy is the execution surface, not origin/main.**

Verifying from `origin/main` proves the remote tree is correct. But
`supabase db push`, `python`, `flutter build`, and every other local
command reads the user's working copy — not the remote. A correct remote
and a stale local produce the same failure as never having fixed the bug.

Any instruction to run a local command must begin with:

    git pull origin main
    # Then confirm the specific fix is present:
    grep -n "venues_rag" supabase/migrations/0005_entity_ref_generalization.sql
    # or on Windows:
    findstr /n "venues_rag" supabase\migrations\0005_entity_ref_generalization.sql

Only after the grep confirms the expected content should the command run.
This is not paranoia — it closes the gap between "verified on remote" and
"executing locally" that cost us the `venue` → `venues_rag` fix arriving
on GitHub but potentially not being pulled before `db push`.


## R11. A success response is not proof of persistence

`SyncEngine` logged `accepted=1 duplicates=0` for five signals while
`db_provider` pointed at the in-memory backend — every one was discarded
on restart. Confirm writes by querying the destination store, never by
trusting an API acknowledgement or an adjacent success signal.

## R12. Never widen the root log level for a debug flag

`logging.basicConfig(level=DEBUG if settings.debug else INFO)` set the
ROOT logger to DEBUG, so `TB_DEBUG=true` made LiteLLM, `openai`, and
`httpx` dump full request bodies, 1536-float embedding arrays, and the
masked `Authorization` header to stdout. Raise the level on your own
loggers only; pin third-party loggers explicitly.

## R13. Both backends must satisfy one interface

`DatabaseService` and `SupabaseService` are independent implementations of
the same contract, and divergence is only caught at runtime:
`record_signal` and `get_valid_signal_types` were each missing from
`supabase_service`, and `add_venue` differed in arity — crashing startup
once the provider resolved to Supabase. `tests/test_backend_parity.py`
asserts signature compatibility so divergence fails in CI.

## R14. Non-ASCII content silently blocks editAsset

Any file containing an em-dash (U+2014), emoji, or box-drawing character
will reject edits while reporting success. The failure signature:

- `editAsset` returns `changed: true`
- `git diff` is empty -- the write was silently discarded
- Subsequent `readAssetById` shows the file unchanged

The tool matches the `old_text` correctly (proving it found the content)
but the write-back fails when the file's byte stream includes non-ASCII.

**Workaround:** create the new content at a temporary path with
`createAsset` (e.g. `docs/FOO.new.md`), then `git rm` the original and
`git mv` the temp file into place.

**Prevention:** all new source files and documentation must be pure ASCII.
Use `--` instead of em-dash, `->` instead of arrows, and never use emoji
or box-drawing characters. Run the ASCII guard in `test_docs_hygiene.py`
before committing.

## R15. Workspace writes are blocked outside the asset tools

The safety filter denies all direct filesystem mutations to `/Workspace`
paths:

- `open(path, 'w')` / `open(path, 'wb')` -- denied
- `shutil.copy2(src, workspace_path)` -- denied
- `sed -i` on workspace paths -- denied
- `subprocess` writing to workspace -- denied
- `os.remove`, `os.rename`, `pathlib.write_text` -- denied

Only the Databricks-managed tools (`createAsset`, `editAsset`, `runGit`)
can mutate workspace files.

**Consequence:** new-file work (via `createAsset`) is cheap; edits to
existing files are expensive. Bias the queue toward new modules over
refactors of existing ones. When an existing file blocks edits due to
non-ASCII content (R14), rebuild it from scratch at a temp path.

## R16. A document that duplicates derivable state will drift

`PROJECT_STATUS.md` mirrored `git log` and test counts by hand and was
wrong in six ways within five days, while claiming to be the single source
of truth:

- Reported 53 tests when the suite had 117
- Claimed behavioral signals "NOT STARTED" when 8 were registered
- Said the backend "still uses in-memory" after the Supabase flip shipped
- Said migration 0003 was "unwritten and blocking" after it was applied
- Marked SPEC-03 partial after it was complete
- Marked entity generalization not started after 0005 landed it

**Rule:** never hand-mirror something a command can produce. Write the
command (e.g. `run pytest -q`) and let the reader execute it for a live
answer. A stale number in a doc is worse than no number -- it erodes trust
in the entire file.

Dated observations and verification results belong in
`docs/AWAITING_VERIFICATION.md`, which is a dated log by design and is
expected to go stale.
