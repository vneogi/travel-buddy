"""Travel Buddy MVP - Production Supabase Service

Replaces the in-memory database_service.py with real Supabase operations.
Handles PostgreSQL + pgvector for:
  - User tier management (with daily reset logic)
  - Trip state persistence (JSONB)
  - Venue RAG storage and hybrid vector search
  - Semantic cache with TTL
  - Event logging for analytics

Usage:
  from services.supabase_service import supabase_db
  # Then swap db_service references to supabase_db

Requires:
  pip install supabase httpx
  Environment vars: TB_SUPABASE_URL, TB_SUPABASE_KEY
"""

import json
import uuid
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import httpx

from config.settings import settings
from models.schemas import (
    TierStatus,
    TripState,
    UserTier,
    VenueRAG,
    VenueSearchResult,
)


class SupabaseService:
    """Production database service using Supabase REST API.

    Uses httpx for async-ready HTTP calls to Supabase PostgREST.
    For the MVP, can also use the supabase-py client.
    """

    def __init__(self):
        self.url = settings.supabase_url
        self.key = settings.supabase_key
        self._client = None

    @property
    def client(self):
        """Lazy-initialize Supabase client."""
        if self._client is None:
            try:
                from supabase import create_client
                self._client = create_client(self.url, self.key)
            except ImportError:
                raise ImportError(
                    "supabase package required. Install with: pip install supabase"
                )
        return self._client

    @property
    def headers(self) -> Dict:
        """Auth headers for direct PostgREST calls."""
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    # =========================================================================
    # User Tier Operations
    # =========================================================================

    def get_or_create_user(self, user_id: str) -> UserTier:
        """Get user tier info, creating free-tier user if not exists."""
        result = (
            self.client.table("user_tiers")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )

        if result.data:
            user_data = result.data[0]
            # Check if daily reset needed
            if user_data["last_reset_date"] != date.today().isoformat():
                self._reset_daily_reroutes(user_id)
                user_data["daily_reroute_count"] = 0
            return UserTier(
                user_id=user_data["user_id"],
                tier_status=TierStatus(user_data["tier_status"]),
                daily_reroute_count=user_data["daily_reroute_count"],
                max_daily_reroutes=user_data["max_daily_reroutes"],
            )
        else:
            # Create new free-tier user
            new_user = {
                "user_id": user_id,
                "tier_status": "free",
                "daily_reroute_count": 0,
                "max_daily_reroutes": settings.max_daily_reroutes_free,
                "last_reset_date": date.today().isoformat(),
            }
            self.client.table("user_tiers").insert(new_user).execute()
            return UserTier(**new_user)

    def _reset_daily_reroutes(self, user_id: str) -> None:
        """Reset daily reroute count for a user."""
        self.client.table("user_tiers").update({
            "daily_reroute_count": 0,
            "last_reset_date": date.today().isoformat(),
        }).eq("user_id", user_id).execute()

    def increment_reroute_count(self, user_id: str) -> int:
        """Increment daily reroute count. Returns new count."""
        # Use RPC for atomic increment
        result = self.client.rpc(
            "increment_reroute",
            {"target_user_id": user_id}
        ).execute()

        if result.data:
            return result.data

        # Fallback: read-modify-write
        user = self.get_or_create_user(user_id)
        new_count = user.daily_reroute_count + 1
        self.client.table("user_tiers").update({
            "daily_reroute_count": new_count,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("user_id", user_id).execute()
        return new_count

    def check_reroute_allowed(self, user_id: str) -> Tuple[bool, int, int]:
        """Check if user can reroute. Returns (allowed, remaining, max)."""
        user = self.get_or_create_user(user_id)
        remaining = user.max_daily_reroutes - user.daily_reroute_count
        return (remaining > 0, max(0, remaining), user.max_daily_reroutes)

    def consume_reroute(self, user_id: str):
        """Atomically reserve one reroute via the consume_reroute() SQL function.
        Returns the new count (truthy) if granted, or None if over the cap."""
        self.get_or_create_user(user_id)  # ensures row exists + daily reset
        result = self.client.rpc("consume_reroute", {"target_user_id": user_id}).execute()
        return result.data  # new count, or None when over the limit

    def upgrade_user(self, user_id: str) -> UserTier:
        """Upgrade user to pro tier."""
        self.client.table("user_tiers").update({
            "tier_status": "pro",
            "max_daily_reroutes": settings.max_daily_reroutes_pro,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("user_id", user_id).execute()
        return self.get_or_create_user(user_id)

    def downgrade_user(self, user_id: str) -> UserTier:
        """Downgrade a user back to the free tier."""
        self.client.table("user_tiers").update({
            "tier_status": "free",
            "max_daily_reroutes": settings.max_daily_reroutes_free,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("user_id", user_id).execute()
        return self.get_or_create_user(user_id)

    def get_venue_count(self) -> int:
        result = self.client.table("venues_rag").select("venue_id", count="exact").execute()
        return result.count or 0

    # =========================================================================
    # Trip State Operations
    # =========================================================================

    def save_trip(self, trip_state: TripState) -> str:
        """Save or upsert a trip state."""
        trip_data = {
            "trip_id": trip_state.trip_id,
            "user_id": trip_state.user_id,
            "state_json": trip_state.model_dump(mode="json"),
            "is_active": True,
            "updated_at": datetime.utcnow().isoformat(),
        }
        self.client.table("trip_states").upsert(trip_data).execute()
        return trip_state.trip_id

    def get_trip(self, trip_id: str) -> Optional[TripState]:
        """Retrieve a trip state by ID."""
        result = (
            self.client.table("trip_states")
            .select("state_json")
            .eq("trip_id", trip_id)
            .eq("is_active", True)
            .execute()
        )
        if result.data:
            return TripState(**result.data[0]["state_json"])
        return None

    def get_active_trips(self, user_id: str) -> List[TripState]:
        """Get all active trips for a user."""
        result = (
            self.client.table("trip_states")
            .select("state_json")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .order("updated_at", desc=True)
            .execute()
        )
        return [TripState(**row["state_json"]) for row in result.data]

    # =========================================================================
    # Venue RAG Operations (pgvector)
    # =========================================================================

    def add_venue(self, venue: VenueRAG, embedding: List[float]) -> str:
        """Add a venue with its embedding to pgvector."""
        venue_data = {
            "venue_id": venue.venue_id,
            "name": venue.name,
            "description": venue.description,
            "micro_location": venue.micro_location,
            "lat": venue.lat,
            "lng": venue.lng,
            "vibe_tags": venue.vibe_tags,
            "audience": venue.audience,
            "category": venue.category,
            "opening_hours": venue.opening_hours,
            "is_sponsored": venue.is_sponsored,
            "bid_weight": venue.bid_weight,
            "embedding": embedding,  # pgvector handles the array
        }
        self.client.table("venues_rag").insert(venue_data).execute()
        return venue.venue_id

    def hybrid_venue_search(
        self,
        query: Optional[str] = None,
        user_lat: float = 25.1972,
        user_lng: float = 55.2744,
        radius_km: float = None,
        vibe_filter: Optional[List[str]] = None,
        audience_filter: Optional[List[str]] = None,
        top_k: int = None,
        query_embedding: Optional[List[float]] = None,
    ) -> List[VenueSearchResult]:
        """Perform hybrid search using the database function.

        Interface-compatible with the in-memory backend: accepts a text `query`,
        embeds it, calls the pgvector function, and returns VenueSearchResult
        objects with coordinates (needed by the scheduler).
        """
        from services.embedding_service import embedding_service
        if radius_km is None:
            radius_km = settings.transit_radius_km
        if top_k is None:
            top_k = settings.max_venue_results
        if query_embedding is None:
            if not query:
                raise ValueError("hybrid_venue_search needs `query` or `query_embedding`")
            query_embedding = embedding_service.generate_embedding(query)

        rows = self.client.rpc("hybrid_venue_search", {
            "query_embedding": query_embedding,
            "user_lat": user_lat,
            "user_lng": user_lng,
            "radius_km": radius_km,
            "sponsored_boost": settings.sponsored_boost_multiplier,
            "result_limit": top_k,
        }).execute().data or []

        if vibe_filter:
            rows = [r for r in rows
                    if any(t in (r.get("vibe_tags") or []) for t in vibe_filter)]

        results = []
        for r in rows[:top_k]:
            venue = VenueRAG(
                venue_id=str(r.get("venue_id")),
                name=r.get("name", ""),
                description=r.get("description", ""),
                micro_location=r.get("micro_location", ""),
                lat=r.get("lat", user_lat),
                lng=r.get("lng", user_lng),
                vibe_tags=r.get("vibe_tags") or [],
                opening_hours=r.get("opening_hours", "09:00-23:00"),
            )
            results.append(VenueSearchResult(
                venue=venue,
                similarity_score=float(r.get("similarity_score", 0.0)),
                final_score=float(r.get("final_score", 0.0)),
            ))
        return results

    # =========================================================================
    # Semantic Cache Operations
    # =========================================================================

    def check_cache(
        self, query_embedding: List[float], threshold: float = None
    ) -> Optional[Tuple[str, float]]:
        """Check semantic cache using vector similarity.

        Uses pgvector's cosine distance operator (<=>).
        Returns (cached_response, similarity_score) or None.
        """
        if threshold is None:
            threshold = settings.semantic_cache_threshold

        # Use RPC function for vector similarity search on cache
        result = self.client.rpc(
            "check_semantic_cache",
            {
                "query_embedding": query_embedding,
                "similarity_threshold": threshold,
            }
        ).execute()

        if result.data and len(result.data) > 0:
            hit = result.data[0]
            # Increment hit count
            self.client.table("cached_responses").update({
                "hit_count": hit.get("hit_count", 0) + 1
            }).eq("cache_id", hit["cache_id"]).execute()

            return (hit["cached_response_text"], hit["similarity_score"])

        return None

    def store_cache(
        self,
        query_text: str,
        query_embedding: List[float],
        response_text: str,
        geo_lat: float = 25.1972,
        geo_lng: float = 55.2744,
    ) -> None:
        """Store a query-response pair in the semantic cache."""
        cache_entry = {
            "cache_id": str(uuid.uuid4()),
            "query_text": query_text,
            "query_embedding": query_embedding,
            "cached_response_text": response_text,
            "geo_fence_center": f"({geo_lat},{geo_lng})",
            "hit_count": 0,
            "expires_at": (
                datetime.utcnow() + timedelta(hours=settings.cache_ttl_hours)
            ).isoformat(),
        }
        self.client.table("cached_responses").insert(cache_entry).execute()

    def clear_expired_cache(self) -> int:
        """Remove expired cache entries. Returns count deleted."""
        result = (
            self.client.table("cached_responses")
            .delete()
            .lt("expires_at", datetime.utcnow().isoformat())
            .execute()
        )
        return len(result.data) if result.data else 0

    # =========================================================================
    # Event Logging
    # =========================================================================

    def log_event(
        self,
        user_id: str,
        trip_id: str,
        event_type: str,
        routing_tier: str = "light",
        from_cache: bool = False,
        token_cost: float = 0.0,
        payload: dict = None,
    ) -> None:
        """Log an event for analytics and cost tracking."""
        event = {
            "event_id": str(uuid.uuid4()),
            "user_id": user_id,
            "trip_id": trip_id,
            "event_type": event_type,
            "routing_tier_used": routing_tier,
            "from_cache": from_cache,
            "token_cost_estimate": token_cost,
            "event_payload": json.dumps(payload) if payload else None,
        }
        self.client.table("event_log").insert(event).execute()

    def get_event_stats(self, user_id: Optional[str] = None) -> Dict:
        """Get event statistics, optionally filtered by user."""
        query = self.client.table("event_log").select("*", count="exact")
        if user_id:
            query = query.eq("user_id", user_id)
        result = query.execute()

        events = result.data or []
        return {
            "total_events": len(events),
            "cached_responses": sum(1 for e in events if e.get("from_cache")),
            "heavy_model_calls": sum(
                1 for e in events if e.get("routing_tier_used") == "heavy"
            ),
            "total_token_cost": sum(
                e.get("token_cost_estimate", 0) for e in events
            ),
        }

    # =========================================================================
    # Additional SQL Functions (to be created via migration)
    # =========================================================================


ADDITIONAL_SQL_FUNCTIONS = """
-- Atomic reroute increment (unconditional; kept for compatibility)
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

-- Atomic check-and-increment: increments only if under the cap.
-- Returns the new count, or NULL if the user is already at the limit.
-- Use this in the throttle path to avoid the check-then-increment race.
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

-- Semantic cache similarity search
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
"""


# Singleton (only instantiate when Supabase creds are configured)
def get_supabase_service() -> Optional[SupabaseService]:
    """Get Supabase service if credentials are configured."""
    if settings.supabase_url and settings.supabase_key:
        return SupabaseService()
    return None


supabase_db = get_supabase_service()
