-- Migration 0010: dish_glossary table + venue_dish.dish_key FK
--
-- Allergen/dietary safety facts live ONCE in the glossary.
-- Venues reference them via dish_key. Duplicated safety data across
-- venue rows will drift, and drift here is dangerous.
--
-- ADDITIVE: new table + new nullable FK column on venue_dish.

CREATE TABLE IF NOT EXISTS dish_glossary (
    dish_key        TEXT PRIMARY KEY,              -- e.g. 'khao_piak_sen', 'croissant_plain'
    canonical_name  TEXT NOT NULL,                 -- Human-readable: 'Khao Piak Sen'
    cuisine         TEXT,                          -- 'lao', 'french', etc.
    contains        TEXT[] NOT NULL DEFAULT '{}',  -- Confirmed allergens
    may_contain     TEXT[] NOT NULL DEFAULT '{}',  -- Cross-contamination risk
    suitable_for    TEXT[] NOT NULL DEFAULT '{}',  -- Dietary labels this dish meets
    description     TEXT,                          -- Optional: what it is
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE dish_glossary IS 'Canonical dish definitions with allergen safety data. Single source of truth — venue_dish references via dish_key.';
COMMENT ON COLUMN dish_glossary.dish_key IS 'Snake_case identifier, globally unique. Used as FK from venue_dish.';
COMMENT ON COLUMN dish_glossary.contains IS 'Array of confirmed allergens from config/dietary.py VALID_ALLERGENS.';
COMMENT ON COLUMN dish_glossary.may_contain IS 'Array of cross-contamination allergens.';
COMMENT ON COLUMN dish_glossary.suitable_for IS 'Array of dietary labels from config/dietary.py VALID_DIETARY_LABELS.';

-- Add dish_key FK to venue_dish (nullable — existing rows will be NULL until backfilled)
ALTER TABLE venue_dish
    ADD COLUMN IF NOT EXISTS dish_key TEXT REFERENCES dish_glossary(dish_key);

COMMENT ON COLUMN venue_dish.dish_key IS 'FK to dish_glossary. Allergen facts live there, not here.';

-- Index for join performance
CREATE INDEX IF NOT EXISTS idx_venue_dish_dish_key ON venue_dish(dish_key);
