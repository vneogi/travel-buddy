-- Migration 0009: Add cuisine and price_local to venue_dish
-- Supports multi-regional dish data (Laos cuisines, local currency pricing)
-- ADDITIVE: new nullable columns only, no data loss risk.

ALTER TABLE venue_dish
  ADD COLUMN IF NOT EXISTS cuisine TEXT DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS price_local INTEGER DEFAULT NULL;

COMMENT ON COLUMN venue_dish.cuisine IS 'Cuisine type: lao, thai, french, fusion, international, vietnamese, emirati, etc.';
COMMENT ON COLUMN venue_dish.price_local IS 'Price in local currency minor units (e.g. 35000 LAK, 45 AED). No decimals.';
