-- Migration 0016: Fix pg_description for dish_glossary (ASCII) and retire
-- suitable_for claim per SPEC-14.
--
-- 0010 was applied when the table comment contained an em-dash (U+2014).
-- The file was fixed in d008040 but the live pg_description still holds the
-- original bytes. Re-issuing COMMENT ON corrects the database to match.
--
-- SPEC-14 retires suitable_for as a dietary claim: no badge, no filter, no
-- presentation. The column stays (backcompat) but the comment must stop
-- documenting it as an active feature.

-- ============================================================================
-- Fix 1: dish_glossary table comment -- replace em-dash with ASCII
-- ============================================================================

COMMENT ON TABLE dish_glossary IS
    'Canonical dish definitions with allergen safety data. Single source of truth -- venue_dish references via dish_key.';

-- ============================================================================
-- Fix 2: suitable_for column comment -- record SPEC-14 retirement
-- ============================================================================

COMMENT ON COLUMN dish_glossary.suitable_for IS
    'RETIRED (SPEC-14). Array of dietary labels. Column retained for backcompat but no longer presented, filtered, or claimed. See docs/specs/SPEC-14-dietary-model.md.';
