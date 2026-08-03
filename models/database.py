"""Travel Buddy MVP - Database Schema Definitions

SQL schema for Supabase/PostgreSQL with pgvector support.
Used for initial migration and as documentation.
"""

# SQL to initialize the database
SCHEMA_SQL = """
-- Enable pgvector extension
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

CREATE INDEX idx_trip_states_user ON trip_states(user_id);
CREATE INDEX idx_trip_states_active ON trip_states(is_active) WHERE is_active = true;

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

CREATE INDEX idx_cached_responses_embedding
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

CREATE INDEX idx_venues_embedding
    ON venues_rag USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
CREATE INDEX idx_venues_location ON venues_rag(micro_location);
CREATE INDEX idx_venues_vibe ON venues_rag USING gin(vibe_tags);
CREATE INDEX idx_venues_sponsored ON venues_rag(is_sponsored) WHERE is_sponsored = true;

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

CREATE INDEX idx_event_log_user ON event_log(user_id);
CREATE INDEX idx_event_log_trip ON event_log(trip_id);

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
"""
