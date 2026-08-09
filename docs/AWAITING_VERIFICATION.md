# Awaiting Device Verification

No test laptop available ~Aug 10-17 2026. Nothing below can be verified
on device or against real Supabase until then.

pytest is the ONLY real verification available during this window.
Dart/PowerShell commits are labelled [UNVERIFIED].

## Queue (priority order)

### 1. arrival_delta server derivation [IN PROGRESS]
- Pure backend, pytest-verifiable
- Derive arrival_delta from visited_confirmed.captured_at vs node.scheduled_start
- One tap -> two data points
- Status: not started

### 2. smoke-test.ps1 content bugs [BLOCKED - local only]
- Missing captured_at in signal payload (422 from API)
- signal_id uses Substring(0,8) not full UUID (PK violation)
- Assert-Check param typed [bool] instead of untyped with coercion
- Non-ASCII purge + BOM: DONE (commit #86)
- Content fixes: must be applied locally (exact edits documented in session)
- Verify: `.\scripts\smoke-test.ps1` with backend running

### 3. VALID_DISH_CONTAINS R5 violation [BLOCKED - local only]
- Currently defined in load_dish_glossary.py (should be in config/dietary.py)
- config/dietary.py has em-dashes -> can't be patched via editAsset
- Fix: move VALID_DISH_CONTAINS into dietary.py, replace em-dashes with --
- Verify: pytest (import from new location)

### 4. reroute_rejected + swap sheet UI [UNVERIFIED Dart]
- Last missing behavioural signal
- Needs SwapSheet widget showing alternatives user can reject
- Verify: flutter analyze && flutter test

### 5. SPEC-09 anonymous identity [UNVERIFIED Dart + backend]
- Spec written, prerequisite for tester builds
- Verify: flutter test + pytest

## Commits Awaiting Verification

| Commit | What | Verify with |
|--------|------|-------------|
| #84 | fix(dart): 4 compile errors + lint warnings | flutter analyze && flutter test |
| #85 | feat(spec-07): wire typed signal methods to UI | flutter analyze && flutter test |
| #86 | fix(scripts): purge non-ASCII + add BOM | .\scripts\smoke-test.ps1 |
| #87 | feat(glossary): load_dish_glossary.py loader | python scripts/load_dish_glossary.py data/laos_dish_glossary.json --dry-run |

## Workspace-Write Limitations (R14/R15)

The safety filter blocks ALL writes to /Workspace files via:
- open(path, 'w') / open(path, 'wb')
- shutil.copy2(src, workspace_path)
- sed -i on workspace paths
- subprocess writing to workspace

editAsset ALSO fails on files with non-ASCII (em-dash U+2014, emoji, box-drawing).

What DOES work:
- createAsset (new files only)
- editAsset on pure-ASCII files that were JUST created (same session)
- editAsset on pure-ASCII files in non-git workspace locations
- Reading any file (executeCode open(path, 'r'), readAssetById)

Consequence: bias toward NEW modules over refactors. Edits to existing
non-ASCII files must be done locally.

## Data Nudges (not blocking)

- Vientiane has 0 massage_spa venues (needed as fatigue-reroute target)
- mobility_limited on 36/55 venues (65%) -- overcorrected
- halal + pork passes cross-field check (no LABEL_EXCLUDES rule for halal)
  Genuine safety hole for Muslim travellers in SE Asia
- Loader category restrictions: dishes on market/craft_workshop may be rejected
