-- Migration 0015: Four drift fixes (price_band vocab, dish localisation,
-- price currency, embedding provenance).
--
-- NOTE: This migration is NOT purely additive. Fix A drops an incorrect CHECK
-- constraint on venue_dish.price_band and replaces it with the taxonomy-aligned
-- vocabulary using NOT VALID to avoid aborting on existing rows.

-- ============================================================================
-- Fix A: venue_dish.price_band vocabulary -- align CHECK with taxonomy_term seed
-- ============================================================================
-- Old CHECK (from 0005): ('budget', 'mid', 'premium', 'splurge')
-- Taxonomy seed (0013):   ('budget', 'free', 'mid', 'splurge')
-- Data in use:            budget, mid (Laos dishes); free, splurge (potential)

-- Drop the old constraint (Postgres names inline CHECKs as <table>_<column>_check)
ALTER TABLE venue_dish DROP CONSTRAINT IF EXISTS venue_dish_price_band_check;

-- Re-add with taxonomy-authoritative vocabulary. NOT VALID skips validating
-- existing rows so the migration does not abort if the hosted DB contains
-- 'premium' values from Dubai data not visible in data/.
ALTER TABLE venue_dish
    ADD CONSTRAINT venue_dish_price_band_check
    CHECK (price_band IN ('budget', 'free', 'mid', 'splurge'))
    NOT VALID;

-- Run this manually ONLY after confirming:
--   SELECT DISTINCT price_band FROM venue_dish;
-- returns only values in the set above.
-- ALTER TABLE venue_dish VALIDATE CONSTRAINT venue_dish_price_band_check;

-- ============================================================================
-- Fix B: Dish localisation parity -- add names_local JSONB
-- ============================================================================
-- venues_rag.names_local shape: {"lo": {"value": "...", "source": "...", "ref": "..."}}
-- venue_dish.name_local is bare TEXT. Add the structured column, backfill Laos
-- rows only, keep the old column marked deprecated.

ALTER TABLE venue_dish
    ADD COLUMN IF NOT EXISTS names_local JSONB DEFAULT NULL;

COMMENT ON COLUMN venue_dish.names_local IS
    'Structured localised name: {"<lang>": {"value": "...", "source": "generated|...", "ref": null}}. Same shape as venues_rag.names_local.';

COMMENT ON COLUMN venue_dish.name_local IS
    'DEPRECATED -- use names_local JSONB instead. Kept for transition dual-read.';

-- Backfill: Laos rows only (language "lo"). Scoped via JOIN to venues_rag
-- geo_region so we do not invent a language for Dubai or other regions.
-- A separate region-specific pass handles non-Laos rows, exactly as with
-- AED currency below.
UPDATE venue_dish vd
SET names_local = jsonb_build_object(
    'lo', jsonb_build_object(
        'value', vd.name_local,
        'source', 'generated',
        'ref', NULL
    )
)
FROM venues_rag vr
WHERE vd.venue_id = vr.venue_id
  AND vr.geo_region IN ('luang_prabang_laos', 'vang_vieng_laos', 'vientiane_laos')
  AND vd.name_local IS NOT NULL
  AND vd.names_local IS NULL;

-- ============================================================================
-- Fix C: Price currency and unit
-- ============================================================================
-- price_local is INTEGER in minor units per ISO 4217 exponent:
--   LAK (exponent 0): 35000 means 35000 LAK
--   AED (exponent 2): 4500 means 45.00 AED
-- The 0009 comment said "45 AED" which is ambiguous. This column clarifies.

ALTER TABLE venue_dish
    ADD COLUMN IF NOT EXISTS currency_code TEXT DEFAULT NULL;

COMMENT ON COLUMN venue_dish.currency_code IS
    'ISO 4217 currency code (e.g. LAK, AED). price_local is in minor units per the ISO exponent (LAK exp=0, AED exp=2).';

COMMENT ON COLUMN venue_dish.price_local IS
    'Price in local currency minor units per ISO 4217 exponent. LAK@exp0: 35000 = 35000 LAK. AED@exp2: 4500 = 45.00 AED.';

-- Existing AED rows (Dubai) are suspect because the original comment implied
-- major units (45 AED not 4500) -- they need a device-check before trusting
-- the values. We do NOT blindly backfill AED here; the loader writes
-- currency_code going forward. A separate data-fix pass handles existing
-- Dubai dishes.

-- ============================================================================
-- Fix D: Embedding provenance
-- ============================================================================
-- VECTOR(1536) exists in venues_rag and cached_responses with no record of
-- which model produced it. Add embedding_model so the column is never written
-- without a model tag.

ALTER TABLE venues_rag
    ADD COLUMN IF NOT EXISTS embedding_model TEXT DEFAULT NULL;

COMMENT ON COLUMN venues_rag.embedding_model IS
    'Model identifier that produced the embedding vector (e.g. text-embedding-3-small).';

ALTER TABLE cached_responses
    ADD COLUMN IF NOT EXISTS embedding_model TEXT DEFAULT NULL;

COMMENT ON COLUMN cached_responses.embedding_model IS
    'Model identifier that produced the query_embedding vector.';
