# Laptop verify -- Windows (PowerShell 5.1)

Owner-only. This is the complete, canonical Device Day runbook for
verifying the entire October spine (SPEC-09, SPEC-22, SPEC-12, SPEC-10,
SPEC-04, and post-spine hardening) on your Windows machine with live
credentials.

PowerShell 5.1. Canonical copy: `docs/briefs/LAPTOP_VERIFY.md` on `main`.

Device Day (`docs/briefs/DEVICE_DAY.md`) is CLOSED. Do not re-apply
0011-0018. Do not re-export Dubai. Do not `VALIDATE CONSTRAINT` on
0015/0017 (that remains a separate non-blocking follow-up).

`docs/TESTING_GUIDE.md` section 4 still mentions
`--dart-define=TB_DEBUG_USER_ID=...`. That flag was removed in SPEC-09
(`7173a3f`). Ignore it. Identity is `Authorization: Anonymous <uuid>`.

## What this day verifies

Prove, on the Windows machine, in this order:

1. Repo SHA and tools on `main`
2. Backend pytest with live Supabase URL (the five integration tests must
   not skip for missing URL)
3. Migrations 0019, 0020, and 0021 applied on the hosted Supabase DB
4. Flutter analyze + test (all 92 unit and widget tests pass with 0 warnings)
5. Sabotage proofs (R17) -- break, watch the named test fail,
   restore, do not commit the break
6. Local API + `smoke-test.ps1`
7. Anonymous identity E2E (`TB_ALLOW_ANONYMOUS=true`, JWT secret unset)
8. Flutter UI verification in Chrome:
   - 8a: Dev gate / Home on `/`
   - 8b: Real anon Supabase defines -- no onboarding redirect loop
   - 8c: Profile device ID (UUID v4 format, persisted)
   - 8d: Live swap on itinerary reflows timeline
   - 8e: Visited / NOW badge on current-window node
   - 8f: Chat empty-state is a question (not a swap promise)
   - 8g: SPEC-12 Driver Card: Lao script, landmark, fair fare band (`20,000 - 50,000 LAK`), one-tap confirm
   - 8h: SPEC-10 Booking Anchors: `+ Add Booking` in AppBar, paste auto-fill, locked booking card with icon & badge
   - 8i: SPEC-04 Hotel Rescue: Shield icon in AppBar opens Hotel Driver Card or calm empty state
   - 8j: Offline Itinerary Cache: load trip, stop API, reload screen -> renders cached itinerary with `"Offline: showing saved itinerary"` banner

Stop and write the failure down if a step fails. Do not "fix forward" past a hard stop.

## Hard stops (do not continue)

- `git pull` fails or working directory has uncommitted regressions
- `pytest -q -ra` with `TB_SUPABASE_URL` set shows the five
  `test_supabase_integration` tests skipped for missing URL
- 0019, 0020, or 0021 proof `SELECT` returns zero rows after apply
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
Step 2 pytest -ra skip list (confirm 5 Supabase tests passed):
Step 3 Migrations applied (0019, 0020, 0021):
Step 4 flutter analyze exit (expect 0 errors, 0 warnings):
Step 4 flutter test exit (expect 92 passed):
Step 5 sabotage proofs (named tests failed when broken, passed after restore):
Step 6 smoke-test.ps1 pass/fail counts:
Step 7 Anonymous curl HTTP codes (v4 / v1 / flag-off):
Step 8a Chrome no supabase defines -- reached / ? yes/no
Step 8b Chrome WITH anon dart-defines -- onboarding loop? yes/no
Step 8c Profile device id (UUID v4 shape, stable on reload):
Step 8d Swap: itinerary row changed? yes/no
Step 8e Visited / NOW visible on node in current window:
Step 8f Chat empty-state text:
Step 8g Driver Card: Lao script, landmark, LAK fare band visible? yes/no
Step 8h Booking Anchors: Add Booking sheet auto-fills, card shows locked badge? yes/no
Step 8i Hotel Rescue: Shield icon opens hotel card or rescue sheet? yes/no
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
Write-Host "creds present URL=$($env:TB_SUPABASE_URL.Substring(0,[Math]::Min(40,$env:TB_SUPABASE_URL.Length)))..."
```

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

## Step 1 -- check live schema before migrations

Check what signal types are currently in the live database:

```sql
SELECT key FROM signal_type
WHERE key IN ('prompt_dismissed', 'driver_card_shown', 'name_confirmed', 'booking_added')
ORDER BY 1;
```

---

## Step 2 -- pytest (in-memory & live)

### 2a In-memory backend

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

Expect only the five live integration tests in `tests/test_supabase_integration.py` to skip.

### 2b Live Supabase backend (required)

```powershell
if (-not $env:TB_SUPABASE_URL) { throw "URL missing -- reload .env" }
$env:TB_DEBUG = 'true'
pytest -q -ra
```

Hard stop if the five Supabase tests skip. All 287 tests must pass.

---

## Step 3 -- apply migrations 0019, 0020, and 0021

In the **Supabase SQL Editor** (web dashboard), execute these statements:

### 3a Migration 0019 (`prompt_dismissed`)
```sql
INSERT INTO signal_type (key, category, value_kind, enum_values, decay_policy, description) VALUES
    ('prompt_dismissed', 'explicit_user', 'json', NULL, 'exp_180d',
     'User dismissed an interruptive fact prompt (ask/defer FactView)')
ON CONFLICT (key) DO NOTHING;
```

### 3b Migration 0020 (`driver_card_shown`, `name_confirmed`)
```sql
INSERT INTO signal_type (key, category, value_kind, enum_values, decay_policy, description) VALUES
    ('driver_card_shown', 'behavioral', 'json', NULL, 'none',
     'Traveller opened a driver card for a venue (offline or online)'),
    ('name_confirmed', 'explicit_user', 'json', NULL, 'none',
     'Traveller verified or rejected local-script venue signage (verdict=confirmed|rejected)')
ON CONFLICT (key) DO NOTHING;
```

### 3c Migration 0021 (`booking_anchors`)
```sql
ALTER TABLE trip_node
    ADD COLUMN IF NOT EXISTS node_kind TEXT NOT NULL DEFAULT 'activity',
    ADD COLUMN IF NOT EXISTS booking_type TEXT NULL,
    ADD COLUMN IF NOT EXISTS confirmation_code TEXT NULL,
    ADD COLUMN IF NOT EXISTS booking_notes TEXT NULL,
    ADD COLUMN IF NOT EXISTS import_source TEXT NULL;

INSERT INTO signal_type (key, category, value_kind, enum_values, decay_policy, description) VALUES
    ('booking_added', 'explicit_user', 'json', NULL, 'none',
     'Traveller recorded a booking anchor (flight, hotel, train, tour)')
ON CONFLICT (key) DO NOTHING;
```

### 3d Proof query:
```sql
SELECT key, category, value_kind
FROM signal_type
WHERE key IN ('prompt_dismissed', 'driver_card_shown', 'name_confirmed', 'booking_added')
ORDER BY 1;
```

Expect **4 rows**.

Re-verify drift guard:
```powershell
pytest tests/test_signal_types.py -q -ra
if ($LASTEXITCODE -ne 0) { throw "signal_types tests failed after migrations" }
```

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
flutter test --name "TripNode with geo_region luang_prabang_laos resolves Lao script and LAK fare"
# Expect FAIL
cd ..
git checkout -- mobile/lib/features/driver_card/driver_card_helpers.dart
```

### 5e hotel rescue node matcher
File: `mobile/lib/features/rescue/hotel_rescue_sheet.dart`
In `findHotelNode`, change `return true;` to `return false;`.
```powershell
cd mobile
flutter test --name "identifies hotel booking with non-generic name"
# Expect FAIL
cd ..
git checkout -- mobile/lib/features/rescue/hotel_rescue_sheet.dart
```

### 5f offline itinerary cache fallback
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

## Step 8 -- Flutter UI verification (Chrome)

### 8a No Supabase defines (dev gate off)
```powershell
cd C:\Users\ariav\travel-buddy\mobile
flutter run -d chrome --dart-define=TB_API_BASE_URL=http://localhost:8000
```
- App opens on `/` (Trips).
- Profile shows Device ID (UUID v4 format).

### 8b WITH anon Supabase dart-defines (softlock check)
Use the **anon key** from Supabase Settings > API:
```powershell
flutter run -d chrome `
  --dart-define=TB_API_BASE_URL=http://localhost:8000 `
  --dart-define=TB_SUPABASE_URL=https://YOUR_PROJECT.supabase.co `
  --dart-define=TB_SUPABASE_ANON_KEY=YOUR_ANON_KEY
```
- App opens on `/` and stays (no redirect bounce).

### 8c Device ID stability
Reload/restart Chrome; device ID on Profile must stay identical.

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
- Landmarks (native script + English), coordinates, and fair fare band visible.
- If unconfirmed: tap `Confirm` -> promotes to verified and enqueues `name_confirmed`.

### 8h SPEC-10 Booking Anchors
In itinerary AppBar, tap `+ Add Booking` icon (`bookmark_add_outlined`):
- Modal sheet opens. Select `Hotel` or `Flight`.
- Paste sample confirmation text: `"Booking Confirmed! Flight EK501 to Dubai. PNR: AB12CD"`
- Tap `Auto-fill from paste` -> Type and PNR populate automatically.
- Tap `Save Anchor` -> locked card appears on timeline with lock icon and `[BOOKING: FLIGHT]` badge.

### 8i SPEC-04 Hotel Rescue
In itinerary AppBar, tap the Shield icon (`shield_outlined`):
- If a hotel is in the itinerary: directly opens hotel driver card in 1 tap.
- If no hotel is saved: opens calm `HotelRescueSheet` with `"+ Add Hotel Booking"` button.

### 8j Offline itinerary caching
With the trip loaded in Chrome:
- Stop the uvicorn backend server in terminal (simulating lost connectivity).
- Refresh the Chrome browser / reload the trip screen.
- Screen renders the cached itinerary from SQLite with banner:
  `"Offline: showing saved itinerary"` (no blank screen, no crash).
- Restart uvicorn.

---

## After verification

Copy the filled **Results sheet** into chat. We will record the dated finding in `docs/AWAITING_VERIFICATION.md`!
