"""Travel Buddy MVP - Semantic Cache Service

Implements Lever 2 from BRD: Semantic Cache Check.
Before routing to an LLM, checks if a semantically similar query
has been answered recently. Threshold: 0.92 cosine similarity.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from config.settings import settings
from services.embedding_service import embedding_service


class CacheEntry:
    """A single cached query-response pair."""

    def __init__(
        self,
        query_text: str,
        response_text: str,
        embedding: List[float],
        geo_lat: float = 25.1972,
        geo_lng: float = 55.2744,
    ):
        self.query_text = query_text
        self.response_text = response_text
        self.embedding = embedding
        self.geo_lat = geo_lat
        self.geo_lng = geo_lng
        self.created_at = datetime.now(tz=timezone.utc)
        self.hit_count = 0
        self.expires_at = self.created_at + timedelta(hours=settings.cache_ttl_hours)

    @property
    def is_expired(self) -> bool:
        return datetime.now(tz=timezone.utc) > self.expires_at


class SemanticCacheService:
    """In-memory semantic cache for MVP testing.

    In production, this queries the cached_responses table in Supabase
    using pgvector's cosine similarity operator (<=>).
    """

    def __init__(self):
        self._cache: List[CacheEntry] = []
        self.threshold = settings.semantic_cache_threshold
        self.total_hits = 0
        self.total_misses = 0

    def check_cache(
        self, query: str, geo_lat: float = 25.1972, geo_lng: float = 55.2744
    ) -> Optional[Tuple[str, float]]:
        """Check if a semantically similar query exists in cache.

        Returns:
            Tuple of (cached_response, similarity_score) if hit, None if miss.
        """
        query_embedding = embedding_service.generate_embedding(query)

        best_match: Optional[CacheEntry] = None
        best_score: float = 0.0

        for entry in self._cache:
            if entry.is_expired:
                continue

            similarity = embedding_service.cosine_similarity(query_embedding, entry.embedding)

            if similarity > best_score:
                best_score = similarity
                best_match = entry

        if best_match and best_score >= self.threshold:
            best_match.hit_count += 1
            self.total_hits += 1
            return (best_match.response_text, best_score)

        self.total_misses += 1
        return None

    def store_response(
        self,
        query: str,
        response: str,
        geo_lat: float = 25.1972,
        geo_lng: float = 55.2744,
    ) -> None:
        """Store a query-response pair in the cache."""
        embedding = embedding_service.generate_embedding(query)
        entry = CacheEntry(
            query_text=query,
            response_text=response,
            embedding=embedding,
            geo_lat=geo_lat,
            geo_lng=geo_lng,
        )
        self._cache.append(entry)

    def clear_expired(self) -> int:
        """Remove expired entries. Returns count of removed entries."""
        before_count = len(self._cache)
        self._cache = [e for e in self._cache if not e.is_expired]
        return before_count - len(self._cache)

    def get_stats(self) -> dict:
        """Return cache performance stats."""
        return {
            "total_entries": len(self._cache),
            "total_hits": self.total_hits,
            "total_misses": self.total_misses,
            "hit_rate": (
                self.total_hits / (self.total_hits + self.total_misses)
                if (self.total_hits + self.total_misses) > 0
                else 0.0
            ),
            "threshold": self.threshold,
        }

    def clear_all(self) -> None:
        """Clear all cache entries."""
        self._cache = []
        self.total_hits = 0
        self.total_misses = 0


# Singleton instance
cache_service = SemanticCacheService()
