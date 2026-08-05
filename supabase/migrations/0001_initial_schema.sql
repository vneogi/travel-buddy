-- =============================================================================
-- Migration: 0001_initial_schema.sql
-- Description: Baseline schema — retrofits the existing Travel Buddy Supabase
--              schema (user_tiers, trip_states, venues_rag, cached_responses,
--              event_log) plus all stored functions. This is the known state as
--              of commit #34, previously managed via models/database.py +
--              supabase_service.py. From this point forward, ALL schema changes
--              go through versioned migrations.
-- Applied: 2026-08-05 (retroactive baseline)
-- =============================================================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS postgis;

-- =============================================================================
-- Table: user_tiers
-- Purpose: Tracks user subscription status and daily reroute quotas
-- =============================================================================
CREATE TABLE IF NOT EXISTS user_tiers (
    user_id UUID PRIMARY KEY,
    tier_status TEXT NOT NULL DEFAULT 'free' CHECK (tier_status IN ('free', 'pro')),
    daily_reroute_count INTEGER NOT NULL DEFAULT 0,
    max_daily_reroutes INTEGER NOT NULL DEFAULT 5,
    last_reset_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================================================
-- Table: trip_states
-- Purpose: Persistent storage for active trip state objects
-- =============================================================================
CREATE TABLE IF NOT EXISTS trip_states (
    trip_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES user_tiers(user_id),
    state_json JSONB NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trip_states_user ON trip_states(user_id);
CREATE INDEX IF NOT EXISTS idx_trip_states_active ON trip_states(is_active) WHERE is_active = true;

-- =============================================================================
-- Table: cached_responses
-- Purpose: Semantic cache to avoid redundant LLM calls
-- =============================================================================
CREATE TABLE IF NOT EXISTS cached_responses (
    cache_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_embedding VECTOR(1536),
    query_text TEXT NOT NULL,
    cached_response_text TEXT NOT NULL,
    geo_fence_center POINT,
    hit_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() + INTERVAL '24 hours')
);

CREATE INDEX IF NOT EXISTS idx_cached_responses_embedding
    ON cached_responses USING ivfflat (query_embedding vector_cosine_ops)
    WITH (lists = 100);

-- =============================================================================
-- Table: venues_rag
-- Purpose: Dubai venue knowledge base with vector embeddings for RAG
-- =============================================================================
CREATE TABLE IF NOT EXISTS venues_rag (
    venue_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    micro_location TEXT NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    lng DOUBLE PRECISION NOT NULL,
    vibe_tags TEXT[] DEFAULT '{}',
    audience TEXT[] DEFAULT '{}',
    category TEXT DEFAULT 'experience',
    opening_hours TEXT DEFAULT '09:00-23:00',
    is_sponsored BOOLEAN DEFAULT false,
    bid_weight FLOAT DEFAULT 0.0,
    embedding VECTOR(1536),
    source_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_venues_embedding
    ON venues_rag USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_venues_location ON venues_rag(micro_location);
CREATE INDEX IF NOT EXISTS idx_venues_vibe ON venues_rag USING gin(vibe_tags);
CREATE INDEX IF NOT EXISTS idx_venues_sponsored ON venues_rag(is_sponsored) WHERE is_sponsored = true;

-- =============================================================================
-- Table: event_log
-- Purpose: Audit trail of all user events for analytics
-- =============================================================================
CREATE TABLE IF NOT EXISTS event_log (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_tiers(user_id),
    trip_id UUID REFERENCES trip_states(trip_id),
    event_type TEXT NOT NULL,
    event_payload JSONB,
    routing_tier_used TEXT,
    from_cache BOOLEAN DEFAULT false,
    token_cost_estimate FLOAT DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_event_log_user ON event_log(user_id);
CREATE INDEX IF NOT EXISTS idx_event_log_trip ON event_log(trip_id);

-- =============================================================================
-- Function: Reset daily reroute counts (called by cron)
-- =============================================================================
CREATE OR REPLACE FUNCTION reset_daily_reroutes()
RETURNS void AS $$
BEGIN
    UPDATE user_tiers
    SET daily_reroute_count = 0,
        last_reset_date = CURRENT_DATE
    WHERE last_reset_date < CURRENT_DATE;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- Function: Hybrid venue search with sponsored boost
-- =============================================================================
CREATE OR REPLACE FUNCTION hybrid_venue_search(
    query_embedding VECTOR(1536),
    user_lat DOUBLE PRECISION,
    user_lng DOUBLE PRECISION,
    radius_km DOUBLE PRECISION DEFAULT 15.0,
    sponsored_boost FLOAT DEFAULT 0.15,
    result_limit INTEGER DEFAULT 5
)
RETURNS TABLE (
    venue_id UUID, name TEXT, description TEXT, micro_location TEXT,
    vibe_tags TEXT[], lat DOUBLE PRECISION, lng DOUBLE PRECISION,
    opening_hours TEXT, similarity_score FLOAT, final_score FLOAT,
    distance_km DOUBLE PRECISION
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        v.venue_id, v.name, v.description, v.micro_location, v.vibe_tags,
        v.lat, v.lng, v.opening_hours,
        (1 - (v.embedding <=> query_embedding))::FLOAT AS similarity_score,
        ((1 - (v.embedding <=> query_embedding)) +
         (CASE WHEN v.is_sponsored THEN v.bid_weight * sponsored_boost ELSE 0 END))::FLOAT AS final_score,
        (6371 * acos(
            cos(radians(user_lat)) * cos(radians(v.lat)) *
            cos(radians(v.lng) - radians(user_lng)) +
            sin(radians(user_lat)) * sin(radians(v.lat))
        )) AS distance_km
    FROM venues_rag v
    WHERE (6371 * acos(
            cos(radians(user_lat)) * cos(radians(v.lat)) *
            cos(radians(v.lng) - radians(user_lng)) +
            sin(radians(user_lat)) * sin(radians(v.lat))
        )) <= radius_km
    ORDER BY final_score DESC
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- Function: Atomic reroute increment (unconditional; kept for compatibility)
-- =============================================================================
CREATE OR REPLACE FUNCTION increment_reroute(target_user_id UUID)
RETURNS INTEGER AS $$
DECLARE
    new_count INTEGER;
BEGIN
    UPDATE user_tiers
    SET daily_reroute_count = daily_reroute_count + 1,
        updated_at = NOW()
    WHERE user_id = target_user_id
    RETURNING daily_reroute_count INTO new_count;
    RETURN new_count;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- Function: Atomic check-and-increment (consume_reroute)
-- Returns new count, or NULL if user is already at the limit.
-- =============================================================================
CREATE OR REPLACE FUNCTION consume_reroute(target_user_id UUID)
RETURNS INTEGER AS $$
DECLARE
    new_count INTEGER;
BEGIN
    UPDATE user_tiers
    SET daily_reroute_count = daily_reroute_count + 1,
        updated_at = NOW()
    WHERE user_id = target_user_id
      AND daily_reroute_count < max_daily_reroutes
    RETURNING daily_reroute_count INTO new_count;
    RETURN new_count;  -- NULL when no row updated (over the cap)
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- Function: Semantic cache similarity search
-- =============================================================================
CREATE OR REPLACE FUNCTION check_semantic_cache(
    query_embedding VECTOR(1536),
    similarity_threshold FLOAT DEFAULT 0.92
)
RETURNS TABLE (
    cache_id UUID, cached_response_text TEXT,
    similarity_score FLOAT, hit_count INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT c.cache_id, c.cached_response_text,
        (1 - (c.query_embedding <=> query_embedding))::FLOAT AS similarity_score,
        c.hit_count
    FROM cached_responses c
    WHERE c.expires_at > NOW()
      AND (1 - (c.query_embedding <=> query_embedding)) >= similarity_threshold
    ORDER BY similarity_score DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- ROLLBACK (manual — apply these in reverse order to undo this migration):
-- DROP FUNCTION IF EXISTS check_semantic_cache;
-- DROP FUNCTION IF EXISTS consume_reroute;
-- DROP FUNCTION IF EXISTS increment_reroute;
-- DROP FUNCTION IF EXISTS hybrid_venue_search;
-- DROP FUNCTION IF EXISTS reset_daily_reroutes;
-- DROP INDEX IF EXISTS idx_event_log_trip;
-- DROP INDEX IF EXISTS idx_event_log_user;
-- DROP TABLE IF EXISTS event_log;
-- DROP INDEX IF EXISTS idx_venues_sponsored;
-- DROP INDEX IF EXISTS idx_venues_vibe;
-- DROP INDEX IF EXISTS idx_venues_location;
-- DROP INDEX IF EXISTS idx_venues_embedding;
-- DROP TABLE IF EXISTS venues_rag;
-- DROP INDEX IF EXISTS idx_cached_responses_embedding;
-- DROP TABLE IF EXISTS cached_responses;
-- DROP INDEX IF EXISTS idx_trip_states_active;
-- DROP INDEX IF EXISTS idx_trip_states_user;
-- DROP TABLE IF EXISTS trip_states;
-- DROP TABLE IF EXISTS user_tiers;
-- DROP EXTENSION IF EXISTS postgis;
-- DROP EXTENSION IF EXISTS vector;
-- =============================================================================
