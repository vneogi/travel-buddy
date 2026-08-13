"""Travel Buddy MVP - Database Service

In-memory database service that mimics Supabase/PostgreSQL operations.
All data is stored in Python dicts for MVP testing without external deps.
In production, swap with actual Supabase client calls.
"""

from datetime import datetime, date, timezone
from typing import Dict, List, Optional
import uuid

from config.settings import settings
from models.signal_types import SIGNAL_TYPES
from models.schemas import (
    TripState,
    UserTier,
    TierStatus,
    TripParty,
    TripPartyIn,
    VenueRAG,
    VenueSearchResult,
)
from services.embedding_service import embedding_service


class DatabaseService:
    """In-memory database mimicking Supabase operations."""

    def __init__(self):
        # In-memory stores
        self._users: Dict[str, dict] = {}
        self._trips: Dict[str, dict] = {}
        self._venues: List[dict] = []
        self._event_log: List[dict] = []
        self._signals: Dict[str, dict] = {}  # keyed by signal_id (idempotency)
        self._parties: Dict[str, dict] = {}  # keyed by trip_id (SPEC-03)
        self._trip_nodes: Dict[str, list] = {}  # SPEC-16: trip_id -> node rows
        self._trip_edges: Dict[str, list] = {}  # SPEC-16: trip_id -> edge rows
        self._valid_signal_types = set(SIGNAL_TYPES)  # from models.signal_types (single source of truth)

    # =========================================================================
    # User Tier Operations
    # =========================================================================

    def get_or_create_user(self, user_id: str) -> UserTier:
        """Get user tier info, creating a free-tier user if not exists."""
        if user_id not in self._users:
            self._users[user_id] = {
                "user_id": user_id,
                "tier_status": TierStatus.FREE,
                "daily_reroute_count": 0,
                "max_daily_reroutes": settings.max_daily_reroutes_free,
                "last_reset_date": date.today().isoformat(),
            }

        user_data = self._users[user_id]

        # Reset daily count if new day
        if user_data["last_reset_date"] != date.today().isoformat():
            user_data["daily_reroute_count"] = 0
            user_data["last_reset_date"] = date.today().isoformat()

        # Build model explicitly — last_reset_date is internal bookkeeping,
        # not a UserTier field (Pydantic v2 rejects extras → 500).
        return UserTier(
            user_id=user_data["user_id"],
            tier_status=user_data["tier_status"],
            daily_reroute_count=user_data["daily_reroute_count"],
            max_daily_reroutes=user_data["max_daily_reroutes"],
        )

    def increment_reroute_count(self, user_id: str) -> int:
        """Increment the daily reroute count. Returns new count."""
        user = self.get_or_create_user(user_id)
        self._users[user_id]["daily_reroute_count"] += 1
        return self._users[user_id]["daily_reroute_count"]

    def check_reroute_allowed(self, user_id: str) -> tuple:
        """Check if user can reroute. Returns (allowed, remaining, max)."""
        user = self.get_or_create_user(user_id)
        remaining = user.max_daily_reroutes - user.daily_reroute_count
        return (remaining > 0, max(0, remaining), user.max_daily_reroutes)

    def consume_reroute(self, user_id: str):
        """Atomically reserve one reroute. Returns remaining count, or None if
        already at the daily cap. (Single-process in-memory: inherently atomic.)"""
        self.get_or_create_user(user_id)  # applies daily reset
        data = self._users[user_id]
        if data["daily_reroute_count"] >= data["max_daily_reroutes"]:
            return None
        data["daily_reroute_count"] += 1
        return data["max_daily_reroutes"] - data["daily_reroute_count"]

    def upgrade_user(self, user_id: str) -> UserTier:
        """Upgrade user to pro tier."""
        self.get_or_create_user(user_id)
        self._users[user_id]["tier_status"] = TierStatus.PRO
        self._users[user_id]["max_daily_reroutes"] = settings.max_daily_reroutes_pro
        ud = self._users[user_id]
        return UserTier(
            user_id=ud["user_id"],
            tier_status=ud["tier_status"],
            daily_reroute_count=ud["daily_reroute_count"],
            max_daily_reroutes=ud["max_daily_reroutes"],
        )

    def downgrade_user(self, user_id: str) -> UserTier:
        """Downgrade user to free tier (subscription cancelled)."""
        self.get_or_create_user(user_id)
        self._users[user_id]["tier_status"] = TierStatus.FREE
        self._users[user_id]["max_daily_reroutes"] = settings.max_daily_reroutes_free
        ud = self._users[user_id]
        return UserTier(
            user_id=ud["user_id"],
            tier_status=ud["tier_status"],
            daily_reroute_count=ud["daily_reroute_count"],
            max_daily_reroutes=ud["max_daily_reroutes"],
        )

    # =========================================================================
    # Trip State Operations
    # =========================================================================

    def save_trip(self, trip_state: TripState) -> str:
        """Save or update a trip state. Dual-writes normalised nodes (SPEC-16)."""
        trip_dict = trip_state.model_dump(mode="json")
        self._trips[trip_state.trip_id] = trip_dict
        # SPEC-16 phase 1: dual-write normalised rows
        from services.itinerary_normaliser import decompose_trip
        nodes, edges = decompose_trip(trip_dict)
        self._trip_nodes[trip_state.trip_id] = nodes
        self._trip_edges[trip_state.trip_id] = edges
        return trip_state.trip_id

    def get_trip(self, trip_id: str) -> Optional[TripState]:
        """Retrieve a trip state by ID."""
        if trip_id in self._trips:
            return TripState(**self._trips[trip_id])
        return None

    def get_active_trips(self, user_id: str) -> List[TripState]:
        """Get all active trips for a user."""
        return [
            TripState(**t)
            for t in self._trips.values()
            if t["user_id"] == user_id
        ]


    # =========================================================================
    # Itinerary Normalisation (SPEC-16)
    # =========================================================================

    def save_trip_nodes(self, trip_id: str, nodes: list) -> int:
        """Save normalised trip_node rows. Idempotent: replaces existing."""
        self._trip_nodes[trip_id] = list(nodes)
        return len(nodes)

    def get_trip_nodes(self, trip_id: str) -> list:
        """Get normalised trip_node rows for a trip, ordered by (day_index, seq)."""
        rows = self._trip_nodes.get(trip_id, [])
        return sorted(rows, key=lambda r: (r.get("day_index", 0), r.get("seq", 0)))

    def save_trip_edges(self, trip_id: str, edges: list) -> int:
        """Save normalised trip_edge rows. Idempotent: replaces existing."""
        self._trip_edges[trip_id] = list(edges)
        return len(edges)

    def get_trip_edges(self, trip_id: str) -> list:
        """Get normalised trip_edge rows for a trip."""
        return list(self._trip_edges.get(trip_id, []))

        # =========================================================================
    # Trip Party (SPEC-03 — party_context stamping)
    # =========================================================================

    def save_trip_party(self, trip_id: str, party: TripPartyIn) -> TripParty:
        """Save a trip party. Defaults to solo if None passed."""
        stored = TripParty(
            trip_id=trip_id,
            party_type=party.party_type,
            size=party.size,
            members=party.members,
            notes=party.notes,
        )
        self._parties[trip_id] = stored.model_dump(mode="json")
        return stored

    def get_trip_party(self, trip_id: str) -> Optional[TripParty]:
        """Get the party for a trip. Returns None if not found."""
        if trip_id in self._parties:
            return TripParty(**self._parties[trip_id])
        return None

    # =========================================================================
    # Venue RAG Operations
    # =========================================================================

    def add_venue(self, venue: VenueRAG) -> str:
        """Add a venue to the RAG store."""
        venue_dict = venue.model_dump()
        # Generate embedding if not provided
        if not venue_dict.get("embedding"):
            text = f"{venue.name} {venue.description} {' '.join(venue.vibe_tags)}"
            venue_dict["embedding"] = embedding_service.generate_embedding(text)
        self._venues.append(venue_dict)
        return venue.venue_id

    def hybrid_venue_search(
        self,
        query: str,
        user_lat: float = 25.1972,
        user_lng: float = 55.2744,
        radius_km: float = None,
        vibe_filter: Optional[List[str]] = None,
        audience_filter: Optional[List[str]] = None,
        top_k: int = None,
        geo_region: Optional[str] = None,
    ) -> List[VenueSearchResult]:
        """Perform hybrid search: vector similarity + hard filters + sponsored boost.

        Implements BRD Section 3.3:
        Step 1: Dense vector search
        Step 2: Hard filtering & monetization boost

        geo_region filters venues to those belonging to the trip's city.
        When None, all venues are searched (backward compat).
        """
        if radius_km is None:
            radius_km = settings.transit_radius_km
        if top_k is None:
            top_k = settings.max_venue_results

        query_embedding = embedding_service.generate_embedding(query)
        results = []

        for venue in self._venues:
            # Step 0: Geo-region filter (multi-city support)
            if geo_region and venue.get("geo_region", "dubai_uae") != geo_region:
                continue

            # Step 2a: Distance filter
            from services.maps_service import maps_service
            distance = maps_service.calculate_distance_km(
                user_lat, user_lng, venue["lat"], venue["lng"]
            )
            if distance > radius_km:
                continue

            # Optional vibe tag filter
            if vibe_filter:
                if not any(tag in venue.get("vibe_tags", []) for tag in vibe_filter):
                    continue

            # Optional audience filter
            if audience_filter:
                if not any(a in venue.get("audience", []) for a in audience_filter):
                    continue

            # Step 1: Cosine similarity
            similarity = embedding_service.cosine_similarity(
                query_embedding, venue["embedding"]
            )

            # Step 2b: Sponsored boost (BRD formula)
            sponsored_boost = 0.0
            if venue.get("is_sponsored", False):
                sponsored_boost = (
                    venue.get("bid_weight", 0.0)
                    * settings.sponsored_boost_multiplier
                )

            final_score = similarity + sponsored_boost

            venue_obj = VenueRAG(**{k: v for k, v in venue.items() if k != "embedding"})
            results.append(
                VenueSearchResult(
                    venue=venue_obj,
                    similarity_score=round(similarity, 4),
                    final_score=round(final_score, 4),
                    is_open_now=True,  # Will be validated by maps_service
                )
            )

        # Sort by final score descending
        results.sort(key=lambda x: x.final_score, reverse=True)
        return results[:top_k]

    def resolve_venue_by_name(self, place_ref: str) -> Optional[str]:
        """Resolve a venue name to venue_id. Case-insensitive exact match."""
        place_lower = place_ref.lower().strip()
        for venue in self._venues:
            if venue.get("name", "").lower().strip() == place_lower:
                return venue.get("venue_id")
        return None

    def get_venue_count(self) -> int:
        """Get total number of venues in store."""
        return len(self._venues)

    # =========================================================================
    # Event Log
    # =========================================================================

    def log_event(
        self,
        user_id: str,
        trip_id: str,
        event_type: str,
        routing_tier: str = "light",
        from_cache: bool = False,
        payload: dict = None,
    ) -> None:
        """Log an event for analytics."""
        self._event_log.append({
            "event_id": str(uuid.uuid4()),
            "user_id": user_id,
            "trip_id": trip_id,
            "event_type": event_type,
            "routing_tier_used": routing_tier,
            "from_cache": from_cache,
            "payload": payload or {},
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        })

    def get_event_stats(self) -> dict:
        """Get event log statistics."""
        total = len(self._event_log)
        cached = sum(1 for e in self._event_log if e["from_cache"])
        heavy = sum(1 for e in self._event_log if e["routing_tier_used"] == "heavy")
        return {
            "total_events": total,
            "cached_responses": cached,
            "heavy_model_calls": heavy,
            "light_model_calls": total - cached - heavy,
        }


    # =========================================================================
    # Signal Capture (SPEC-01 Part B — data flywheel)
    # =========================================================================

    def get_valid_signal_types(self) -> set:
        """Return the set of known signal type keys."""
        return self._valid_signal_types

    def record_signal(
        self,
        user_id: str,
        signal_id: str,
        signal_type: str,
        place_ref: str,
        value_text: Optional[str] = None,
        value_numeric: Optional[float] = None,
        value_json: Optional[dict] = None,
        captured_at: datetime = None,
        trip_id: Optional[str] = None,
    ) -> bool:
        """Record a signal. Returns True if new, False if duplicate (idempotent).

        signal_id is the client-generated UUID — the idempotency key.
        Re-recording the same signal_id is a no-op (returns False).
        """
        if signal_id in self._signals:
            return False  # duplicate — idempotent no-op

        self._signals[signal_id] = {
            "signal_id": signal_id,
            "place_ref": place_ref,
            "source": "first_party",
            "signal_type": signal_type,
            "user_id": user_id,
            "trip_id": trip_id,
            "value_text": value_text,
            "value_numeric": value_numeric,
            "value_json": value_json,
            "captured_at": (captured_at or datetime.now(tz=timezone.utc)).isoformat(),
            "ingested_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        return True

    def get_signals_count(self) -> int:
        """Get total signals stored (for testing)."""
        return len(self._signals)

    def get_signal(self, signal_id: str) -> Optional[dict]:
        """Get a signal by ID (for testing)."""
        return self._signals.get(signal_id)


# Singleton instance
db_service = DatabaseService()
