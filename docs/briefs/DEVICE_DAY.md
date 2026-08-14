# Device Day -- Windows laptop (PowerShell)

Run this on the Windows test laptop. All commands are PowerShell 5.1
compatible. Do not improvise order. Do not apply any migration until Step 2
has committed and pushed `data/dubai_uae.json` after a successful loader
dry-run.

Canonical copy: `docs/briefs/DEVICE_DAY.md` on `origin/main`.

Success criteria for the day:

- `data/dubai_uae.json` exists in git with 16 venues, and
  `python scripts/load_venues.py data/dubai_uae.json --dry-run` exited 0
  before that commit (restorable, not merely parseable)
- Live schema dump and 0011 dual-column decision are recorded
- Migrations 0011 to 0018 applied, or a hard stop documented with the
  blocking finding
- Three Laos venue files re-loaded
- `pytest -q -ra` run with `TB_SUPABASE_URL` set; the five Supabase tests
  either pass or fail with a named finding (skips are not a pass)
- Live checks below recorded in `docs/AWAITING_VERIFICATION.md` as a dated
  entry

Tooling assumed on this laptop:

- git
- Python 3 on PATH as `python` (same as `scripts/start-backend.ps1`)
- pip
- psql (PostgreSQL client) OR the Supabase SQL editor for the SQL steps
- Network access to the hosted Supabase project

Supabase CLI is optional. This brief uses `psql` against `TB_DATABASE_URL`.

If `psql` is missing, run the SQL blocks in the Supabase SQL editor and save
the result grids to the same temp filenames under `$env:TEMP`.

---

## Step 0 -- pull and confirm the tree

```powershell
cd $HOME\travel-buddy
# If the clone lives elsewhere, cd there instead, then:
git pull origin main
if ($LASTEXITCODE -ne 0) { throw "git pull failed" }
git status

findstr /n "name_local TEXT" supabase\migrations\0011_venues_rag_missing_columns.sql
# Expect the PREREQUISITE comment about dual name_local / names_local columns
```

Copy `.env.example` to `.env` if needed and fill at least:

- `TB_SUPABASE_URL`
- `TB_SUPABASE_KEY` (service_role -- bypasses RLS)
- `TB_DATABASE_URL` (postgres connection string for psql)
- `OPENAI_API_KEY` (needed for the Laos reload embeddings)
- `TB_LITELLM_API_KEY` if your loader/embeddings path expects it

Load `.env` into this PowerShell process (the export script does not read `.env`):

```powershell
$ErrorActionPreference = 'Stop'
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
if (-not $env:TB_DATABASE_URL) { throw "TB_DATABASE_URL missing" }
Write-Host "creds present"
```

Install runtime and test deps if this machine has not:

```powershell
python -m pip install -r requirements.txt -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
```

---

## Step 1 -- live snapshot (durability first)

```powershell
python scripts/export_live_snapshot.py
if ($LASTEXITCODE -ne 0) { throw "snapshot failed" }
```

Note the printed `Snapshot directory: data/live_snapshot/<stamp>`.
That directory is gitignored. Set SNAP to that stamp path and confirm Dubai:

```powershell
# replace STAMP with the directory name the script printed
$env:SNAP = "data\live_snapshot\STAMP"
@"
import json, os
snap = os.environ['SNAP']
venues = json.load(open(os.path.join(snap, 'venues_rag.json'), encoding='utf-8'))
regions = {}
for v in venues:
    regions[v.get('geo_region')] = regions.get(v.get('geo_region'), 0) + 1
print(regions)
dubai = [v for v in venues if 'dubai' in (v.get('geo_region') or '')]
print('dubai_count', len(dubai))
if len(dubai) < 16:
    raise SystemExit('STOP: expected at least 16 Dubai venues; do not continue')
"@ | Set-Content -Encoding ascii "$env:TEMP\tb_check_dubai.py"
python "$env:TEMP\tb_check_dubai.py"
if ($LASTEXITCODE -ne 0) { throw "Dubai count check failed -- STOP" }
```

Hard stop if Dubai count is below 16 (or differs from what PROJECT_STATUS
claims -- record the real number and investigate before applying anything).

---

## Step 2 -- durable Dubai file under data/

Write the loader-shaped file, then prove `load_venues.py` can consume it.
A parse check is not a restore proof -- the Laos loader bug in 8dfc412 sat
behind a green test module while the committed data could not be loaded.

```powershell
# SNAP must still point at the Step 1 stamp directory
python scripts/export_dubai_from_snapshot.py $env:SNAP
if ($LASTEXITCODE -ne 0) { throw "Dubai export failed -- do not commit" }

python -c "import json; w=json.load(open('data/dubai_uae.json',encoding='utf-8')); assert w['geo_region']; assert len(w['venues'])>=16; print('ok', w['geo_region'], len(w['venues']))"
if ($LASTEXITCODE -ne 0) { throw "parse check failed" }

python scripts/load_venues.py data/dubai_uae.json --dry-run
if ($LASTEXITCODE -ne 0) { throw "loader dry-run failed -- file is not restorable; fix mapping and retry before commit" }
# Expect exit code 0 and zero validation errors. Warnings are allowed only if
# you understand them; errors mean do not commit.
```

Commit only after the dry-run exits 0:

```powershell
git add data/dubai_uae.json
git commit -m @"
data: export Dubai venues from live Supabase

The 16 Dubai rows existed only in the hosted database. Capture them under
data/ before any migration apply so a rebuild cannot silently drop them.
"@
if ($LASTEXITCODE -ne 0) { throw "commit failed" }
git push origin main
if ($LASTEXITCODE -ne 0) { throw "push failed" }

python -c "import subprocess,json,sys; raw=subprocess.check_output(['git','show','origin/main:data/dubai_uae.json']); w=json.loads(raw); print(w['geo_region'], len(w['venues'])); sys.exit(0 if len(w['venues'])>=16 else 1)"
if ($LASTEXITCODE -ne 0) { throw "origin/main dubai file missing or short" }
```

Hard stop until `origin/main` shows the file with the expected count.

---

## Step 3 -- schema dump and 0011 dual-column decision

PostgREST OpenAPI is already in `$env:SNAP\_live_schema.json`. Also capture
columns and comments via SQL (OpenAPI cannot see CHECKs or pg_description):

```powershell
$colFile = Join-Path $env:TEMP 'tb_venues_rag_columns.txt'
$descFile = Join-Path $env:TEMP 'tb_pg_description.txt'

psql $env:TB_DATABASE_URL -v ON_ERROR_STOP=1 -A -F "`t" -c "SELECT column_name, data_type, udt_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'venues_rag' ORDER BY ordinal_position;" | Set-Content -Encoding ascii $colFile
if ($LASTEXITCODE -ne 0) { throw "column dump failed" }

psql $env:TB_DATABASE_URL -v ON_ERROR_STOP=1 -A -F "`t" -c "SELECT c.relname AS table_name, coalesce(a.attname, '') AS column_name, d.description FROM pg_catalog.pg_description d JOIN pg_catalog.pg_class c ON c.oid = d.objoid LEFT JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.objsubid WHERE c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public') ORDER BY 1, 2;" | Set-Content -Encoding ascii $descFile
if ($LASTEXITCODE -ne 0) { throw "pg_description dump failed" }

python scripts/device_day_name_column_decision.py $colFile
if ($LASTEXITCODE -ne 0) {
    Write-Host "STOP: do not apply 0011 as-is. Record the finding in docs/AWAITING_VERIFICATION.md"
    throw "0011 dual-column gate failed"
}
```

Optional OpenAPI diff against 0011 ADD COLUMN names:

```powershell
@"
import json, re, pathlib
snap = pathlib.Path('data/live_snapshot')
stamps = sorted(p for p in snap.iterdir() if p.is_dir())
schema = json.loads((stamps[-1] / '_live_schema.json').read_text(encoding='utf-8'))
live_cols = set(schema.get('venues_rag', {}).keys())
mig = pathlib.Path('supabase/migrations/0011_venues_rag_missing_columns.sql').read_text(encoding='utf-8')
wanted = set(re.findall(r'ADD COLUMN IF NOT EXISTS (\w+)', mig))
print('0011 columns already live:', sorted(wanted & live_cols))
print('0011 columns missing live:', sorted(wanted - live_cols))
print('live columns not in 0011 add-set (sample):', sorted(live_cols - wanted)[:30])
"@ | Set-Content -Encoding ascii "$env:TEMP\tb_openapi_diff.py"
python "$env:TEMP\tb_openapi_diff.py"
```

If the decision is "do not apply 0011 as-is", stop. Do not proceed to Step 4.

---

## Step 4 -- apply migrations 0011 to 0018

Only after Step 2 is on `origin/main` and Step 3 decision is "safe".

```powershell
git pull origin main
if ($LASTEXITCODE -ne 0) { throw "git pull failed" }

$files = @(
  'supabase\migrations\0011_venues_rag_missing_columns.sql',
  'supabase\migrations\0012_venue_external_id.sql',
  'supabase\migrations\0013_taxonomy_term.sql',
  'supabase\migrations\0014_itinerary_normalisation.sql',
  'supabase\migrations\0015_drift_fixes.sql',
  'supabase\migrations\0016_comment_fixes.sql',
  'supabase\migrations\0017_venues_rag_price_band_check.sql',
  'supabase\migrations\0018_anonymous_identity.sql'
)
foreach ($f in $files) {
    Write-Host "APPLY $f"
    psql $env:TB_DATABASE_URL -v ON_ERROR_STOP=1 -f $f
    if ($LASTEXITCODE -ne 0) {
        throw "STOP: $f failed -- do not continue. Record in docs/AWAITING_VERIFICATION.md"
    }
}

psql $env:TB_DATABASE_URL -c "\d user_tiers"
# expect identity_kind
```

---

## Step 5 -- re-load Laos venues and glossary

Dry run first:

```powershell
python scripts/load_venues.py `
  data/laos_luang_prabang.json `
  data/laos_vang_vieng.json `
  data/laos_vientiane.json `
  --dry-run
if ($LASTEXITCODE -ne 0) { throw "Laos venue dry-run failed" }

python scripts/load_dish_glossary.py data/laos_dish_glossary.json --dry-run
if ($LASTEXITCODE -ne 0) { throw "glossary dry-run failed" }
```

Then real load (writes embeddings -- needs OpenAI / LiteLLM key in the env):

```powershell
python scripts/load_venues.py `
  data/laos_luang_prabang.json `
  data/laos_vang_vieng.json `
  data/laos_vientiane.json
if ($LASTEXITCODE -ne 0) { throw "Laos venue load failed" }

python scripts/load_dish_glossary.py data/laos_dish_glossary.json
if ($LASTEXITCODE -ne 0) { throw "glossary load failed" }
```

Spot-check opening hours no longer null for Laos:

```powershell
psql $env:TB_DATABASE_URL -c "SELECT geo_region, count(*) AS venues, count(opening_hours_structured) AS with_hours FROM venues_rag WHERE geo_region LIKE '%laos%' GROUP BY 1 ORDER BY 1;"
```

---

## Step 6 -- pytest with live credentials

```powershell
git pull origin main
# TB_SUPABASE_URL / TB_SUPABASE_KEY already in this process from Step 0
# Keep TB_ALLOW_ANONYMOUS unset/false unless deliberately testing that path.
pytest -q -ra
```

Record the summary line including skips. The five tests in
`tests/test_supabase_integration.py` must not skip for missing URL. Any
failure is a finding -- do not re-label it as environmental without evidence.

Optional companion smoke (API must be running):

```powershell
.\scripts\smoke-test.ps1
```

---

## Step 7 -- live checks (record results)

Save SQL to a temp file (PowerShell 5.1 is safer this way than inline quoting),
run it, and paste outcomes into a new dated section of
`docs/AWAITING_VERIFICATION.md`:

```powershell
$sqlFile = Join-Path $env:TEMP 'tb_device_day_checks.sql'
@'
-- price_band distinct values (venue_dish and venues_rag)
SELECT 'venue_dish' AS src, price_band, count(*)
FROM venue_dish GROUP BY 1,2 ORDER BY 1,2;
SELECT 'venues_rag' AS src, price_band, count(*)
FROM venues_rag GROUP BY 1,2 ORDER BY 1,2;

-- AED magnitudes on Dubai dishes (do not backfill today; observe only)
SELECT vd.name, vd.price_local, vd.currency_code, vd.price_band, v.name AS venue
FROM venue_dish vd
JOIN venues_rag v ON v.venue_id = vd.venue_id
WHERE v.geo_region LIKE '%dubai%'
ORDER BY vd.price_local NULLS LAST
LIMIT 50;

-- pg_description non-ASCII (0016 confirmation)
SELECT c.relname, a.attname, d.description
FROM pg_catalog.pg_description d
JOIN pg_catalog.pg_class c ON c.oid = d.objoid
LEFT JOIN pg_catalog.pg_attribute a
  ON a.attrelid = c.oid AND a.attnum = d.objsubid
WHERE c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
  AND d.description ~ '[^[:ascii:]]';

-- hybrid_venue_search signature vs migration 0001 expectation
SELECT pg_get_function_identity_arguments(p.oid) AS args,
       pg_get_functiondef(p.oid) AS def
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public' AND p.proname = 'hybrid_venue_search';
'@ | Set-Content -Encoding ascii $sqlFile

psql $env:TB_DATABASE_URL -v ON_ERROR_STOP=1 -f $sqlFile
if ($LASTEXITCODE -ne 0) { throw "live checks failed" }
```

Do not run `VALIDATE CONSTRAINT` on the price_band CHECKs today unless the
distinct-value read shows a clean set that matches the taxonomy seed. If it
does, validating is allowed; if it does not, leave NOT VALID and file the
finding.

---

## Step 8 -- close the day in docs

Append a dated block to `docs/AWAITING_VERIFICATION.md` covering:

- Dubai export commit SHA and venue count
- Loader dry-run result for `data/dubai_uae.json`
- 0011 dual-column decision and what was applied
- pytest summary with skip reasons
- price_band / AED / pg_description / hybrid_venue_search observations

Update `docs/PROJECT_STATUS.md` only for facts that changed (migration
status rows, Dubai source-file risk). Do not hand-mirror test counts (R16).

Push documentation commits to main. Verify with:

```powershell
git fetch origin
git show origin/main:docs/AWAITING_VERIFICATION.md | Select-Object -Last 80
```

---

## Explicit non-goals for this day

- No Flutter work
- No SPEC-09 client half
- No Railway / deploy
- No Genie code changes during the apply window
- No blind VALIDATE CONSTRAINT
- No Dubai dish `names_local` backfill
