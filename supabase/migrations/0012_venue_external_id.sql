-- Migration 0012: venue_external_id
-- Links venues to their canonical identifiers in external systems.
-- UNIQUE(source, external_id) prevents two venues from claiming the same
-- Wikidata item, which is the constraint that makes multi-city dedup possible.
--
-- The source vocabulary here (wikidata, osm, google, foursquare) is intentionally
-- SEPARATE from SPEC-12's VALID_LOCALIZED_SOURCES (name provenance). They overlap
-- (both include wikidata, osm) but mean different things: one says "this name came
-- from Wikidata", the other says "this venue IS Wikidata item Q12345".

CREATE TABLE IF NOT EXISTS venue_external_id (
    venue_id        UUID NOT NULL REFERENCES venues_rag(venue_id) ON DELETE CASCADE,
    source          TEXT NOT NULL,
    external_id     TEXT NOT NULL,
    confidence      FLOAT DEFAULT 1.0,
    verified_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_venue_external_id_venue
    ON venue_external_id(venue_id);
