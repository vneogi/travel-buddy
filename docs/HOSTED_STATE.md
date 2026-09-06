# Hosted State and Local Credential Verification

This is the canonical ledger for the hosted Supabase schema and credential-backed
providers. Update this file after a hosted migration or provider smoke test.
Other living documents must link here instead of maintaining a second ledger.

Never record secret values, API responses containing keys, or `.env` contents.
The repository cannot inspect a laptop-local `.env`; it can only record a dated,
successful test of a named variable.

## Current verified state

Last verified: 2026-09-06 on the owner's Windows laptop and hosted Supabase
project.

### Hosted Supabase

| Migration | State | Evidence |
|---|---|---|
| 0001-0010 | Applied | Existing hosted baseline |
| 0011-0018 | Applied | Device day 2026-08-17; 0015 and 0017 CHECK constraints intentionally remain NOT VALID |
| 0019 | Applied | `signal_type.prompt_dismissed` present on 2026-09-06 |
| 0020 | Applied | `driver_card_shown` and `name_confirmed` present on 2026-09-06 |
| 0021 | Applied | `trip_node.node_kind` and `booking_added` present on 2026-09-06 |
| 0022 | Applied | `trip_node.names_local` present on 2026-09-06 |
| 0023 | Applied | Live `hybrid_venue_search` has seventh argument `filter_geo_region text` on 2026-09-06 |
| 0024 | Applied | `signal_type.session_start` present on 2026-09-06 |

The project applies SQL manually and does not have a trustworthy migration
history table. "Applied" above means the expected live schema sentinel was
observed; it is not inferred from a filename.

### Laptop-local backend variables

| Variable | State | Evidence |
|---|---|---|
| `TB_GOOGLE_MAPS_API_KEY` | Present and provider-authorized | Distance Matrix returned status OK, a 2.5 km route, base duration, and traffic duration on 2026-09-06 |
| `TB_OPENWEATHER_API_KEY` | Present and provider-authorized | OpenWeather forecast returned code 200 and 40 forecast periods on 2026-09-06 |
| `TB_SUPABASE_URL` | Not established by these smoke tests | Required separately for live backend tests |
| `TB_SUPABASE_KEY` | Not established by these smoke tests | Backend service-role key; never pass to Flutter |
| `TB_LITELLM_API_KEY` | Not established by these smoke tests | Required by existing model and embedding paths |
| `TB_ALLOW_ANONYMOUS` | Not established by these smoke tests | Defaults false; SPEC-37 hosted field test deliberately sets true |
| `TB_SUPABASE_JWT_SECRET` | Not established by these smoke tests | Leave unset for the Anonymous field-test path; configured JWT takes precedence |

The provider test proves the variables were loaded into that PowerShell process.
It does not prove they are configured on a hosted backend deployment.

### Hosted application deployment

No production/field-test API deployment is currently verified. Therefore no
backend variable is recorded as present on a hosted application service,
including Supabase, LLM, Maps, Weather, or anonymous-auth configuration.
SPEC-37 owns provisioning and verification after SPEC-36 merges, with final
phone acceptance targeted for 2026-09-18. Until then, the hosted Supabase
database and the laptop-local backend environment must not be described as a
deployed application.

Security action: a Google Maps key was exposed outside `.env` during testing.
Rotate it in Google Cloud, retain API and application restrictions, replace the
local value, and rerun the safe smoke test below. Do not record the replacement
key in this repository.

## Check local variable presence without printing secrets

Run from the repository root in every new PowerShell:

```powershell
Get-Content .env | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq '' -or $line.StartsWith('#')) { return }
    $eq = $line.IndexOf('=')
    if ($eq -lt 1) { return }
    Set-Item -Path "Env:$($line.Substring(0, $eq).Trim())" `
        -Value $line.Substring($eq + 1).Trim().Trim('"').Trim("'")
}

@(
    'TB_SUPABASE_URL',
    'TB_SUPABASE_KEY',
    'TB_LITELLM_API_KEY',
    'TB_ALLOW_ANONYMOUS',
    'TB_SUPABASE_JWT_SECRET',
    'TB_GOOGLE_MAPS_API_KEY',
    'TB_OPENWEATHER_API_KEY'
) | ForEach-Object {
    $value = (Get-Item "Env:$_" -ErrorAction SilentlyContinue).Value
    if ([string]::IsNullOrWhiteSpace($value)) { "MISSING $_" } else { "SET $_" }
}
```

Only `SET` or `MISSING` is printed. Never use `Get-ChildItem Env:` in a shared
transcript because it prints values.

## Provider smoke tests

PowerShell aliases `curl` to `Invoke-WebRequest`. Use `curl.exe`:

```powershell
$maps = curl.exe -s "https://maps.googleapis.com/maps/api/distancematrix/json?origins=19.885,102.135&destinations=19.892,102.142&mode=driving&departure_time=now&traffic_model=best_guess&units=metric&key=$env:TB_GOOGLE_MAPS_API_KEY" |
    ConvertFrom-Json
if ($maps.status -ne 'OK' -or $maps.rows[0].elements[0].status -ne 'OK') {
    throw "Google Maps smoke failed: $($maps.status)"
}
"Google Maps: OK; traffic seconds=$($maps.rows[0].elements[0].duration_in_traffic.value)"

$weather = curl.exe -s "https://api.openweathermap.org/data/2.5/forecast?lat=19.885&lon=102.135&appid=$env:TB_OPENWEATHER_API_KEY" |
    ConvertFrom-Json
if ([string]$weather.cod -ne '200') {
    throw "OpenWeather smoke failed: $($weather.cod)"
}
"OpenWeather: OK; forecast periods=$($weather.cnt)"
```

These commands print summaries rather than the full payload. The URL still
contains the key inside the local process, so do not enable verbose HTTP tracing.

## Recheck the hosted Supabase sentinels

Run in the Supabase SQL Editor:

```sql
WITH expected(migration, kind, object_name) AS (
  VALUES
    ('0011', 'column', 'venues_rag.embedding_model'),
    ('0012', 'table',  'venue_external_id'),
    ('0013', 'table',  'taxonomy_term'),
    ('0014', 'table',  'trip_node'),
    ('0014', 'table',  'trip_edge'),
    ('0018', 'column', 'user_tiers.identity_kind'),
    ('0019', 'signal', 'prompt_dismissed'),
    ('0020', 'signal', 'driver_card_shown'),
    ('0020', 'signal', 'name_confirmed'),
    ('0021', 'column', 'trip_node.node_kind'),
    ('0021', 'signal', 'booking_added'),
    ('0022', 'column', 'trip_node.names_local'),
    ('0024', 'signal', 'session_start')
),
objects AS (
  SELECT 'table' AS kind, c.relname AS object_name
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relkind = 'r'
  UNION ALL
  SELECT 'column', t.relname || '.' || a.attname
  FROM pg_attribute a
  JOIN pg_class t ON t.oid = a.attrelid
  JOIN pg_namespace n ON n.oid = t.relnamespace
  WHERE n.nspname = 'public' AND a.attnum > 0 AND NOT a.attisdropped
  UNION ALL
  SELECT 'signal', key FROM signal_type
)
SELECT e.migration, e.kind, e.object_name,
       (o.object_name IS NOT NULL) AS applied
FROM expected e
LEFT JOIN objects o USING (kind, object_name)
ORDER BY e.migration, e.object_name;

SELECT p.proname AS function_name,
       pg_get_function_identity_arguments(p.oid) AS args
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public'
  AND p.proname = 'hybrid_venue_search';
```

Every sentinel row must be true. Migration 0023 is present only when the
function arguments include `filter_geo_region text`.
