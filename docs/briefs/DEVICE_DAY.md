# Device Day Brief

Run this on the laptop when it is available (target: on or after Aug 15 2026).
Do not improvise order. Do not apply any migration until Step 3 says the
Dubai file is committed and pushed.

Success criteria for the day:

- `data/dubai_uae.json` exists in git with 16 venues, and
  `python3 scripts/load_venues.py data/dubai_uae.json --dry-run` exited 0
  before that commit (restorable, not merely parseable)
- Live schema dump and 0011 dual-column decision are recorded
- Migrations 0011 to 0018 applied, or a hard stop documented with the
  blocking finding
- Three Laos venue files re-loaded
- `pytest -q -ra` run with `TB_SUPABASE_URL` set; the five Supabase tests
  either pass or fail with a named finding (skips are not a pass)
- Live checks below recorded in `docs/AWAITING_VERIFICATION.md` as a dated
  entry

Tooling assumed: git, python3, pip, psql (or Supabase SQL editor for the
SQL steps), network access to the hosted project. Supabase CLI is optional;
this brief uses `psql` against `TB_DATABASE_URL`.

---

## Step 0 -- pull and confirm the tree

```bash
cd ~/travel-buddy
git pull origin main
git status   # working tree should be clean before starting
grep -n "name_local TEXT" supabase/migrations/0011_venues_rag_missing_columns.sql
# Expect the PREREQUISITE comment about dual name_local / names_local columns
```

Copy `.env.example` to `.env` if needed and fill at least:

- `TB_SUPABASE_URL`
- `TB_SUPABASE_KEY` (service_role -- bypasses RLS)
- `TB_DATABASE_URL` (postgres connection string for psql)
- `OPENAI_API_KEY` (needed for the Laos reload embeddings)

Load them into the shell (the export script does not read `.env`):

```bash
set -a
source .env
set +a
test -n "$TB_SUPABASE_URL" && test -n "$TB_SUPABASE_KEY" && test -n "$TB_DATABASE_URL"
echo "creds present"
```

Install runtime and test deps if this machine has not:

```bash
python3 -m pip install -r requirements.txt -r requirements-dev.txt
```

---

## Step 1 -- live snapshot (durability first)

```bash
python3 scripts/export_live_snapshot.py
```

Note the printed `Snapshot directory: data/live_snapshot/<stamp>`.
That directory is gitignored. Confirm the region breakdown includes Dubai:

```bash
# replace STAMP with the directory name the script printed
export SNAP=data/live_snapshot/STAMP
python3 - <<'PY'
import json, os
snap = os.environ["SNAP"]
venues = json.loads(open(f"{snap}/venues_rag.json", encoding="utf-8").read())
regions = {}
for v in venues:
    regions[v.get("geo_region")] = regions.get(v.get("geo_region"), 0) + 1
print(regions)
dubai = [v for v in venues if "dubai" in (v.get("geo_region") or "")]
print("dubai_count", len(dubai))
if len(dubai) < 16:
    raise SystemExit("STOP: expected at least 16 Dubai venues; do not continue")
PY
```

Hard stop if Dubai count is not 16 (or whatever the live count is, if it
differs -- record the real number and stop to investigate before applying
anything).

---

## Step 2 -- durable Dubai file under data/

Write a loader-shaped file the repo can rebuild from. Map live columns back
to the JSON keys the loader understands. Keep ASCII on disk via `\uXXXX`
escapes (`ensure_ascii=True`).

```bash
export SNAP=data/live_snapshot/STAMP   # same stamp as Step 1
python3 - <<'PY'
import json, os
from datetime import date
from pathlib import Path

snap = Path(os.environ["SNAP"])
venues = json.loads((snap / "venues_rag.json").read_text(encoding="utf-8"))
dishes_path = snap / "venue_dish.json"
dishes = json.loads(dishes_path.read_text(encoding="utf-8")) if dishes_path.is_file() else []

dubai = [v for v in venues if (v.get("geo_region") or "").find("dubai") >= 0]
if not dubai:
    raise SystemExit("no dubai rows")

# Attach dishes by venue_id when present
by_venue = {}
for d in dishes:
    by_venue.setdefault(d.get("venue_id"), []).append(d)

def first_local(blob, field_fallback):
    """Prefer names_local/landmarks_local JSONB; fall back to legacy TEXT."""
    if isinstance(blob, dict) and blob:
        # pick any language entry that has a value
        for _lang, entry in blob.items():
            if isinstance(entry, dict) and entry.get("value"):
                return entry.get("value"), entry.get("source"), entry.get("ref")
            if isinstance(entry, str) and entry:
                return entry, None, None
    if field_fallback:
        return field_fallback, None, None
    return None, None, None

out_venues = []
for v in sorted(dubai, key=lambda r: (r.get("name") or "")):
    names_local = v.get("names_local")
    if isinstance(names_local, str):
        try:
            names_local = json.loads(names_local)
        except Exception:
            names_local = None
    landmarks_local = v.get("landmarks_local")
    if isinstance(landmarks_local, str):
        try:
            landmarks_local = json.loads(landmarks_local)
        except Exception:
            landmarks_local = None

    name_local, name_src, name_ref = first_local(
        names_local, v.get("name_local")
    )
    landmark_local, _, _ = first_local(
        landmarks_local, v.get("nearest_landmark_local")
    )

    opening = v.get("opening_hours_structured") or v.get("opening_hours")
    if isinstance(opening, str):
        try:
            opening = json.loads(opening)
        except Exception:
            pass

    row = {
        "name": v.get("name"),
        "category": v.get("category"),
        "micro_location": v.get("micro_location"),
        "nearest_landmark": v.get("nearest_landmark"),
        "lat": v.get("lat"),
        "lng": v.get("lng"),
        "typical_dwell_minutes": v.get("typical_dwell_minutes"),
        "indoor_outdoor": v.get("indoor_outdoor"),
        "has_aircon": v.get("has_aircon"),
        "price_band": v.get("price_band"),
        "audience": v.get("audience") or [],
        "vibe_tags": v.get("vibe_tags") or [],
        "description": v.get("description") or "",
        "wheelchair_notes": v.get("wheelchair_notes"),
    }
    if name_local:
        row["name_local"] = name_local
        if name_src:
            row["name_local_source"] = name_src
        if name_ref:
            row["name_local_ref"] = name_ref
    if landmark_local:
        row["nearest_landmark_local"] = landmark_local
    if opening:
        row["opening_hours"] = opening

    # Dishes: keep fields the loader understands; leave unknowns out
    attached = []
    for d in by_venue.get(v.get("venue_id"), []):
        dish = {
            k: d.get(k)
            for k in (
                "name", "name_local", "dish_key", "price_local", "price_band",
                "currency_code", "contains", "may_contain", "suitable_for",
                "description",
            )
            if d.get(k) is not None
        }
        if dish.get("name"):
            attached.append(dish)
    if attached:
        row["dishes"] = attached

    # Drop nulls for readability
    out_venues.append({k: val for k, val in row.items() if val is not None})

wrapper = {
    "geo_region": dubai[0].get("geo_region") or "dubai_uae",
    "curated_at": date.today().isoformat(),
    "curator_notes": (
        "Exported from live Supabase on device day. Not re-curated. "
        "Preserve until a deliberate curation pass replaces it."
    ),
    "venues": out_venues,
}

out = Path("data/dubai_uae.json")
out.write_text(json.dumps(wrapper, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
print("wrote", out, "venues", len(out_venues))
PY
```

Verify the file parses, then prove the real loader can consume it. A parse
check is not a restore proof -- the Laos loader bug in 8dfc412 sat behind a
green test module while the committed data could not be loaded. Hard stop on
any dry-run error; fix the export mapping and re-run before committing.

```bash
python3 - <<'PY'
import json
w = json.load(open("data/dubai_uae.json", encoding="utf-8"))
assert w["geo_region"]
assert len(w["venues"]) >= 16, len(w["venues"])
print("ok", w["geo_region"], len(w["venues"]))
PY

python3 scripts/load_venues.py data/dubai_uae.json --dry-run
# Expect exit code 0 and zero validation errors. Warnings are allowed only if
# you understand them; errors mean the file is not restorable -- do not commit.
```

Commit only after the dry-run exits 0:

```bash
git add data/dubai_uae.json
git commit -m "$(cat <<'EOF'
data: export Dubai venues from live Supabase

The 16 Dubai rows existed only in the hosted database. Capture them under
data/ before any migration apply so a rebuild cannot silently drop them.
EOF
)"
git push origin main
git show origin/main:data/dubai_uae.json | python3 -c "import sys,json; w=json.load(sys.stdin); print(w['geo_region'], len(w['venues']))"
```

Hard stop until `origin/main` shows the file with the expected count.

---

## Step 3 -- schema dump and 0011 dual-column decision

PostgREST OpenAPI is already in `$SNAP/_live_schema.json`. Also capture
CHECK constraints and comments via SQL (OpenAPI cannot see them):

```bash
psql "$TB_DATABASE_URL" -v ON_ERROR_STOP=1 -A -F$'\t' -c "
SELECT column_name, data_type, udt_name
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'venues_rag'
ORDER BY ordinal_position;
" | tee /tmp/tb_venues_rag_columns.txt

psql "$TB_DATABASE_URL" -v ON_ERROR_STOP=1 -A -F$'\t' -c "
SELECT c.relname AS table_name, coalesce(a.attname, '') AS column_name, d.description
FROM pg_catalog.pg_description d
JOIN pg_catalog.pg_class c ON c.oid = d.objoid
LEFT JOIN pg_catalog.pg_attribute a
  ON a.attrelid = c.oid AND a.attnum = d.objsubid
WHERE c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
ORDER BY 1, 2;
" | tee /tmp/tb_pg_description.txt
```

Decide before apply:

```bash
python3 - <<'PY'
from pathlib import Path
cols = set()
for line in Path("/tmp/tb_venues_rag_columns.txt").read_text(encoding="utf-8").splitlines():
    if not line or line.startswith("column_name") or line.startswith("("):
        continue
    cols.add(line.split("\t")[0].strip())
print("venues_rag columns:", sorted(cols))
print("has name_local:", "name_local" in cols)
print("has names_local:", "names_local" in cols)
print("has nearest_landmark_local:", "nearest_landmark_local" in cols)
print("has landmarks_local:", "landmarks_local" in cols)
if "name_local" in cols and "names_local" not in cols:
    print("DECISION: write a backfill BEFORE 0011, or amend apply order.")
    print("DO NOT apply 0011 as-is: ADD COLUMN names_local would leave name_local unread.")
elif "name_local" in cols and "names_local" in cols:
    print("DECISION: both exist -- inspect which is populated; do not blind-apply.")
else:
    print("DECISION: safe to apply 0011 as written for the names_local path.")
PY
```
Also diff OpenAPI properties against migration-declared names if useful:

```bash
python3 - <<'PY'
import json, re, pathlib
snap = pathlib.Path("data/live_snapshot")
# pick latest stamp
stamps = sorted(p for p in snap.iterdir() if p.is_dir())
schema = json.loads((stamps[-1] / "_live_schema.json").read_text(encoding="utf-8"))
live_cols = set(schema.get("venues_rag", {}).keys())
mig = pathlib.Path("supabase/migrations/0011_venues_rag_missing_columns.sql").read_text(encoding="utf-8")
wanted = set(re.findall(r"ADD COLUMN IF NOT EXISTS (\w+)", mig))
print("0011 columns already live:", sorted(wanted & live_cols))
print("0011 columns missing live:", sorted(wanted - live_cols))
print("live columns not in 0011 add-set (sample):", sorted(live_cols - wanted)[:30])
PY
```

If the decision is "do not apply 0011 as-is", stop and write the finding into
`docs/AWAITING_VERIFICATION.md`. Do not proceed to Step 4.

---

## Step 4 -- apply migrations 0011 to 0018

Only after Step 2 is on `origin/main` and Step 3 decision is "safe".

```bash
git pull origin main
for f in \
  supabase/migrations/0011_venues_rag_missing_columns.sql \
  supabase/migrations/0012_venue_external_id.sql \
  supabase/migrations/0013_taxonomy_term.sql \
  supabase/migrations/0014_itinerary_normalisation.sql \
  supabase/migrations/0015_drift_fixes.sql \
  supabase/migrations/0016_comment_fixes.sql \
  supabase/migrations/0017_venues_rag_price_band_check.sql \
  supabase/migrations/0018_anonymous_identity.sql
do
  echo "APPLY $f"
  psql "$TB_DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"
done
```

If any file fails, stop. Do not continue the loop. Capture the error and the
file name in `docs/AWAITING_VERIFICATION.md`.

Confirm 0018 column:

```bash
psql "$TB_DATABASE_URL" -c "\d user_tiers"
# expect identity_kind
```

---

## Step 5 -- re-load Laos venues and glossary

Dry run first:

```bash
python3 scripts/load_venues.py \
  data/laos_luang_prabang.json \
  data/laos_vang_vieng.json \
  data/laos_vientiane.json \
  --dry-run

python3 scripts/load_dish_glossary.py data/laos_dish_glossary.json --dry-run
```

Then real load (writes embeddings -- needs `OPENAI_API_KEY`):

```bash
python3 scripts/load_venues.py \
  data/laos_luang_prabang.json \
  data/laos_vang_vieng.json \
  data/laos_vientiane.json

python3 scripts/load_dish_glossary.py data/laos_dish_glossary.json
```

Spot-check opening hours no longer null for Laos:

```bash
psql "$TB_DATABASE_URL" -c "
SELECT geo_region,
       count(*) AS venues,
       count(opening_hours_structured) AS with_hours
FROM venues_rag
WHERE geo_region LIKE '%laos%'
GROUP BY 1
ORDER BY 1;
"
```

---

## Step 6 -- pytest with live credentials

```bash
git pull origin main
export TB_SUPABASE_URL TB_SUPABASE_KEY
# Keep TB_ALLOW_ANONYMOUS unset/false unless deliberately testing that path.
pytest -q -ra
```

Record the summary line including skips. The five tests in
`tests/test_supabase_integration.py` must not skip for missing URL. Any
failure is a finding -- do not re-label it as environmental without evidence.

---

## Step 7 -- live checks (record results)

Run and paste outcomes into a new dated section of
`docs/AWAITING_VERIFICATION.md`:

```bash
psql "$TB_DATABASE_URL" -v ON_ERROR_STOP=1 <<'SQL'
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
SQL
```

Do not run `VALIDATE CONSTRAINT` on the price_band CHECKs today unless the
distinct-value read shows a clean set that matches the taxonomy seed. If it
does, validating is allowed; if it does not, leave NOT VALID and file the
finding.

---

## Step 8 -- close the day in docs

Append a dated block to `docs/AWAITING_VERIFICATION.md` covering:

- Dubai export commit SHA and venue count
- 0011 dual-column decision and what was applied
- pytest summary with skip reasons
- price_band / AED / pg_description / hybrid_venue_search observations

Update `docs/PROJECT_STATUS.md` only for facts that changed (migration
status rows, Dubai source-file risk). Do not hand-mirror test counts (R16).

Push documentation commits to main. Verify with:

```bash
git fetch origin
git show origin/main:docs/AWAITING_VERIFICATION.md | tail -80
```

---

## Explicit non-goals for this day

- No Flutter work
- No SPEC-09 client half
- No Railway / deploy
- No Genie code changes during the apply window
- No blind VALIDATE CONSTRAINT
- No Dubai dish `names_local` backfill
