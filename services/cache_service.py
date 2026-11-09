"""Travel Buddy MVP - Semantic Cache Service

Implements Lever 2 from BRD: Semantic Cache Check.
Before routing to an LLM, checks if a semantically similar query
has been answered recently. Threshold: 0.92 cosine similarity.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Tuple

from config.settings import settings
from monitoring.redact import MIN_RESTRICTED_NEEDLE_LEN, redact_secrets
from services.embedding_service import embedding_service


def hmac_query(query: str, key: bytes) -> str:
    """SPEC-43 Gap 8: HMAC-SHA256 (hex) of the UTF-8 query bytes.

    The cache stores this instead of the traveller's question. Matching
    still uses the request-time embedding, never this digest.
    """
    return hmac.new(key, (query or "").encode("utf-8"), hashlib.sha256).hexdigest()


def response_is_restricted(response: str, extra_needles: Iterable[object] = ()) -> bool:
    """SPEC-43 Gap 8: True if *response* must not be cached.

    Restricted when Gap 10 token detection would change it (keys, Bearer
    tokens, sk-/AIza-style values, configured secrets), or when any extra
    needle (e.g. a trip node's confirmation_code / booking_notes) of at
    least MIN_RESTRICTED_NEEDLE_LEN chars appears in it.
    """
    text = response or ""
    if redact_secrets(text) != text:
        return True
    for needle in extra_needles or ():
        if needle is None:
            continue
        value = str(needle).strip()
        if len(value) >= MIN_RESTRICTED_NEEDLE_LEN and value in text:
            return True
    return False


def normalize_identity_scope(identity_scope: object) -> Optional[str]:
    """SPEC-43 Gap 8: usable cache identity, or None.

    Empty, whitespace, and the literal 'anonymous' are not scopes: there is
    no shared bucket for unidentified callers.
    """
    if identity_scope is None:
        return None
    scope = str(identity_scope).strip()
    if not scope or scope == "anonymous":
        return None
    return scope


class CacheEntry:
    """A single cached query-response pair, owned by one identity scope.

    SPEC-43 Gap 8: holds query_hmac, never the raw question text.
    """

    def __init__(
        self,
        query_hmac: str,
        response_text: str,
        embedding: List[float],
        identity_scope: str,
        geo_lat: float = 25.1972,
        geo_lng: float = 55.2744,
        geo_region: str = "",
        venue_name: str = "",
        trip_id: str = "",
        local_date: str = "",
        source_version: str = "",
    ):
        self.query_hmac = query_hmac
        self.response_text = response_text
        self.embedding = embedding
        self.identity_scope = identity_scope
        self.geo_lat = geo_lat
        self.geo_lng = geo_lng
        self.geo_region = geo_region
        self.venue_name = venue_name
        # SPEC-43 Gap 8: exact-match context (never hashed or embedded).
        self.trip_id = trip_id
        self.local_date = local_date
        self.source_version = source_version
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

    def __init__(self, hmac_key: Optional[bytes] = None):
        # SPEC-43 Gap 8: per-process key when none is injected (the in-memory
        # cache already dies on restart). Never logged.
        self._hmac_key: bytes = hmac_key if hmac_key is not None else secrets.token_bytes(32)
        self._cache: List[CacheEntry] = []
        self.threshold = settings.semantic_cache_threshold
        self.total_hits = 0
        self.total_misses = 0

    def check_cache(
        self,
        query: str,
        *,
        identity_scope: str,
        geo_lat: float = 25.1972,
        geo_lng: float = 55.2744,
        geo_region: str = "",
        venue_name: str = "",
        trip_id: str = "",
        local_date: str = "",
        source_version: str = "",
        restricted_needles: Iterable[object] = (),
    ) -> Optional[Tuple[str, float]]:
        """Check if a semantically similar query exists in cache.

        Cache entries are scoped by (identity_scope, geo_region, venue_name)
        so the same question text from another traveller or in another
        destination never collides (SPEC-43 Gap 8).

        Returns:
            Tuple of (cached_response, similarity_score) if hit, None if miss.
        """
        # SPEC-43 Gap 8: delete expired rows from memory (not just skip them),
        # before the identity early-return so any request purges.
        self.clear_expired()
        scope = normalize_identity_scope(identity_scope)
        if scope is None:
            self.total_misses += 1
            return None

        # SPEC-43 Gap 3: booking needles are redacted from the provider
        # payload only; the HMAC and matching still use the original query.
        query_embedding = embedding_service.generate_embedding(
            query, restricted_needles=restricted_needles
        )

        best_match: Optional[CacheEntry] = None
        best_score: float = 0.0

        for entry in self._cache:
            if entry.is_expired:
                continue
            # SPEC-43 Gap 8: same owner, exact match after strip.
            if entry.identity_scope != scope:
                continue
            # Scope: same region AND same venue context.
            if entry.geo_region != geo_region or entry.venue_name != venue_name:
                continue
            # SPEC-43 Gap 8: same trip, destination-local day, and source
            # version (itinerary version + catalog version). Empty hits empty.
            if (
                entry.trip_id != trip_id
                or entry.local_date != local_date
                or entry.source_version != source_version
            ):
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
        *,
        identity_scope: str,
        geo_lat: float = 25.1972,
        geo_lng: float = 55.2744,
        geo_region: str = "",
        venue_name: str = "",
        restricted_needles: Iterable[object] = (),
        trip_id: str = "",
        local_date: str = "",
        source_version: str = "",
    ) -> None:
        """Store a query-response pair in the cache.

        The entry is keyed by (identity_scope, geo_region, venue_name,
        semantic_embedding). An unusable identity stores nothing. A
        restricted response (SPEC-43 Gap 8) stores nothing: no
        redact-and-store, and neither the response nor the needles are
        logged.
        """
        # SPEC-43 Gap 8: delete expired rows from memory (not just skip them),
        # before the identity early-return so any request purges.
        self.clear_expired()
        scope = normalize_identity_scope(identity_scope)
        if scope is None:
            return
        if response_is_restricted(response, restricted_needles):
            return
        embedding = embedding_service.generate_embedding(
            query, restricted_needles=restricted_needles
        )
        entry = CacheEntry(
            query_hmac=hmac_query(query, self._hmac_key),
            response_text=response,
            embedding=embedding,
            identity_scope=scope,
            geo_lat=geo_lat,
            geo_lng=geo_lng,
            geo_region=geo_region,
            venue_name=venue_name,
            trip_id=trip_id,
            local_date=local_date,
            source_version=source_version,
        )
        self._cache.append(entry)

    def clear_expired(self) -> int:
        """Remove expired entries. Returns count of removed entries."""
        before_count = len(self._cache)
        self._cache = [e for e in self._cache if not e.is_expired]
        return before_count - len(self._cache)

    def clear_identity(self, identity_scope: str) -> int:
        """SPEC-43 Gap 4: drop every entry owned by one identity scope.

        An unusable scope (blank, "anonymous") removes nothing; this never
        falls back to clear_all. Hit/miss totals are process totals and are
        kept. The scope is not logged.
        """
        scope = normalize_identity_scope(identity_scope)
        if scope is None:
            return 0
        before_count = len(self._cache)
        self._cache = [e for e in self._cache if e.identity_scope != scope]
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
