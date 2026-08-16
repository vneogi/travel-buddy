# Device Day -- Windows laptop (PowerShell)

PowerShell 5.1. Canonical copy: `docs/briefs/DEVICE_DAY.md` on `origin/main`.

## RESUME HERE (as of 2026-08-16, after Step 2)

Steps 0-2 are done on the first Windows session. **Start at Step 3.**

| Step | Status | Evidence |
|---|---|---|
| 0 Pull + env | DONE | Creds loaded; deps installed |
| 1 Live snapshot | DONE | `data/live_snapshot/20260816T174110Z` (gitignored; laptop-local) |
| 2 Dubai durability | DONE | `data/dubai_uae_raw_snapshot.json` on `origin/main` at `6bfa1c6` -- 16 venues, `not_loader_source: true` |
| 3 Schema dump / 0011 gate | NEXT | |
| 4 Apply 0011-0018 | pending | |
| 5 Re-load Laos | pending | |
| 6 Pytest with live creds | pending | |
| 7 Live checks | pending | |
| 8 Close day in docs | pending | |

### Pickup commands (any Windows machine)

```powershell
cd C:\Users\ariav\travel-buddy   # or wherever this clone lives
git pull origin main
if ($LASTEXITCODE -ne 0) { throw "git pull failed" }

# Confirm durability is on origin (do not re-do Step 2)
python -c "import subprocess,json; w=json.loads(subprocess.check_output(['git','show','origin/main:data/dubai_uae_raw_snapshot.json'])); print(w['geo_region'], len(w['venues']), w.get('not_loader_source'))"
# Expect: dubai_uae 16 True

# Load .env into this PowerShell process
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

`data/live_snapshot/` is gitignored. If this is a different machine, or the
stamp folder is gone, re-take a snapshot before Step 3's optional OpenAPI
diff (the SQL column dump does not need it):

```powershell
python scripts/export_live_snapshot.py
if ($LASTEXITCODE -ne 0) { throw "snapshot failed" }
# Set SNAP to the NEW stamp the script printed -- never leave the word STAMP
$env:SNAP = "data\live_snapshot\PASTE_STAMP_HERE"
```

If the original stamp still exists on this machine:

```powershell
$env:SNAP = "data\live_snapshot\20260816T174110Z"
```

Then continue at **Step 3** below.

### What Step 2 already decided (do not re-litigate mid-apply)

- Loader-shaped `data/dubai_uae.json` **failed** `load_venues.py --dry-run`
  (72 errors): all 16 rows have null `typical_dwell_minutes` /
  `indoor_outdoor` / `price_band`; Dubai categories/audiences/vibes sit
  outside the Laos-era loader vocabulary.
- We did **not** invent those values. Raw dump was committed instead.
- Loader-valid `data/dubai_uae.json` is a **follow-up**, not a migration
  blocker. Do not pass the raw file to `load_venues.py`.
- Raw dump recorded `venue_dishes: 0`. Before trusting that, optionally:

```powershell
@"
import json, os
from pathlib import Path
snap = Path(os.environ['SNAP'])
venues = json.loads((snap/'venues_rag.json').read_text(encoding='utf-8'))
dishes = json.loads((snap/'venue_dish.json').read_text(encoding='utf-8'))
ids = {v['venue_id'] for v in venues if 'dubai' in (v.get('geo_region') or '')}
print('dubai_venues', len(ids))
print('dishes_for_dubai', sum(1 for d in dishes if d.get('venue_id') in ids))
print('dish_geo_hint_sample', dishes[0].keys() if dishes else None)
"@ | Set-Content -Encoding ascii "$env:TEMP\tb_dubai_dishes.py"
python "$env:TEMP\tb_dubai_dishes.py"
```

---

## Success criteria (full day)

- Durable Dubai on `origin/main` before migrations -- **met** via raw dump
- Live schema dump and 0011 dual-column decision recorded
- Migrations 0011 to 0018 applied, or hard stop documented
- Three Laos venue files re-loaded
- `pytest -q -ra` with `TB_SUPABASE_URL` set; five Supabase tests must not
  skip for missing URL
- Live checks recorded in `docs/AWAITING_VERIFICATION.md`

Tooling: git, `python`, pip, `psql` (or Supabase SQL editor), network to
hosted Supabase. If `psql` is missing, run SQL in the Supabase SQL editor and
save results to the same `$env:TEMP` filenames.

---

## Steps 0-2 -- DONE (reference only)

Kept so a fresh reader can see what already ran. Do not repeat unless the
durable Dubai file is missing from `origin/main`.

### Step 0 -- pull and confirm the tree (DONE)

```powershell
cd C:\Users\ariav\travel-buddy
git pull origin main
findstr /n "name_local TEXT" supabase\migrations\0011_venues_rag_missing_columns.sql
# Load .env into process env (see RESUME HERE)
python -m pip install -r requirements.txt -r requirements-dev.txt
```

### Step 1 -- live snapshot (DONE)

Stamp used: `20260816T174110Z`. Counts: dubai 16, luang_prabang 23,
vang_vieng 15, vientiane 20. Unapplied tables 404'd as expected
(`venue_external_id`, `taxonomy_term`, `trip_node`, `trip_edge`).

Pitfall: `$env:SNAP = "data\live_snapshot\STAMP"` is a placeholder -- replace
`STAMP` with the real directory name the export script printed.

### Step 2 -- durable Dubai (DONE via 2b)

- 2a loader export dry-run: FAILED (expected; see RESUME HERE)
- 2b raw dump: committed `6bfa1c6` as `data/dubai_uae_raw_snapshot.json`

---

## Step 3 -- schema dump and 0011 dual-column decision (START HERE)

PostgREST OpenAPI is in `$env:SNAP\_live_schema.json` if SNAP points at a
local stamp. The SQL dumps below are mandatory either way.

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

Optional OpenAPI diff against 0011 ADD COLUMN names (needs a local stamp):

```powershell
@"
import json, re, pathlib
snap = pathlib.Path('data/live_snapshot')
stamps = sorted(p for p in snap.iterdir() if p.is_dir())
if not stamps:
    raise SystemExit('no local live_snapshot stamps -- re-run export_live_snapshot.py')
schema = json.loads((stamps[-1] / '_live_schema.json').read_text(encoding='utf-8'))
live_cols = set(schema.get('venues_rag', {}).keys())
mig = pathlib.Path('supabase/migrations/0011_venues_rag_missing_columns.sql').read_text(encoding='utf-8')
wanted = set(re.findall(r'ADD COLUMN IF NOT EXISTS (\w+)', mig))
print('using stamp', stamps[-1])
print('0011 columns already live:', sorted(wanted & live_cols))
print('0011 columns missing live:', sorted(wanted - live_cols))
print('live columns not in 0011 add-set (sample):', sorted(live_cols - wanted)[:30])
"@ | Set-Content -Encoding ascii "$env:TEMP\tb_openapi_diff.py"
python "$env:TEMP\tb_openapi_diff.py"
```

If the decision is "do not apply 0011 as-is", stop. Do not proceed to Step 4.
Paste the decision script output into chat or AWAITING_VERIFICATION before
applying anything.

---

## Step 4 -- apply migrations 0011 to 0018

Only after Step 2 durability is on `origin/main` (met) and Step 3 decision
is "safe".

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
# TB_SUPABASE_URL / TB_SUPABASE_KEY already in this process from pickup
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
distinct-value read shows a clean set that matches the taxonomy seed.

---

## Step 8 -- close the day in docs

Append a dated block to `docs/AWAITING_VERIFICATION.md` covering:

- Dubai durability: raw dump SHA `6bfa1c6`, loader-valid file still owed
- 0011 dual-column decision and what was applied
- pytest summary with skip reasons
- price_band / AED / pg_description / hybrid_venue_search observations
- Whether Dubai `venue_dish` rows exist live

Update `docs/PROJECT_STATUS.md` only for facts that changed (migration
status rows, Dubai risk). Do not hand-mirror test counts (R16).

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
- No inventing Dubai dwell/price/indoor values to force a loader dry-run
- No Dubai dish `names_local` backfill
- Do not pass `data/dubai_uae_raw_snapshot.json` to `load_venues.py`
