# Device Day -- Windows laptop (PowerShell)

PowerShell 5.1. Canonical copy: `docs/briefs/DEVICE_DAY.md` on `origin/main`.

## RESUME HERE (as of 2026-08-17, after Step 5 load + Step 6 pytest)

Steps 0-5 done. Step 6 ran live: **270 passed, 10 failed**. The five
Supabase integration tests are **not** among the failures (they ran with
`TB_SUPABASE_URL` set). Fix the 10 failures below (pull), re-run pytest,
then Step 5d spot-check + Steps 7-8.

| Step | Status | Evidence |
|---|---|---|
| 0-3 | DONE | OpenAPI gate safe; durability on origin |
| 4 Apply 0011-0018 | DONE (confirm) | SQL editor; confirm `identity_kind` if not pasted |
| 5 Re-load Laos | DONE | 58 venues upserted; 30 glossary rows |
| 6 Pytest with live creds | PARTIAL | 270 passed / 10 failed -- see Step 6 notes; Supabase five ran |
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

Then continue at **Step 4** below (Step 3 already passed on this machine).

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

### Pitfall -- empty column dump is NOT "safe"

If `device_day_name_column_decision.py` prints `venues_rag columns: []` or
`column_count: 0`, **stop**. That means the TSV is empty (often a failed
`psql` password prompt written into the file). An empty set must never be
treated as permission to apply 0011. Use Step 3a (OpenAPI) instead.

---

## Success criteria (full day)

- Durable Dubai on `origin/main` before migrations -- **met** via raw dump
- Live schema dump and 0011 dual-column decision recorded
- Migrations 0011 to 0018 applied, or hard stop documented
- Three Laos venue files re-loaded
- `pytest -q -ra` with `TB_SUPABASE_URL` set; five Supabase tests must not
  skip for missing URL
- Live checks recorded in `docs/AWAITING_VERIFICATION.md`

Tooling: git, `python`, pip, network to hosted Supabase, and the **Supabase
SQL editor** for migration apply (Step 4). `psql` is optional; do not block
on installing it.

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

`psql` is optional. Prefer the OpenAPI path below when `psql` is not on PATH
(common on the Windows laptop). The dual-column gate only needs the live
column *names* for `venues_rag`.

### 3a. Column dump without psql (preferred when psql is missing)

Needs a local stamp under `data/live_snapshot/` (gitignored). If missing,
re-run `python scripts/export_live_snapshot.py` first and set `$env:SNAP`.

```powershell
# If the original stamp still exists:
$env:SNAP = "data\live_snapshot\20260816T174110Z"
# Otherwise re-export and paste the new stamp name instead of STAMP:
# python scripts/export_live_snapshot.py
# $env:SNAP = "data\live_snapshot\PASTE_STAMP_HERE"

$colFile = Join-Path $env:TEMP 'tb_venues_rag_columns.txt'
python scripts/device_day_schema_from_openapi.py $env:SNAP --out $colFile
if ($LASTEXITCODE -ne 0) { throw "openapi column dump failed" }

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

### 3b. Column + comment dump with psql (if installed later)

```powershell
$colFile = Join-Path $env:TEMP 'tb_venues_rag_columns.txt'
$descFile = Join-Path $env:TEMP 'tb_pg_description.txt'

# Do NOT add -U postgres. TB_DATABASE_URL already carries the role; -U forces
# an interactive password prompt and can leave $colFile empty while exit 0.
psql $env:TB_DATABASE_URL -v ON_ERROR_STOP=1 -A -F "`t" -c "SELECT column_name, data_type, udt_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'venues_rag' ORDER BY ordinal_position;" | Set-Content -Encoding ascii $colFile
if ($LASTEXITCODE -ne 0) { throw "column dump failed" }
Get-Content $colFile | Select-Object -First 5
if (-not (Get-Content $colFile | Where-Object { $_ -match '^venue_id\t' })) {
    throw "column dump missing venue_id -- refuse empty/auth-failed TSV"
}

psql $env:TB_DATABASE_URL -v ON_ERROR_STOP=1 -A -F "`t" -c "SELECT c.relname AS table_name, coalesce(a.attname, '') AS column_name, d.description FROM pg_catalog.pg_description d JOIN pg_catalog.pg_class c ON c.oid = d.objoid LEFT JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.objsubid WHERE c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public') ORDER BY 1, 2;" | Set-Content -Encoding ascii $descFile
if ($LASTEXITCODE -ne 0) { throw "pg_description dump failed" }

python scripts/device_day_name_column_decision.py $colFile
if ($LASTEXITCODE -ne 0) {
    Write-Host "STOP: do not apply 0011 as-is. Record the finding in docs/AWAITING_VERIFICATION.md"
    throw "0011 dual-column gate failed"
}
```

`pg_description` (comment scan) still needs SQL. Defer it to Step 7 and run
those queries in the Supabase SQL editor if `psql` stays unavailable.

If the decision is "do not apply 0011 as-is", stop. Do not proceed to Step 4.
Paste the decision script output into chat or AWAITING_VERIFICATION before
applying anything.

---

## Step 4 -- apply migrations 0011 to 0018 (START HERE)

Only after Step 2 durability is on `origin/main` (met) and Step 3 decision
is "safe" (met via OpenAPI on 2026-08-17).

**Preferred path: Supabase SQL editor.** Do not install or fight `psql` for
this step. Paste one migration file per run, in order. Stop on the first
error; record the file name and message in chat or
`docs/AWAITING_VERIFICATION.md` before continuing.

### How to apply each file

1. Open the hosted Supabase project -> **SQL Editor** -> New query.
2. On the laptop, open the migration file under `supabase\migrations\` in an
   editor, copy **the entire file** (including comments).
3. Paste into the SQL editor and Run.
4. Confirm success (no error banner). Then move to the next file.
5. After `0018`, run this check in a new query:

```sql
SELECT column_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'user_tiers'
  AND column_name = 'identity_kind';
```

Expect exactly one row. Then continue to Step 5.

### Files in order

| # | File | Notes |
|---|---|---|
| 1 | `supabase/migrations/0011_venues_rag_missing_columns.sql` | `typical_dwell_minutes` / `indoor_outdoor` / `price_band` already live -> `IF NOT EXISTS` no-ops; still adds `has_aircon`, `names_local`, `nearest_landmark`, `landmarks_local`, `wheelchair_notes` |
| 2 | `supabase/migrations/0012_venue_external_id.sql` | |
| 3 | `supabase/migrations/0013_taxonomy_term.sql` | |
| 4 | `supabase/migrations/0014_itinerary_normalisation.sql` | |
| 5 | `supabase/migrations/0015_drift_fixes.sql` | |
| 6 | `supabase/migrations/0016_comment_fixes.sql` | |
| 7 | `supabase/migrations/0017_venues_rag_price_band_check.sql` | `NOT VALID` CHECK; must not abort on live Dubai nulls |
| 8 | `supabase/migrations/0018_anonymous_identity.sql` | then run `identity_kind` SELECT above |

### Optional -- psql fallback (skip unless you already use it cleanly)

Do **not** pass `-U postgres` when `TB_DATABASE_URL` already has the role.

```powershell
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
```

---
## Step 5 -- re-load Laos venues and glossary

Dry-run does **not** need embedding or write keys. A real load does.

### 5a. Env preflight (before real load)

Re-load `.env` into this PowerShell process (pickup block at top), then:

```powershell
# Presence only -- do not print secret values
@(
  'TB_SUPABASE_URL',
  'TB_SUPABASE_KEY',
  'TB_LITELLM_API_KEY',
  'OPENAI_API_KEY'
) | ForEach-Object {
    $v = [Environment]::GetEnvironmentVariable($_)
    "{0} present={1}" -f $_, [bool]$v
}
if (-not $env:TB_SUPABASE_URL) { throw "TB_SUPABASE_URL missing" }
if (-not $env:TB_SUPABASE_KEY) { throw "TB_SUPABASE_KEY missing (service_role)" }
if (-not $env:TB_LITELLM_API_KEY -and -not $env:OPENAI_API_KEY) {
    throw "TB_LITELLM_API_KEY (or OPENAI_API_KEY) missing -- needed for embeddings"
}
# Bridge if .env only has the project name (loaders also do this after pull):
if (-not $env:OPENAI_API_KEY -and $env:TB_LITELLM_API_KEY) {
    $env:OPENAI_API_KEY = $env:TB_LITELLM_API_KEY
}
```

If `TB_LITELLM_API_KEY` is absent from `.env`, add the OpenAI key there (same
value LiteLLM uses for `text-embedding-3-small`), re-run the pickup `.env`
loader, then re-check presence.

### 5b. Dry run

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

Two warnings about markets with no dishes are expected and non-blocking.

### 5c. Real load

```powershell
python scripts/load_venues.py `
  data/laos_luang_prabang.json `
  data/laos_vang_vieng.json `
  data/laos_vientiane.json
if ($LASTEXITCODE -ne 0) { throw "Laos venue load failed" }

python scripts/load_dish_glossary.py data/laos_dish_glossary.json
if ($LASTEXITCODE -ne 0) { throw "glossary load failed" }
```

### 5d. Spot-check opening hours (SQL editor if no psql)

```sql
SELECT geo_region,
       count(*) AS venues,
       count(opening_hours_structured) AS with_hours
FROM venues_rag
WHERE geo_region LIKE '%laos%'
GROUP BY 1
ORDER BY 1;
```

Or with psql (no `-U postgres`):

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

### Known Windows failures from first live run (2026-08-17)

First live suite: **270 passed, 10 failed**. Supabase five ran (present in
warnings, absent from FAILED list). Classify before re-running:

1. **8x `test_data_format` CRLF** -- working tree has `\r\n` under
   `core.autocrlf`; serializers emit `\n`. Repo now has `.gitattributes`
   (`data/*.json text eol=lf`). After pull:

```powershell
git add --renormalize data
git status
# If data/*.json show as modified, restore LF from index:
git checkout -- data/*.json
python -c "from pathlib import Path; p=Path('data/laos_luang_prabang.json'); print('CRLF' if b'\r\n' in p.read_bytes()[:40] else 'LF')"
# Expect: LF
pytest -q tests/test_data_format.py
```

2. **`test_no_unexpected_non_ascii`** -- R14 arrows in DEVICE_DAY /
   ENGINEERING_RULES (`->` / `=>` fixed on origin).

3. **`test_no_silent_key_drop`** -- raw Dubai dump keys were scanned as if
   loader-sourced. Test now skips `not_loader_source: true` files.

Re-run full `pytest -q -ra` after pull. Expect green or a new finding only.

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
