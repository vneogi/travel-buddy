# Engineering Rules

Hard-won rules. Each one exists because the corresponding bug reached a commit.

## R1. Never escape Dart string interpolation

Writing `\$variable` instead of `$variable` inside a Dart string produces a
literal `$variable` and silently breaks the value. This has happened THREE
times in this repo:

1. `core/api_client.dart` -- broke the base URL and the `Bearer` token.
   Every authenticated API call failed.
2. `features/itinerary/itinerary_screen.dart:128` -- broke the `ValueKey`,
   so every row got an identical key and the heart never filled in.
3. `offline/sync_engine.dart` -- caught pre-commit.

**After ANY write to a `.dart` file, run:**

    grep -rn '\\$' mobile/lib

Expected output: only the two price strings in `upgrade_screen.dart`.
Anything else is a bug -- fix before committing.

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
  the JWT secret, with `debug=True` by default -- one header impersonated
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

**For any offline/failure drill, first confirm the failure mode is real** --
e.g. see requests actually stop -- before trusting a pass.

## R8. Report passed AND skipped, with a reason per skip

A skip asserts nothing. "All green" is only true when the skip count is
expected and every skip has a named `skipif`. Eight tests once degraded
from passing to skipped because a test dependency (`pytest-asyncio`)
vanished from the ephemeral environment -- the summary line still read as
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
not "unsupported" -- it was unrepresentable, and nothing failed to say so.
Missing data looks identical to absent behavior.

Before building a capture flow, verify the schema can represent the fact
you intend to capture. Prefer generalizing a subject reference
(`entity_type` + `entity_id`) over adding a parallel table per subject.

## R10. Verify from the remote ref, not the workspace working copy

The workspace edit tool (`editAsset`) has shown a pattern of reporting
success while silently reverting writes. In commit #62 and #64, three
separate edits were reported as applied but did not persist:

1. The `value_kind` drift guard replacement -- reported done, file unchanged
2. A `DISH_SIGNAL_TYPES` import addition -- reported done, reverted by next read
3. Appended test functions -- reported done, lost on next edit cycle

The failure mode is uniquely dangerous: the tool reports success ->
verification reads the (unchanged) file -> content passes because it
matched *before* the edit -> false confidence that the edit landed.

**Rules:**
- After `commit_and_push`, verify critical changes from the pushed tree:
  `git show origin/main:<path> | grep <expected_string>`
  (or in Databricks: `pull` then filesystem `grep`, confirming `isClean=true`)
- Never rely on `editAsset` success status alone for multi-line replacements
- The pattern is: old_text match succeeds, replacement write is discarded,
  file content after call == file content before call
- If a file read shows content you just "replaced," assume reversion. Do
  NOT re-apply through the filesystem -- those writes are denied. Switch to
  git plumbing (R15) and do not retry `editAsset` a second time.

**Amendment: local working copy is the execution surface, not origin/main.**

Verifying from `origin/main` proves the remote tree is correct. But
`supabase db push`, `python`, `flutter build`, and every other local
command reads the user's working copy -- not the remote. A correct remote
and a stale local produce the same failure as never having fixed the bug.

Any instruction to run a local command must begin with:

    git pull origin main
    # Then confirm the specific fix is present:
    grep -n "venues_rag" supabase/migrations/0005_entity_ref_generalization.sql
    # or on Windows:
    findstr /n "venues_rag" supabase\migrations\0005_entity_ref_generalization.sql

Only after the grep confirms the expected content should the command run.
This is not paranoia -- it closes the gap between "verified on remote" and
"executing locally" that cost us the `venue` -> `venues_rag` fix arriving
on GitHub but potentially not being pulled before `db push`.


## R11. A success response is not proof of persistence

`SyncEngine` logged `accepted=1 duplicates=0` for five signals while
`db_provider` pointed at the in-memory backend -- every one was discarded
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
`supabase_service`, and `add_venue` differed in arity -- crashing startup
once the provider resolved to Supabase. `tests/test_backend_parity.py`
asserts signature compatibility so divergence fails in CI.

## R14. The ASCII convention, and what it is actually for

**This rule was over-broad for months and is now narrowed. The original text
claimed that any file containing an em-dash would silently reject edits.
That was disproved twice: `editAsset` matched and wrote non-ASCII Lao venue
JSONs successfully, and git plumbing bypasses the write path entirely. The
convention survives, but for different and smaller reasons than the ones it
was introduced with.**

Two places where non-ASCII does real damage, both now guarded by
`tests/test_docs_hygiene.py`:

1. **Inside a `COMMENT ON ... IS '...'` body in any `.sql` file.** The text
   persists into `pg_description` in the live database. A non-UTF-8 client
   then renders it as mojibake indistinguishable from corruption, and no file
   guard can see it afterwards because the damage is in the database rather
   than the repo. This is not theoretical: an em-dash in `0010` was applied to
   production and needed migration `0016` to correct, because fixing the file
   fixes only future builds.
2. **In `.py` comments and docstrings.** Keeps a mojibake round-trip visible
   as a diff instead of silent corruption. There is also a concrete Windows
   failure: check and cross marks in `test_backend_parity` output crashed on
   a cp1252 console, which is a correctness reason rather than a style one.

**Deliberately exempt, and each exemption is a decision rather than an
oversight:**

- **String literals in `.py`.** A degree sign in a temperature format is
  correct code, and this product renders Lao and Arabic. A blanket ban would
  fight the code rather than protect it.
- **`.dart` files.** Display strings in a client are legitimately non-ASCII;
  localisation belongs in ARB files, not under a byte guard.
- **`--` comments in `.sql`.** Inert. They never reach the database.
- **`data/` JSON.** Stored as `\uXXXX` escapes, which is pure ASCII on disk
  and readable via `scripts/format_venue_json.py`.
- **Markdown on the allowlist**, which may only shrink, never grow.

**When a test genuinely needs native script**, the prescribed form is a
`\uXXXX` escape in a string literal. The answer is never a new allowlist
entry.

**A file guard cannot see the database.** After applying migrations, scan
`pg_description` for non-ASCII directly; that is the only way to know whether
a comment landed badly before the guard existed.

## R15. Workspace writes are filtered, but git plumbing is not

The safety filter denies direct filesystem mutation of `/Workspace` paths:

- `open(path, 'w')` / `open(path, 'wb')` -- denied
- `shutil.copy2(src, workspace_path)` -- denied
- `sed -i` on workspace paths -- denied
- `subprocess` writing to workspace -- denied
- `os.remove`, `os.rename`, `pathlib.write_text` -- denied

**The original conclusion drawn from this -- that only `createAsset`,
`editAsset` and `runGit` can mutate workspace files -- was wrong.** Git
plumbing writes arbitrary bytes and is not filtered:

    git hash-object -w        # content into the object store
    git update-index          # point the index at it
    git checkout-index -f     # materialise it in the working tree

This is the canonical path for writing a file whose content is awkward for
the asset tools, including anything non-ASCII, and it retired the
delete-and-recreate workaround this rule used to prescribe.

**One trap remains.** After a plumbing write, `editAsset` operates from a
stale cache and can silently revert what plumbing just wrote. Do not mix the
two mechanisms on one file inside one task. Pick plumbing, finish the file,
commit, and only then go back to the asset tools.

**Consequence for the queue:** new-file work is still cheaper than editing
existing files, but the gap is far smaller than this rule once claimed, and
"the file has non-ASCII" is no longer a reason to rebuild it from scratch.

**When `runGit` itself is unavailable the workspace cannot be mutated at
all**, which is a different failure and is covered below.

**When runGit itself is unavailable, the workspace cannot be mutated at
all.** `runGit` has failed with `Git folder (Repo) has invalid type`
(`RESOURCE_DOES_NOT_EXIST`) after a session died mid-task, leaving the
compute able to create files but unable to delete, move, or commit them.
Repair is a re-clone of the Git folder, not a retry. Because of this,
documentation and whole-file rewrites are pushed through the GitHub API
by the planning agent, and the compute is reserved for code plus pytest.

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

## R17. A guard that cannot fail is not a guard

This defect class keeps reaching a commit, in a new disguise each time, which
is why it gets its own rule rather than staying a footnote to R7. The
instances below are recorded because the disguise is the interesting part: in
every one, the assertion looked reasonable in review.

1. **Asserting on constants instead of the payload.** `test_no_silent_key_drop`
   compared two module-level constants to each other. Both were correct; the
   dictionary the loader actually built was not, and four curated fields were
   being dropped on every run while the test stayed green.
2. **Asserting on a helper the test itself calls.** The first
   `venue_external_id` test built a record via the helper and asserted on the
   result. It passed for days while nothing in the production path ever called
   that helper, so the table had no writer at all.
3. **Keying a safety guard off English prose.** The raw-meat check looks for
   the word "raw" in a description. Rewording the description silently
   disables a safety guard, and nothing fails.
4. **Substring matching text that also appears in a comment.**
   `test_..._price_band_check_is_not_valid` asserts `"NOT VALID" in sql`.
   Delete `NOT VALID` from the constraint and the test still passes, because
   the file's own explanatory comment contains the phrase. Proven by
   sabotaging the DDL and watching the assertion hold.

Three more arrived in a single day, all of them tests written specifically to
guard a defect that had just been found, and all three passed with the defect
reintroduced.

5. **A test that supplies the value production is supposed to compute.** The
   provenance test built the dict itself and handed it to the storage layer.
   The bug was the router discarding it. Deleting the argument from the router
   left the test green.
6. **A test whose fake cannot express the failure.** The race test asserted
   that a conditional `UPDATE` wrote nothing, against a fake that only applied
   updates when a filter was present. Remove the filter and the fake wrote
   nothing either -- for the opposite reason. The assertion was right and the
   double was wrong.
7. **A sabotage proof run against the file rather than the test.** Five
   passing structural tests in the same file hid one inert test, because the
   suite went red and nobody checked which assertion produced it.
8. **An empty observation counted as a clean bill of health.** The 0011
   dual-column decision script treated "neither `name_local` nor
   `names_local` present" as safe to apply. When the input TSV was empty
   (failed `psql` password prompt), both were absent for the wrong reason,
   and the script printed `DECISION: safe`. Absence of evidence is not
   evidence of absence: refuse empty / auth-noise / missing-core-column
   dumps before evaluating the dual-column branch.

**Rules:**

- Assert on the value the production path produces, reached the way
  production reaches it. If the test has to call a helper to get the value,
  ask what calls that helper in real life, and if the answer is "nothing",
  that is the finding.
- Reaching the failure the way production reaches it is the stronger form of
  the rule above, and it is the one that catches instance 5. A test that
  constructs the input itself proves the code downstream of the bug works. Go
  in through the endpoint, the loader, the router -- whatever the real caller
  is.
- Before trusting a new guard, break the thing it guards and watch it fail.
  A guard never observed failing has not been tested; it has been written.
- Watch *which* guard fails, by name. A red suite is not the proof; the
  specific assertion you believed covered the case is. Instance 7 passed the
  weaker version of this rule and still shipped an inert test.
- A test double is part of the guard. If the fake cannot represent the
  failure, the assertion above it cannot catch the failure, however well
  written it is. When sabotage produces the expected pass, suspect the double
  before the assertion.
- Strip comments before matching against source text, or match the
  construct rather than a string that may appear anywhere in the file.
- Prefer a guard that enumerates both sides and compares sets over one that
  looks for the presence of a substring. Set equality names what diverged;
  a substring check cannot.
- A negative observation ("X not found") is only meaningful if the scan
  actually ran over a real population. Empty input, auth failure text, or a
  missing required key must refuse before the "not found ⇒ safe" branch.
- A guard hardcoded to one filename does not cover the next file. If the
  claim is "this can never happen again", the guard has to scan for the
  pattern rather than check the one place it is known to occur.
