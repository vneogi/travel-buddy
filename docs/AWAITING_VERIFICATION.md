# Awaiting Device Verification

No test laptop available ~Aug 10-17 2026. Nothing below can be verified
on device or against real Supabase until then.

pytest is the ONLY real verification available during this window.
Dart/PowerShell commits are labelled [UNVERIFIED].

## Completed (verified via pytest)

### arrival_delta server derivation
- Commit: 564fd7d
- Derives arrival_delta from visited_confirmed.captured_at vs node.scheduled_start
- One tap -> two data points
- Verified: pytest green (services/arrival_delta_service.py + tests/test_arrival_delta.py)

## Commits Awaiting Device Verification

| # | SHA | What | Verify with |
|---|-----|------|-------------|
| 84 | 21249f4 | fix(dart): 4 compile errors + lint warnings | `flutter analyze && flutter test` |
| 85 | 951f0ca | feat(spec-07): wire typed signal methods to UI | `flutter analyze && flutter test` |
| 86 | c6712bb | fix(scripts): purge non-ASCII + add BOM | `.\scripts\smoke-test.ps1` |

## Work Queue (priority order, no laptop needed)

1. reroute_rejected + swap sheet UI -- last missing behavioural signal [UNVERIFIED Dart]
2. SPEC-09 anonymous device identity [UNVERIFIED Dart + backend]
3. VALID_DISH_CONTAINS relocation to config/dietary.py [BLOCKED - has em-dashes]

## Known Open Issues

| Issue | Detail |
|-------|--------|
| opening_hours null (58 Laos venues) | Loader field-name fix committed; data needs re-load with `--dry-run` removed |
| halal + pork passes allergen check | No LABEL_EXCLUDES_ALLERGENS rule for halal. Safety hole. |
| mobility_limited overcorrected | 65% of venues flagged -- too loose |
| Vientiane zero massage_spa | Fatigue-reroute target missing in one region |
| VALID_DISH_CONTAINS location (R5) | In load_dish_glossary.py, belongs in config/dietary.py |

## Workspace-Write Limitations

See docs/ENGINEERING_RULES.md rules R14 and R15 for the full explanation.

Short version: editAsset silently fails on files with non-ASCII bytes,
and the safety filter blocks all direct filesystem writes. Use the
createAsset + git rm/mv workaround for files that contain em-dashes,
emoji, or box-drawing characters.

Files known to have non-ASCII (cannot be patched via editAsset):
- config/dietary.py (em-dashes in comments)
- config/regions.py (box-drawing chars)
- mobile/lib/features/itinerary/itinerary_screen.dart (em-dash)
- All Lao venue JSON files (Lao script)
