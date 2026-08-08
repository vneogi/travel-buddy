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
