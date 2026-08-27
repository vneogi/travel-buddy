-- SPEC-12 hardening: preserve localized driver-card fields through venue search.
-- Also adds the geo-region argument already used by SupabaseService.

DROP FUNCTION IF EXISTS hybrid_venue_search(
    VECTOR,
    DOUBLE PRECISION,
    DOUBLE PRECISION,
    DOUBLE PRECISION,
    FLOAT,
    INTEGER
);

CREATE FUNCTION hybrid_venue_search(
    query_embedding VECTOR(1536),
    user_lat DOUBLE PRECISION,
    user_lng DOUBLE PRECISION,
    radius_km DOUBLE PRECISION DEFAULT 15.0,
    sponsored_boost FLOAT DEFAULT 0.15,
    result_limit INTEGER DEFAULT 5,
    filter_geo_region TEXT DEFAULT NULL
)
RETURNS TABLE (
    venue_id UUID,
    name TEXT,
    description TEXT,
    micro_location TEXT,
    vibe_tags TEXT[],
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    opening_hours TEXT,
    geo_region TEXT,
    names_local JSONB,
    landmarks_local JSONB,
    nearest_landmark TEXT,
    similarity_score FLOAT,
    final_score FLOAT,
    distance_km DOUBLE PRECISION
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        v.venue_id,
        v.name,
        v.description,
        v.micro_location,
        v.vibe_tags,
        v.lat,
        v.lng,
        v.opening_hours,
        v.geo_region,
        v.names_local,
        v.landmarks_local,
        v.nearest_landmark,
        (1 - (v.embedding <=> query_embedding))::FLOAT AS similarity_score,
        (
            (1 - (v.embedding <=> query_embedding)) +
            (
                CASE
                    WHEN v.is_sponsored
                    THEN v.bid_weight * sponsored_boost
                    ELSE 0
                END
            )
        )::FLOAT AS final_score,
        (
            6371 * acos(
                cos(radians(user_lat)) * cos(radians(v.lat)) *
                cos(radians(v.lng) - radians(user_lng)) +
                sin(radians(user_lat)) * sin(radians(v.lat))
            )
        ) AS distance_km
    FROM venues_rag v
    WHERE (
        6371 * acos(
            cos(radians(user_lat)) * cos(radians(v.lat)) *
            cos(radians(v.lng) - radians(user_lng)) +
            sin(radians(user_lat)) * sin(radians(v.lat))
        )
    ) <= radius_km
      AND (
          filter_geo_region IS NULL
          OR v.geo_region = filter_geo_region
      )
    ORDER BY final_score DESC
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;
