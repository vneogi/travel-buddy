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
