-- Migration 0013: taxonomy_term
-- Versioned vocabulary for the five closed taxonomies. The composite primary key
-- (taxonomy, term) is non-negotiable: 'budget' is valid in BOTH price_band and
-- vibe_tag and they are different things.
--
-- The loader validates against Python constants (not this table) so dry-run works
-- without credentials. A test asserts the constants and this table agree exactly,
-- in both directions.

CREATE TABLE IF NOT EXISTS taxonomy_term (
    taxonomy        TEXT NOT NULL,
    term            TEXT NOT NULL,
    introduced_in   TEXT DEFAULT '0013',
    deprecated_in   TEXT,
    replaced_by     TEXT,
    notes           TEXT,
    PRIMARY KEY (taxonomy, term)
);

-- Seed: 45 terms extracted from venue data (category 16, vibe_tag 15, audience 7,
-- price_band 4, indoor_outdoor 3).

-- category (16)
INSERT INTO taxonomy_term (taxonomy, term) VALUES
    ('category', 'bar'),
    ('category', 'cafe'),
    ('category', 'craft_workshop'),
    ('category', 'hospital'),
    ('category', 'market'),
    ('category', 'massage_spa'),
    ('category', 'museum'),
    ('category', 'nature'),
    ('category', 'pharmacy'),
    ('category', 'restaurant'),
    ('category', 'river_activity'),
    ('category', 'street_food'),
    ('category', 'temple'),
    ('category', 'transport_hub'),
    ('category', 'viewpoint'),
    ('category', 'walking_area')
ON CONFLICT DO NOTHING;

-- vibe_tag (15)
INSERT INTO taxonomy_term (taxonomy, term) VALUES
    ('vibe_tag', 'adventurous'),
    ('vibe_tag', 'authentic'),
    ('vibe_tag', 'budget'),
    ('vibe_tag', 'hidden'),
    ('vibe_tag', 'historical'),
    ('vibe_tag', 'lively'),
    ('vibe_tag', 'local_favourite'),
    ('vibe_tag', 'photogenic'),
    ('vibe_tag', 'quiet'),
    ('vibe_tag', 'riverside'),
    ('vibe_tag', 'romantic'),
    ('vibe_tag', 'scenic'),
    ('vibe_tag', 'spiritual'),
    ('vibe_tag', 'touristy'),
    ('vibe_tag', 'upscale')
ON CONFLICT DO NOTHING;

-- audience (7)
INSERT INTO taxonomy_term (taxonomy, term) VALUES
    ('audience', 'couple'),
    ('audience', 'family_teens'),
    ('audience', 'family_young_kids'),
    ('audience', 'friends_group'),
    ('audience', 'mobility_limited'),
    ('audience', 'seniors'),
    ('audience', 'solo')
ON CONFLICT DO NOTHING;

-- price_band (4)
INSERT INTO taxonomy_term (taxonomy, term) VALUES
    ('price_band', 'budget'),
    ('price_band', 'free'),
    ('price_band', 'mid'),
    ('price_band', 'splurge')
ON CONFLICT DO NOTHING;

-- indoor_outdoor (3)
INSERT INTO taxonomy_term (taxonomy, term) VALUES
    ('indoor_outdoor', 'indoor'),
    ('indoor_outdoor', 'mixed'),
    ('indoor_outdoor', 'outdoor')
ON CONFLICT DO NOTHING;

-- cuisine (4) -- from laos_dish_glossary.json
INSERT INTO taxonomy_term (taxonomy, term) VALUES
    ('cuisine', 'drink'),
    ('cuisine', 'french_colonial'),
    ('cuisine', 'lao'),
    ('cuisine', 'vietnamese')
ON CONFLICT DO NOTHING;

-- dish_type (12)
INSERT INTO taxonomy_term (taxonomy, term) VALUES
    ('dish_type', 'alcoholic_drink'),
    ('dish_type', 'bread_pastry'),
    ('dish_type', 'coffee_tea'),
    ('dish_type', 'dessert'),
    ('dish_type', 'grill'),
    ('dish_type', 'noodle_soup'),
    ('dish_type', 'rice_dish'),
    ('dish_type', 'salad'),
    ('dish_type', 'snack'),
    ('dish_type', 'soft_drink'),
    ('dish_type', 'stew'),
    ('dish_type', 'street_snack')
ON CONFLICT DO NOTHING;

-- spice_level (4)
INSERT INTO taxonomy_term (taxonomy, term) VALUES
    ('spice_level', 'hot'),
    ('spice_level', 'medium'),
    ('spice_level', 'mild'),
    ('spice_level', 'none')
ON CONFLICT DO NOTHING;

-- suitable_for (4)
INSERT INTO taxonomy_term (taxonomy, term) VALUES
    ('suitable_for', 'gluten_free'),
    ('suitable_for', 'halal'),
    ('suitable_for', 'vegan'),
    ('suitable_for', 'vegetarian')
ON CONFLICT DO NOTHING;

-- adventurousness (5) -- integer scale stored as string terms
INSERT INTO taxonomy_term (taxonomy, term) VALUES
    ('adventurousness', '1'),
    ('adventurousness', '2'),
    ('adventurousness', '3'),
    ('adventurousness', '4'),
    ('adventurousness', '5')
ON CONFLICT DO NOTHING;

-- NOTE: glossary typical_price_band uses the SAME value set as venue price_band
-- (a strict subset: only 'budget' and 'mid' appear in current data, but the
-- full vocabulary {budget, free, mid, splurge} applies). No separate taxonomy
-- needed -- typical_price_band is an alias for the price_band taxonomy.
