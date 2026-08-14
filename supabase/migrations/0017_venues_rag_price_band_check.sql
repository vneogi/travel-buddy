-- Migration 0017: Constrain venues_rag.price_band to taxonomy vocabulary.
--
-- venue_dish.price_band was constrained in 0015. venues_rag.price_band is
-- the same domain (budget/free/mid/splurge) from the same taxonomy_term seed
-- (0013) but had no CHECK. This closes the drift class: all three price_band
-- columns (venue_dish, venues_rag, and any future table) are now
-- taxonomy-aligned.
--
-- NOT VALID: avoids aborting if the hosted DB has unexpected values in
-- existing rows. Validate manually after confirming:
--   SELECT DISTINCT price_band FROM venues_rag WHERE price_band IS NOT NULL;

ALTER TABLE venues_rag
    ADD CONSTRAINT venues_rag_price_band_check
    CHECK (price_band IN ('budget', 'free', 'mid', 'splurge'))
    NOT VALID;

-- Run manually after data verification:
-- ALTER TABLE venues_rag VALIDATE CONSTRAINT venues_rag_price_band_check;
