# Laptop verify -- Windows (PowerShell 5.1)

Owner-only. This is the canonical laptop regression runbook for the shipped
October spine (SPEC-09, SPEC-22, SPEC-12, SPEC-10, SPEC-04, and post-spine
hardening) on Windows with live credentials.

This remains the laptop regression runbook. It is not the final phone field
test. After SPEC-36 merges, SPEC-37 requires a hosted HTTPS backend and an
installed phone artifact that works with the laptop and USB disconnected.

PowerShell 5.1. Canonical copy: `docs/briefs/LAPTOP_VERIFY.md` on `main`.

Device Day (`docs/briefs/DEVICE_DAY.md`) is CLOSED. Do not re-apply
0011-0024. Hosted sentinels for every repository migration through 0024 were
verified by 2026-09-06. Do not re-export Dubai. Do not `VALIDATE CONSTRAINT`
on 0015/0017 (that remains a separate non-blocking follow-up). The canonical
ledger and recheck SQL are in `docs/HOSTED_STATE.md`.

Identity is `Authorization: Anonymous <uuid>`. Never pass the removed
`TB_DEBUG_USER_ID` dart-define.

## What this day verifies

Prove, on the Windows machine, in this order:

1. Repo SHA and tools on `main`
2. Hosted migration sentinels still match `docs/HOSTED_STATE.md` (read-only)
3. Backend pytest with live Supabase URL (all 292 tests pass, including live Supabase integration tests)
4. Flutter analyze + test (all 92 unit and widget tests pass with 0 warnings)
5. Sabotage proofs (R17) -- break, watch the named test fail,
   restore, do not commit the break
6. Local API + `smoke-test.ps1`
7. Anonymous identity E2E (`TB_ALLOW_ANONYMOUS=true`, JWT secret unset)
8. Flutter UI verification on Windows desktop or Android (Chrome is optional
   for layout only):
   - 8a: Dev gate / Home on `/`
   - 8b: Real anon Supabase defines -- no onboarding redirect loop
   - 8c: Profile device ID (UUID v4 format, persisted)
   - 8d: Live swap on itinerary reflows timeline
   - 8e: Visited / NOW badge on current-window node
   - 8f: Chat empty-state is a question (not a swap promise)
   - 8g: SPEC-12 Driver Card: native script, landmark, coordinates, no fare
     claim, no screenshot instruction, one-tap confirm
   - 8h: SPEC-10 Booking Anchors: `+ Add Booking` in AppBar, paste auto-fill, locked booking card with icon & badge
   - 8i: SPEC-04 rescue removal: no Shield icon; hotel booking keeps Driver Card action
   - 8j: Offline Itinerary Cache: load trip, stop API, reload screen -> renders cached itinerary with `"Offline: showing saved itinerary"` banner

Stop and write the failure down if a step fails. Do not "fix forward" past a hard stop.

## Hard stops (do not continue)

- `git pull` fails or working directory has uncommitted regressions
- Any hosted migration sentinel in `docs/HOSTED_STATE.md` returns false
- `pytest -q -ra` with `TB_SUPABASE_URL` set shows any failure (all 292 tests must pass)
- `flutter analyze` or `flutter test` non-zero
- uvicorn starts with `supabase_configured` false while you intended live
  mode (R11 -- you are on in-memory)
- `TB_SUPABASE_JWT_SECRET` is set in the uvicorn process when you are
  testing Anonymous -- JWT wins and Anonymous never runs
- You put the **service_role** key into Flutter `--dart-define`. Flutter
  gets the **anon** key only (`TB_SUPABASE_ANON_KEY`)

## Results sheet

Copy this into chat or into a dated `docs/AWAITING_VERIFICATION.md` finding:

```
Date (ISO):
Machine: Windows (PowerShell 5.1)
git SHA:
Branch: main

Step 0 flutter doctor:
Step 2 Hosted migration sentinels all true? yes/no:
Step 3 pytest -ra skip/pass status (confirm 292 passed, 5 Supabase tests included):
Step 4 flutter analyze exit (expect 0 errors, 0 warnings):
Step 4 flutter test exit (expect 92 passed):
Step 5 sabotage proofs (named tests failed when broken, passed after restore):
Step 6 smoke-test.ps1 pass/fail counts:
Step 7 Anonymous curl HTTP codes (v4 / v1 / flag-off):
Step 8a Windows/Android no supabase defines -- reached / ? yes/no
Step 8b Windows/Android WITH anon dart-defines -- onboarding loop? yes/no
Step 8c Profile device id (UUID v4 shape, stable on reload):
Step 8d Swap: itinerary row changed? yes/no
Step 8e Visited / NOW visible on node in current window:
Step 8f Chat empty-state text:
Step 8g Driver Card: native script + coordinates; no fare; Maps pass/fail:
Step 8h Booking Anchors: Add Booking sheet auto-fills, card shows locked badge? yes/no
Step 8i Rescue removal: Shield absent and hotel Driver Card action present? yes/no
Step 8j Offline Cache: stopping API renders cached itinerary with offline banner? yes/no

Unexpected skips:
Anything you did not run, and why:
```

---

## Pickup -- load .env into this PowerShell process

Run at the start of every new PowerShell terminal:

```powershell
cd C:\Users\ariav\travel-buddy   # or wherever this clone lives
$ErrorActionPreference = 'Stop'

git checkout main
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
@(
    'TB_SUPABASE_URL',
    'TB_SUPABASE_KEY',
    'TB_GOOGLE_MAPS_API_KEY',
    'TB_OPENWEATHER_API_KEY'
) | ForEach-Object {
    $value = (Get-Item "Env:$_" -ErrorAction SilentlyContinue).Value
    if ([string]::IsNullOrWhiteSpace($value)) { "MISSING $_" } else { "SET $_" }
}
```

Do not print values or paste `.env` into chat. Maps and OpenWeather were
provider-verified from this laptop on 2026-09-06. Rerun their safe summary-only
checks only after rotation or when diagnosing a provider failure; commands are
in `docs/HOSTED_STATE.md`. Use `curl.exe`, not PowerShell's `curl` alias.

---

## Step 0 -- tools & dependencies

```powershell
python --version
# Expect 3.11 or 3.12

flutter --version
flutter doctor
# Hard stop if Flutter SDK missing

git log -1 --format="%H %s"
```

Install/verify python & dart dependencies:

```powershell
pip install -r requirements.txt
pip install -r requirements-dev.txt
cd mobile
flutter pub get
if ($LASTEXITCODE -ne 0) { throw "flutter pub get failed" }
cd ..
```

---

## Steps 1 and 2 -- read-only hosted-state recheck

Do not execute migration files again. Open `docs/HOSTED_STATE.md`, run its
"Recheck the hosted Supabase sentinels" SQL in the Supabase SQL Editor, and
confirm every sentinel is true. Confirm the `hybrid_venue_search` arguments
include `filter_geo_region text`.

If a sentinel is false, stop and record the discrepancy. Do not repair it by
guessing or by replaying every migration.

---

## Step 3 -- pytest (live Supabase backend)

With the hosted sentinels confirmed, run the full test suite against your live
Supabase project:

```powershell
if (-not $env:TB_SUPABASE_URL) { throw "URL missing -- reload .env" }
$env:TB_DEBUG = 'true'
pytest -q -ra
```

Expect: **all 292 tests passed** (including the five live integration tests in `tests/test_supabase_integration.py`).

---

## Step 4 -- Flutter analyze and test

```powershell
cd C:\Users\ariav\travel-buddy\mobile
flutter pub get
if ($LASTEXITCODE -ne 0) { throw "pub get failed" }

flutter analyze --no-fatal-infos
if ($LASTEXITCODE -ne 0) { throw "analyze failed -- paste first 40 lines" }

flutter test
if ($LASTEXITCODE -ne 0) { throw "flutter test failed" }
cd ..
```

Expect: `flutter analyze` exit 0 (0 errors, 0 warnings); `flutter test` exit 0 (all 92 tests passed).

---

## Step 5 -- sabotage proofs (R17)

Run from `mobile/`. For each substep: break code -> test fails -> restore -> test passes.

### 5a replacement_ref lookup
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

### 5b current window visited
File: `mobile/lib/features/itinerary/current_window.dart`
Replace body of `nodeIsCurrentWindow` with `return false;`.
```powershell
cd mobile
flutter test --name "node 10:00 for 90 minutes contains 10:30"
# Expect FAIL
cd ..
git checkout -- mobile/lib/features/itinerary/current_window.dart
```

### 5c auth redirect gate
File: `mobile/lib/routing/redirect_for_auth.dart`
Inside `redirectForAuth`, after `if (!supabaseReady) return null;`, add:
`if (!hasSession && location != '/onboarding') return '/onboarding';`
```powershell
cd mobile
flutter test --name "anonymous user can stay on /"
# Expect FAIL
cd ..
git checkout -- mobile/lib/routing/redirect_for_auth.dart
```

### 5d driver card geoRegion resolution
File: `mobile/lib/features/driver_card/driver_card_helpers.dart`
In `PlaceDriverCardData.fromTripNode`, change `geoRegion: node.geoRegion` back to `geoRegion: null`.
```powershell
cd mobile
flutter test --name "TripNode with geo_region luang_prabang_laos resolves Lao script via fromTripNode"
# Expect FAIL
cd ..
git checkout -- mobile/lib/features/driver_card/driver_card_helpers.dart
```

### 5e offline itinerary cache fallback
File: `mobile/lib/features/itinerary/itinerary_notifier.dart`
In `load()`, comment out the `getCachedTrip` catch block.
```powershell
cd mobile
flutter test --name "offline load falls back to cached trip when network fails"
# Expect FAIL
cd ..
git checkout -- mobile/lib/features/itinerary/itinerary_notifier.dart
```

```powershell
git status
# Must be clean before Step 6
```

---

## Step 6 -- local API + smoke-test.ps1

```powershell
# Window 1: prepare API environment
if ($env:TB_SUPABASE_JWT_SECRET) { Remove-Item Env:TB_SUPABASE_JWT_SECRET }
$env:TB_DEBUG = 'true'
$env:TB_ALLOW_ANONYMOUS = 'true'
python -c "from config.settings import settings; print('debug', settings.debug); print('allow_anonymous', settings.allow_anonymous); print('jwt_secret_set', bool(settings.supabase_jwt_secret))"

# Start uvicorn
uvicorn main:app --reload --port 8000
```

In Window 2:
```powershell
cd C:\Users\ariav\travel-buddy
.\scripts\smoke-test.ps1
```

Record PASS/FAIL lines.

---

## Step 7 -- Anonymous E2E (curl)

Keep uvicorn running with `TB_ALLOW_ANONYMOUS=true` and JWT unset.

```powershell
$uuid = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
$base = 'http://localhost:8000/api/v1'

# 7a Public health
curl.exe -s -w "`n%{http_code}" "$base/health"

# 7b Anonymous status (200)
curl.exe -s -w "`n%{http_code}" "$base/user/status" -H "Authorization: Anonymous $uuid"

# 7c v1 UUID rejected (4xx)
curl.exe -s -w "`n%{http_code}" "$base/user/status" -H "Authorization: Anonymous aaaaaaaa-aaaa-1aaa-8aaa-aaaaaaaaaaaa"

# 7d Create trip as anonymous device
$tmp = Join-Path $env:TEMP 'tb_create_trip.json'
'{"start_date":"2026-10-02T00:00:00Z","initial_mood":"exploratory"}' | Out-File -Encoding ascii $tmp -Force
curl.exe -s -w "`n%{http_code}" -X POST "$base/trip/create" `
  -H "Authorization: Anonymous $uuid" `
  -H "Content-Type: application/json" `
  --data-binary "@$tmp"
```

Save the printed `trip_id` for Step 8.

---

## Step 8 -- Flutter UI verification (Windows desktop or Android)

Chrome may be used for layout checks only. It is not the acceptance target for
SQLite durability, airplane mode or Maps hand-off.

### 8a No Supabase defines (dev gate off)
```powershell
cd C:\Users\ariav\travel-buddy\mobile
flutter run -d windows --dart-define=TB_API_BASE_URL=http://127.0.0.1:8000
```
- App opens on `/` (Trips).
- Profile shows Device ID (UUID v4 format).

### 8b WITH anon Supabase dart-defines (softlock check)
Use the **anon key** from Supabase Settings > API:
```powershell
flutter run -d windows `
  --dart-define=TB_API_BASE_URL=http://127.0.0.1:8000 `
  --dart-define=TB_SUPABASE_URL=https://YOUR_PROJECT.supabase.co `
  --dart-define=TB_SUPABASE_ANON_KEY=YOUR_ANON_KEY
```
- App opens on `/` and stays (no redirect bounce).

### 8c Device ID stability
Reload/restart the app; device ID on Profile must stay identical.

### 8d Swap reflow
On an unlocked card, tap swap icon. Venue updates and timeline reflows.

### 8e Visited / NOW badge
Nodes in current time window show `NOW` badge and `"I'm here"` button.

### 8f Chat copy
Open Chat; empty-state shows questions (hours/nearby), not swap suggestions.

### 8g SPEC-12 Driver Card
On any activity card, tap the car icon (`Show driver card`):
- Full-screen high-contrast card opens.
- Native script headline rendered via `FactView`.
- Landmarks (native script + English) and small last-resort coordinates render.
- No fare or Fair Fare claim is shown until a source supports it.
- `geo:` is expected to fail on Windows today; record it rather than hiding the
  coordinates. The card must not ask for an offline screenshot.
- If unconfirmed: tap `Confirm` -> promotes to verified and enqueues `name_confirmed`.

### 8h SPEC-10 Booking Anchors
In itinerary AppBar, tap `+ Add Booking` icon (`bookmark_add_outlined`):
- Modal sheet opens. Select `Hotel` or `Flight`.
- Paste sample confirmation text: `"Booking Confirmed! Flight EK501 to Dubai. PNR: AB12CD"`
- Tap `Auto-fill from paste` -> Type and PNR populate automatically.
- Tap `Save Anchor` -> locked card appears on timeline with lock icon and `[BOOKING: FLIGHT]` badge.

### 8j Offline itinerary caching
With the trip loaded on Windows or Android:
- Stop the uvicorn backend server in terminal (simulating lost connectivity).
- Reload the trip screen.
- Screen renders the cached itinerary from SQLite with banner:
  `"Offline: showing saved itinerary"` (no blank screen, no crash).
- Restart uvicorn.

---

## After verification

Copy the filled **Results sheet** into chat. We will record the dated finding in `docs/AWAITING_VERIFICATION.md`!
