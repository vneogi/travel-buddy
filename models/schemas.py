"""Travel Buddy MVP - Pydantic Models & TypedDicts

Defines the TripState schema, request/response models, and
all data structures used across the application.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, TypedDict

from pydantic import BaseModel, Field


# ==============================================================================
# Enums
# ==============================================================================

class TierStatus(str, Enum):
    FREE = "free"
    PRO = "pro"


class NodeStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class RoutingTier(str, Enum):
    LIGHT = "light"
    HEAVY = "heavy"


class EventType(str, Enum):
    """User event types that trigger state changes."""
    CANCEL_ACTIVITY = "cancel_activity"
    SWAP_ACTIVITY = "swap_activity"
    ADD_ACTIVITY = "add_activity"
    CHANGE_MOOD = "change_mood"
    WEATHER_ALERT = "weather_alert"
    TRANSLATE = "translate"
    ASK_INFO = "ask_info"
    REROUTE = "reroute"


# ==============================================================================
# TripState (Core State Object - TypedDict for LangGraph)
# ==============================================================================

class TripNode(BaseModel):
    """A single activity node in the itinerary graph."""
    node_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    venue_name: str
    venue_id: Optional[str] = None
    scheduled_start: datetime
    duration_minutes: int = 90
    is_locked: bool = False
    status: NodeStatus = NodeStatus.PENDING
    micro_location: Optional[str] = None
    vibe_tags: List[str] = []
    lat: Optional[float] = None
    lng: Optional[float] = None
    opening_hours: Optional[str] = None  # "HH:MM-HH:MM"; used for re-validation
    geo_region: Optional[str] = None  # Per-node region; overrides trip's default for multi-city


class CurrentContext(BaseModel):
    """Real-time traveler context."""
    location_lat: float = 25.1972
    location_lng: float = 55.2744
    time_of_day: str = "14:30"
    weather_condition: Optional[str] = None
    mood: Optional[str] = None


class ExecutionControl(BaseModel):
    """Cost-control metadata for the state machine."""
    routing_tier: RoutingTier = RoutingTier.LIGHT
    loop_depth_counter: int = 0
    max_loop_depth: int = 3


class TripState(BaseModel):
    """The live, mutable trip state object."""
    trip_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    geo_region: str = "dubai_uae"  # Per-trip geo-fence; unlocks multi-city
    current_context: CurrentContext = CurrentContext()
    execution_control: ExecutionControl = ExecutionControl()
    nodes: List[TripNode] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


# TypedDict version for LangGraph state
class GraphState(TypedDict):
    """LangGraph-compatible state dict."""
    trip_state: dict  # Serialized TripState
    user_message: str
    event_type: str
    routing_tier: str
    loop_depth: int
    response: str
    venues_found: list
    requires_rewrite: bool


# ==============================================================================
# API Request/Response Models
# ==============================================================================

class TripEventRequest(BaseModel):
    """POST /api/v1/trip/event - Incoming user event."""
    # NOTE: user_id is derived from the auth token server-side; any value sent
    # by the client is ignored. Kept optional only for backward compatibility.
    user_id: Optional[str] = None
    trip_id: str
    event_type: EventType
    message: str
    target_node_id: Optional[str] = None
    preferences: Optional[dict] = None


class TripEventResponse(BaseModel):
    """Response after processing a trip event."""
    trip_id: str
    status: str
    message: str
    updated_nodes: List[TripNode] = []
    routing_tier_used: str = "light"
    from_cache: bool = False
    reroutes_remaining: Optional[int] = None


class CreateTripRequest(BaseModel):
    """POST /api/v1/trip/create - Create a new trip."""
    # NOTE: user_id is derived from the auth token server-side; ignored if sent.
    user_id: Optional[str] = None
    start_date: datetime
    preferences: dict = {}
    initial_mood: Optional[str] = "exploratory"
    party: Optional[TripPartyIn] = None  # SPEC-03: defaults to solo if absent


class UserTier(BaseModel):
    """User tier information."""
    user_id: str
    tier_status: TierStatus = TierStatus.FREE
    daily_reroute_count: int = 0
    max_daily_reroutes: int = 5




# ==============================================================================
# Trip Party (SPEC-03 — party_context stamping)
# ==============================================================================

class PartyMemberIn(BaseModel):
    """A member of the travel party (input model)."""
    role: str = Field(..., description="self|partner|child|teen|parent|friend")
    age_band: str = Field(..., description="infant|toddler|child|teen|adult|senior (NEVER a birth date)")
    needs: List[str] = Field(default_factory=list, description="nap_schedule|stroller|dietary:*|low_stamina")


class TripPartyIn(BaseModel):
    """Trip party composition (input model for create-trip)."""
    party_type: str = Field(
        default="solo",
        description="solo|couple|friends|family_young_kids|family_teens|multigen|daddy_kiddo|accessibility_focused|mixed",
    )
    size: int = Field(default=1, ge=1)
    members: List[PartyMemberIn] = Field(default_factory=list)
    notes: Optional[str] = None


class TripParty(BaseModel):
    """Stored trip party (response model)."""
    party_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trip_id: str
    party_type: str
    size: int = 1
    members: List[PartyMemberIn] = Field(default_factory=list)
    notes: Optional[str] = None

# ==============================================================================
# Venue / RAG Models
# ==============================================================================

class VenueRAG(BaseModel):
    """A venue entry with RAG metadata."""
    venue_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str
    micro_location: str
    lat: float
    lng: float
    vibe_tags: List[str] = []
    audience: List[str] = []
    category: str = "experience"
    is_sponsored: bool = False
    bid_weight: float = 0.0
    opening_hours: str = "09:00-23:00"
    embedding: Optional[List[float]] = None  # 1536-dim vector


class VenueSearchResult(BaseModel):
    """Result from hybrid venue search."""
    venue: VenueRAG
    similarity_score: float
    final_score: float  # After sponsored boost
    is_open_now: bool = True
    transit_minutes: Optional[int] = None
