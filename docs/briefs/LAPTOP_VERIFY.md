# Laptop verify -- Windows (PowerShell 5.1)

Owner-only. This is the Device Day style runbook for everything that
still needs a laptop after Device Day closed (2026-08-17). Isaac records
results in `docs/AWAITING_VERIFICATION.md`. Do not invent a pass from a
green CI job or from Genie.

PowerShell 5.1. Canonical copy: `docs/briefs/LAPTOP_VERIFY.md` on
`origin/main` after this lands.

Device Day (`docs/briefs/DEVICE_DAY.md`) is CLOSED. Do not re-apply
0011-0018. Do not re-export Dubai. Do not `VALIDATE CONSTRAINT` unless
you are deliberately doing that follow-up (it is not in this runbook).

`docs/TESTING_GUIDE.md` section 4 still mentions
`--dart-define=TB_DEBUG_USER_ID=...`. That flag was removed in SPEC-09
(`7173a3f`). Ignore it. Identity is `Authorization: Anonymous <uuid>`.

## What this day is for

Prove, on the Windows machine, in this order:

1. Repo SHA and tools
2. Backend pytest with live Supabase URL (the five integration tests must
   not skip for missing URL)
3. Migration 0019 applied on the hosted DB
4. Flutter analyze + test (including SPEC-22 render tests and PR #18
   helpers once that PR is on the SHA you checkout)
5. Four sabotage proofs (R17) -- break, watch the named test fail,
   restore, do not commit the break
6. Local API + `smoke-test.ps1`
7. Anonymous identity E2E (`TB_ALLOW_ANONYMOUS=true`, JWT secret unset)
8. Flutter UI: home reachable with real Supabase dart-defines (no
   onboarding loop), device id on profile, swap still works, visited
   control appears in the current time window, chat copy is a question

Stop and write the failure down. Do not "fix forward" past a hard stop.

## Hard stops (do not continue)

- `git pull` / checkout fails
- `pytest -q -ra` with `TB_SUPABASE_URL` set shows the five
  `test_supabase_integration` tests skipped for missing URL
- 0019 `SELECT` returns zero rows after you think you applied it
- `flutter analyze` or `flutter test` non-zero (record the first error
  block; that is the finding)
- uvicorn starts with `supabase_configured` false while you intended live
  mode (R11 -- you are on in-memory)
- `TB_SUPABASE_JWT_SECRET` is set in the uvicorn process when you are
  testing Anonymous -- JWT wins and Anonymous never runs
- You put the **service_role** key into Flutter `--dart-define`. Flutter
  gets the **anon** key only (`TB_SUPABASE_ANON_KEY`)

## Results sheet (paste back to Isaac)

Copy this into chat or into a dated AWAITING_VERIFICATION finding. SHA
and skip reasons are load-bearing. Do not write a pytest count into
PROJECT_STATUS (R16).

```
Date (ISO):
Machine:
git SHA:
Branch (main or PR #18 SHA):
PR #18 merged? yes/no

Step 0 flutter doctor (any red?):
Step 2 pytest -ra skip list:
Step 3 0019 SELECT output:
Step 4 flutter analyze exit:
Step 4 flutter test exit (and any failing test names):
Step 5 sabotage: four named tests failed when broken, passed after restore? yes/no
Step 6 smoke-test.ps1 pass/fail counts:
Step 7 Anonymous curl HTTP codes (v4 / v1 / no-flag):
Step 8a Chrome no supabase defines -- reached / ? yes/no
Step 8b Chrome WITH anon dart-defines -- onboarding loop? yes/no
Step 8c Profile device id (UUID v4 shape, not empty):
Step 8d Swap: itinerary row changed? yes/no
Step 8e Visited / NOW visible on a node in the current window? yes/no/not-tried
Step 8f Chat empty-state text (paste exactly):

Unexpected skips:
Anything you did not run, and why:
```

---

## Pickup -- load .env into this PowerShell process

Same helper as Device Day. Run at the start of every new shell.

```powershell
cd C:\Users\ariav\travel-buddy   # or wherever this clone lives
$ErrorActionPreference = 'Stop'

git pull origin main
if ($LASTEXITCODE -ne 0) { throw "git pull failed" }

Get-Content .env | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq '' -or $line.StartsWith('#')) { return }
    $eq = $line.IndexOf('=')
    if ($eq -lt 1) { return }
    $name = $line.Substring(0, $eq).Trim()
    $value = $line.Substring($eq + 1).Trim()
    Set-Item -Path "Env:$name" -Value $value
}
if (-not $env:TB_SUPABASE_URL) { throw "TB_SUPABASE_URL missing" }
if (-not $env:TB_SUPABASE_KEY) { throw "TB_SUPABASE_KEY missing" }
Write-Host "creds present URL=$($env:TB_SUPABASE_URL.Substring(0,[Math]::Min(40,$env:TB_SUPABASE_URL.Length)))..."
```

If PR #18 (`fix/itinerary-signal-auth-ci`) is **not** merged, Flutter
steps 4, 5, 8b, 8e must run on that branch or you will not be testing
the auth-gate / current-window / replacement_ref work:

```powershell
git fetch origin
git checkout origin/fix/itinerary-signal-auth-ci
if ($LASTEXITCODE -ne 0) { throw "checkout PR branch failed" }
git log -1 --oneline
```

If it **is** merged, stay on `main` and record `git log -1 --oneline`.

---

## Step 0 -- tools

```powershell
python --version
# Expect 3.11 or 3.12, not the Windows Store stub.

flutter --version
flutter doctor
# Record anything red. Continue if only Android licenses / VS, etc.
# Hard stop if Flutter SDK missing.

git log -1 --format="%H %s"
```

One-time if needed:

```powershell
pip install -r requirements.txt
pip install -r requirements-dev.txt
cd mobile
flutter pub get
if ($LASTEXITCODE -ne 0) { throw "flutter pub get failed" }
cd ..
```

`intl: ^0.19.0` was dropped on PR #18 because it fought
`flutter_localizations`. If `pub get` fails on `main` before that merge,
you are on a SHA that cannot resolve. Checkout the PR branch.

---

## Step 1 -- do not touch live schema yet

Confirm 0011-0018 are already applied (Device Day). Optional, SQL editor:

```sql
SELECT key FROM signal_type
WHERE key IN ('prompt_dismissed')
ORDER BY 1;
```

Expect **zero rows** before Step 3. If you already see `prompt_dismissed`,
skip the apply and record "0019 already present".

---

## Step 2 -- pytest, twice

### 2a In-memory (URL still set from .env -- this will hit live)

For a true in-memory run you must **unset** the URL in this process only:

```powershell
$savedUrl = $env:TB_SUPABASE_URL
$savedKey = $env:TB_SUPABASE_KEY
Remove-Item Env:TB_SUPABASE_URL
Remove-Item Env:TB_SUPABASE_KEY
$env:TB_DEBUG = 'true'
pytest -q -ra
# Restore immediately
$env:TB_SUPABASE_URL = $savedUrl
$env:TB_SUPABASE_KEY = $savedKey
```

Expect the five tests in `tests/test_supabase_integration.py` to skip
with reason containing creds / URL. Any other skip is a finding (R8).
Do not copy the passed-count into PROJECT_STATUS.

### 2b Live (required)

```powershell
if (-not $env:TB_SUPABASE_URL) { throw "URL missing -- reload .env" }
$env:TB_DEBUG = 'true'
pytest -q -ra
```

Hard stop if those five tests skip. Paste the full `-ra` skip section
into the results sheet.

---

## Step 3 -- apply 0019 (`prompt_dismissed`)

File: `supabase/migrations/0019_prompt_dismissed.sql`

In the **Supabase SQL editor** (same path as Device Day 0011-0018):

1. Paste the INSERT from that file (not the rollback comment).
2. Run.
3. Proof query:

```sql
SELECT key, category, value_kind
FROM signal_type
WHERE key = 'prompt_dismissed';
```

Expect one row: `prompt_dismissed` / `explicit_user` / `json`.

Hard stop if zero rows. Do not emit `prompt_dismissed` from a device
until this is true -- the server will reject an unregistered type.

Re-run the signal-types drift test:

```powershell
pytest tests/test_signal_types.py -q -ra
if ($LASTEXITCODE -ne 0) { throw "signal_types tests failed after 0019" }
```

---

## Step 4 -- Flutter analyze and test

Working directory **must** be `mobile` (the token-literals test accepts
repo root as a fallback, but analyze paths are from `mobile`).

```powershell
cd C:\Users\ariav\travel-buddy\mobile
flutter pub get
if ($LASTEXITCODE -ne 0) { throw "pub get failed" }

flutter analyze --no-fatal-infos
if ($LASTEXITCODE -ne 0) { throw "analyze failed -- paste first 40 lines" }

flutter test
if ($LASTEXITCODE -ne 0) { throw "flutter test failed -- paste failing names" }
cd ..
```

If analyze is a wall of pre-existing **warnings** and zero **errors**,
record both counts. Do not locally add `--no-fatal-warnings` unless Isaac
says so after seeing the log. Errors always fail.

Named tests that must exist on the PR #18 SHA (hard stop if "No tests
ran"):

```powershell
cd mobile
flutter test --name "picks the same node_id with a new venue"
flutter test --name "node 10:00 for 90 minutes contains 10:30"
flutter test --name "anonymous user can stay on /"
flutter test --name "resetBackoff must not wipe attempts"
cd ..
```

If the last name does not match, run:

```powershell
cd mobile
flutter test test/offline_sync_test.dart --name "resetBackoff"
cd ..
```

SPEC-22 files that must be collected (on `main` after `1b9b1b3`):

```
test/render/fact_view_test.dart
test/render/interruption_budget_test.dart
test/render/prompt_dismiss_adapter_test.dart
test/render/token_literals_test.dart
```

---

## Step 5 -- sabotage (R17). Restore every time.

Do this on the PR #18 SHA (or main after merge). After each substep:
the named test is **red**, then `git checkout -- <file>` (or
`git restore --source=HEAD -- <file>`), then the same test is **green**.
Do not commit. Do not leave a broken tree.

### 5a replacement_ref

File: `mobile/lib/features/itinerary/replacement_ref.dart`

Change `n.nodeId == originalNodeId` to `n.nodeId != originalNodeId`.

```powershell
cd mobile
flutter test --name "picks the same node_id with a new venue"
# Expect FAIL
cd ..
git checkout -- mobile/lib/features/itinerary/replacement_ref.dart
cd mobile
flutter test --name "picks the same node_id with a new venue"
# Expect PASS
cd ..
```

If the test still PASSES after the `!=` edit, the guard is dead. Stop.
That is R17. Tell Isaac.

### 5b current window

File: `mobile/lib/features/itinerary/current_window.dart`

Replace the body of `nodeIsCurrentWindow` with `return false;`

```powershell
cd mobile
flutter test --name "node 10:00 for 90 minutes contains 10:30"
# Expect FAIL, then restore
cd ..
git checkout -- mobile/lib/features/itinerary/current_window.dart
```

### 5c auth redirect

File: `mobile/lib/routing/redirect_for_auth.dart`

Inside `redirectForAuth`, after `if (!supabaseReady) return null;`, add:

```
if (!hasSession && location != '/onboarding') return '/onboarding';
```

```powershell
cd mobile
flutter test --name "anonymous user can stay on /"
# Expect FAIL, then restore
cd ..
git checkout -- mobile/lib/routing/redirect_for_auth.dart
```

If you sabotage `app_router.dart` instead of this helper and the test
stays green, production is not calling the helper. Stop.

### 5d resetBackoff

File: `mobile/lib/offline/offline_database.dart`

In `resetBackoff`, put `attempts = 0` back into the UPDATE.

```powershell
cd mobile
flutter test test/offline_sync_test.dart --name "resetBackoff"
# Expect FAIL, then restore
cd ..
git checkout -- mobile/lib/offline/offline_database.dart
```

```powershell
git status
# Must be clean before Step 6
```

---

## Step 6 -- local API + smoke-test.ps1

**Auth mode for smoke:** JWT secret **unset**, `TB_DEBUG=true`. The
script sends `X-Debug-User-Id`, not Anonymous.

```powershell
# In the shell that will run uvicorn (leave it running)
if ($env:TB_SUPABASE_JWT_SECRET) {
    Remove-Item Env:TB_SUPABASE_JWT_SECRET
    Write-Host "unset TB_SUPABASE_JWT_SECRET for debug/anonymous laptop API"
}
$env:TB_DEBUG = 'true'
# Keep TB_SUPABASE_URL and TB_SUPABASE_KEY so supabase_configured is true
python -c "from config.settings import settings; print('debug', settings.debug); print('allow_anonymous', settings.allow_anonymous); print('jwt_secret_set', bool(settings.supabase_jwt_secret)); print('supabase_url_set', bool(settings.supabase_url))"
```

Expect: debug True, jwt_secret_set False, supabase_url_set True.
`allow_anonymous` may still be False for smoke.

Second window:

```powershell
cd C:\Users\ariav\travel-buddy
uvicorn main:app --reload --port 8000
```

Watch startup. It prints booleans, never secrets. If
`supabase_configured` is false, you are in-memory -- hard stop for any
test you wanted live.

Third window:

```powershell
cd C:\Users\ariav\travel-buddy
.\scripts\smoke-test.ps1
```

Record PASS/FAIL lines. The script is allowed to use the debug header.
A failure here is a finding even if Flutter is fine.

---

## Step 7 -- Anonymous E2E (curl)

Stop and restart uvicorn with Anonymous enabled. JWT still unset.

```powershell
$env:TB_ALLOW_ANONYMOUS = 'true'
$env:TB_DEBUG = 'true'
if ($env:TB_SUPABASE_JWT_SECRET) { Remove-Item Env:TB_SUPABASE_JWT_SECRET }
python -c "from config.settings import settings; print('allow_anonymous', settings.allow_anonymous); print('jwt_secret_set', bool(settings.supabase_jwt_secret))"
# Expect allow_anonymous True, jwt_secret_set False
```

Restart uvicorn so it picks up the env (reload may not see a new env var
from another shell -- start it in **this** shell).

Use a **v4** UUID (the 13th hex digit is 4):

```powershell
$uuid = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
$base = 'http://localhost:8000/api/v1'

# 7a health (public)
curl.exe -s -w "`n%{http_code}" "$base/health"

# 7b Anonymous accepted
curl.exe -s -w "`n%{http_code}" "$base/user/status" -H "Authorization: Anonymous $uuid"

# 7c v1 UUID rejected (13th digit is 1) -- must not be 200
curl.exe -s -w "`n%{http_code}" "$base/user/status" -H "Authorization: Anonymous aaaaaaaa-aaaa-1aaa-8aaa-aaaaaaaaaaaa"
```

Expect 7b **200** with a user payload. Expect 7c **4xx**, not 200.

7d fail-closed: in a new shell **without** `TB_ALLOW_ANONYMOUS`, restart
uvicorn, repeat 7b. Expect **401** with detail about Anonymous not
enabled. Then put the flag back for Flutter.

Create a trip as that device (proves write path, not just status):

```powershell
$uuid = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
curl.exe -s -w "`n%{http_code}" -X POST "$base/trip/create" `
  -H "Authorization: Anonymous $uuid" `
  -H "Content-Type: application/json" `
  --data-binary "{`"start_date`":`"2026-10-02T00:00:00Z`",`"initial_mood`":`"exploratory`"}"
```

PowerShell 5.1 mangles quotes. Safer -- write a temp JSON file (same
pattern as `smoke-test.ps1`):

```powershell
$uuid = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
$tmp = Join-Path $env:TEMP 'tb_create_trip.json'
'{"start_date":"2026-10-02T00:00:00Z","initial_mood":"exploratory"}' | Out-File -Encoding ascii $tmp -Force
curl.exe -s -w "`n%{http_code}" -X POST "http://localhost:8000/api/v1/trip/create" `
  -H "Authorization: Anonymous $uuid" `
  -H "Content-Type: application/json" `
  --data-binary "@$tmp"
```

Expect 200 and a `trip_id`. Save that id for Step 8.

---

## Step 8 -- Flutter UI (Chrome first)

Windows Chrome talks to `localhost`, not `10.0.2.2` (that is the Android
emulator alias).

Uvicorn must be running with `TB_ALLOW_ANONYMOUS=true` and JWT unset.

### 8a No Supabase dart-defines (dev gate off)

```powershell
cd C:\Users\ariav\travel-buddy\mobile
flutter run -d chrome --dart-define=TB_API_BASE_URL=http://localhost:8000
```

Expect: app opens on `/` (Trips), **not** stuck on onboarding.
Open Profile. Device ID is a UUID, not blank, not `null`.

### 8b WITH anon dart-defines (the softlock test)

Use the **anon/publishable** key from Supabase Settings > API, never
service_role.

```powershell
flutter run -d chrome `
  --dart-define=TB_API_BASE_URL=http://localhost:8000 `
  --dart-define=TB_SUPABASE_URL=https://YOUR_PROJECT.supabase.co `
  --dart-define=TB_SUPABASE_ANON_KEY=YOUR_ANON_KEY
```

On PR #18 / merged SHA: Get Started / Skip must land on `/` and **stay**.
If it bounces back to onboarding, the router fix is not on this SHA.

On `main` **before** that merge: a loop is the known bug. Record it.
Do not "fix" by omitting the dart-defines and calling 8b passed.

Sign Out on profile currently `go('/onboarding')`. From onboarding, Get
Started must still return to `/` and stay (after the fix).

### 8c Device id stable

Kill Chrome, run 8a or 8b again. Device id on Profile must match the
first run (secure storage). If it changes every launch, SPEC-09 client
is broken.

### 8d Swap on itinerary

Need a `trip_id` (Step 7 create, or create from the app if home can).
Home may be a shell -- if you cannot open a trip from UI, Chrome URL:

`http://localhost:xxxxx/trip/PASTE_TRIP_ID`

(exact port from `flutter run` output).

On a non-locked card, swipe/swap. The venue name on that row must
change. Locked LPM-style row must not swap.

You will not see `replacement_ref` in the UI. After swap, open
Profile > Sync Status. Outbox should not sit in a tight fail loop.
Optional: if a row is visible, you are not proving the JSON field --
Step 5a is what proves the lookup. This step only proves swap still
reflows.

### 8e NOW / visited (needs PR #18)

Create or use a trip whose **first unlocked node's** `scheduled_start`
window contains **now** (UTC vs local: Dart compares instants, so a
node starting "now" in the API's UTC timestamps should work).

The demo `/trip/create` stamps start at 09:00 on `start_date`. If you
created `2026-10-02` in Step 7, NOW will not show in August. Either:

- POST create with `start_date` = today's UTC morning, or
- Wait / do not mark 8e passed

Expect: NOW treatment and an "I visited" control on that card. Tap it.
That is `visited_confirmed`. Sync status should show a queued/synced
signal, not a 401 storm.

If 8e is not tried, write `not-tried` and why. Do not mark it passed
because the unit test passed.

### 8f Chat copy

Open `/trip/PASTE_TRIP_ID/chat` with an empty thread. Paste the
placeholder text verbatim. It must **not** contain `Swap the next stop`.
It should look like a question (hours / nearby). Sending a message may
return cached LIGHT text; that is known. Do not expect the itinerary to
change from chat.

---

## Step 9 -- optional Android emulator

Only if Chrome 8a-8c passed. Use `10.0.2.2` not localhost:

```powershell
cd C:\Users\ariav\travel-buddy\mobile
flutter run -d emulator-5554 --dart-define=TB_API_BASE_URL=http://10.0.2.2:8000
```

Same checks as 8a. If the emulator cannot reach the host, that is a
Windows firewall finding, not an app bug.

---

## What you are not doing today

- Loader-valid `data/dubai_uae.json`
- `VALIDATE CONSTRAINT` on 0015/0017
- SPEC-12 driver card
- Wiring `cacheTrip` into itinerary load
- Email/Supabase sign-in
- Changing Genie's PR while this run is in flight (pick one SHA at Step 0)

---

## After the day

Paste the results sheet to Isaac. Isaac updates
`docs/AWAITING_VERIFICATION.md` with a dated finding (SHA, what ran,
what skipped, what failed). He does not put a pytest count into
PROJECT_STATUS.

If 0019 applied, say so in that finding so nobody applies it twice.
If sabotage 5c stayed green after breaking the helper, that blocks
merge/trust of PR #18 even if CI is green.
