# Pre-Laos final runbook

> Owner-only release sequence for Saturday 26 September through Thursday
> 1 October 2026. The owner flies Thursday night. This runbook does not widen
> scope: reliability, a clean hosted trip slate, one current signed APK, and
> online/offline phone proof are the only goals.

## Hard rules

- PR #67 is the only active implementation path. Do not merge it or apply
  migration 0025 until its real PostgreSQL proof job passes with no skipped
  proofs.
- After #67 merges, apply 0025 before deploying that `main`; the merged backend
  calls `commit_trip_command`.
- Do not distribute this APK to another person. SPEC-43 remains the G1 gate.
- Do not start SPEC-42 Add/Move, SPEC-46, another city, PDF intake, visual
  polish, or refactors before departure.
- Do not reopen already closed migrations 0001-0024.

## Schedule and stop conditions

### Saturday 26 September

1. Finish PR #67 PostgreSQL proof failures. No source-reading-only diagnosis:
   every remainder starts from the first CI traceback.
2. When the proof job is green, review and merge #67.
3. Update the canonical docs with the merge SHA. Do not call 0025 hosted yet.

Stop if the PostgreSQL proof job is red. Phone testing can continue against
current `main`, but the SPEC-44 deploy/migration sequence must not.

### Sunday 27 September

1. Apply migration 0025 once in the Supabase SQL Editor.
2. Run its sentinels and one service-role RPC smoke.
3. Deploy Cloud Run from the merged `main`.
4. Verify `/api/v1/health`, the deployed revision name, and startup
   `supabase_configured=true`.
5. Purge old test trips using the clean-slate SQL below.

Stop if migration, RPC smoke, deploy, or hosted health fails. Do not build the
field APK against a half-upgraded backend.

### Monday 28 September

Run the full Windows checkout and verification commands below. Build and hash a
signed release APK against the Cloud Run URL. Clear the phone app data before
installing so old SQLite trip caches and the old device identity cannot
repopulate the UI.

### Tuesday 29 September

Run the owner phone matrix:

- create one fresh 2+2+4 Laos corridor;
- verify eight date headers and correct city ownership;
- verify named slots, lunch/dinner types, hotel nights and checkout copy;
- verify swap shows server-filtered candidates and changes to the selected
  venue;
- verify SPEC-45 card tap/details, one Ask control, and honest warning copy;
- add one hotel and one flight booking and verify destination-local times;
- force-stop/reopen online;
- load itinerary and driver cards, enable airplane mode, force-stop/reopen,
  and verify cached itinerary and driver card;
- return online and verify the sync queue drains without permanent failures.

Record only observed results in `docs/AWAITING_VERIFICATION.md`.

### Wednesday 30 September

Fix only a blocker found in Tuesday's matrix. A blocker is crash, data loss,
wrong city/date, unusable booking, selected swap not applying, failed cold
reopen, or missing offline itinerary/driver card. Rebuild, hash, reinstall,
and rerun the affected matrix plus one corridor smoke.

No feature work.

### Thursday 1 October, daytime

Freeze the artifact. Record source SHA, Cloud Run revision, APK SHA-256, and
phone result. Create the actual travel trip, open every city once while online,
open the driver cards needed for day one, then perform one final airplane-mode
reopen. Keep the prior known-good APK and Cloud Run revision available for
rollback.

## Hosted clean slate

This removes trip-scoped test data while preserving users, device identities,
venues, dishes, taxonomies, and reference data.

First stop the phone app. Do not reopen the old APK between the hosted purge
and the phone-data clear.

### 1. Preview in the Supabase SQL Editor

```sql
WITH trip_ids AS (
    SELECT trip_id FROM trip_states
)
SELECT 'trip_states' AS object, count(*) AS rows FROM trip_states
UNION ALL
SELECT 'trip_node', count(*) FROM trip_node
WHERE trip_id IN (SELECT trip_id FROM trip_ids)
UNION ALL
SELECT 'trip_edge', count(*) FROM trip_edge
WHERE trip_id IN (SELECT trip_id FROM trip_ids)
UNION ALL
SELECT 'trip_party', count(*) FROM trip_party
WHERE trip_id IN (SELECT trip_id::text FROM trip_ids)
UNION ALL
SELECT 'party_member', count(*)
FROM party_member pm
JOIN trip_party tp ON tp.party_id = pm.party_id
WHERE tp.trip_id IN (SELECT trip_id::text FROM trip_ids)
UNION ALL
SELECT 'signal', count(*) FROM signal
WHERE trip_id IN (SELECT trip_id::text FROM trip_ids)
UNION ALL
SELECT 'event_log', count(*) FROM event_log
WHERE trip_id IN (SELECT trip_id FROM trip_ids)
ORDER BY object;
```

Confirm every `trip_states` row is disposable owner test data. Stop if any trip
must be retained.

### 2. Delete all current trips in one transaction

```sql
BEGIN;

CREATE TEMP TABLE purge_trip_ids ON COMMIT DROP AS
SELECT trip_id FROM trip_states;

DELETE FROM signal
WHERE trip_id IN (SELECT trip_id::text FROM purge_trip_ids);

DELETE FROM event_log
WHERE trip_id IN (SELECT trip_id FROM purge_trip_ids);

DELETE FROM trip_party
WHERE trip_id IN (SELECT trip_id::text FROM purge_trip_ids);

DELETE FROM trip_states
WHERE trip_id IN (SELECT trip_id FROM purge_trip_ids);

SELECT
    (SELECT count(*) FROM purge_trip_ids) AS deleted_trips,
    (SELECT count(*) FROM trip_states) AS remaining_trips,
    (SELECT count(*) FROM trip_node) AS remaining_nodes,
    (SELECT count(*) FROM trip_edge) AS remaining_edges,
    (SELECT count(*) FROM trip_party) AS remaining_parties,
    (SELECT count(*) FROM event_log WHERE trip_id IS NOT NULL) AS remaining_trip_events,
    (SELECT count(*) FROM signal WHERE trip_id IS NOT NULL) AS remaining_trip_signals;

COMMIT;
```

`trip_node` and `trip_edge` cascade from `trip_states`. After 0025,
`trip_command` also cascades from `trip_states`. `party_member` cascades from
`trip_party`.

Run this final check:

```sql
SELECT
    (SELECT count(*) FROM trip_states) AS trips,
    (SELECT count(*) FROM trip_node) AS nodes,
    (SELECT count(*) FROM trip_edge) AS edges,
    (SELECT count(*) FROM trip_party) AS parties,
    (SELECT count(*) FROM event_log WHERE trip_id IS NOT NULL) AS trip_events,
    (SELECT count(*) FROM signal WHERE trip_id IS NOT NULL) AS trip_signals;
```

Every value must be zero before the clean phone session begins.

## Windows checkout, verify, build, and install

Run from PowerShell 5.1:

```powershell
$ErrorActionPreference = 'Stop'
cd C:\Users\ariav\travel-buddy

git fetch origin
git checkout main
git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) { throw "main update failed" }
if (git status --porcelain) { throw "working tree is not clean" }
git log -1 --format="%H %s"

Get-Content .env | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq '' -or $line.StartsWith('#')) { return }
    $eq = $line.IndexOf('=')
    if ($eq -lt 1) { return }
    Set-Item -Path "Env:$($line.Substring(0, $eq).Trim())" `
        -Value $line.Substring($eq + 1).Trim().Trim('"').Trim("'")
}

@('TB_SUPABASE_URL','TB_SUPABASE_KEY') | ForEach-Object {
    $value = (Get-Item "Env:$_" -ErrorAction SilentlyContinue).Value
    if ([string]::IsNullOrWhiteSpace($value)) { throw "MISSING $_" }
    "SET $_"
}

python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q -ra
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }

cd mobile
flutter pub get
flutter analyze --no-fatal-infos
if ($LASTEXITCODE -ne 0) { throw "flutter analyze failed" }
flutter test
if ($LASTEXITCODE -ne 0) { throw "flutter test failed" }

flutter build apk --release `
  --dart-define=TB_API_BASE_URL=https://travel-buddy-196190001420.asia-south1.run.app
if ($LASTEXITCODE -ne 0) { throw "release APK build failed" }

$apk = "build\app\outputs\flutter-apk\app-release.apk"
certutil -hashfile $apk SHA256

adb devices
adb shell am force-stop com.vneogi.travelbuddy
adb shell pm clear com.vneogi.travelbuddy
adb install -r $apk
if ($LASTEXITCODE -ne 0) { throw "APK install failed" }
```

`pm clear` intentionally removes SQLite caches, outbox rows, secure-storage
identity, and prior app state. The next launch creates a fresh anonymous device
identity. Never put the service-role key in a Dart define.
