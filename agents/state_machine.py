"""Travel Buddy MVP - LangGraph State Machine

The core orchestration engine. Implements the continuous self-correcting
"state loop" that maintains the active itinerary, processes interruptions,
and intelligently replaces activities.

Graph Flow:
  classify_intent -> [check_cache] -> route_model -> [venue_search] -> update_state -> respond

Includes Lever 3 (Circuit Breaker): max_loop_depth = 3
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from config.settings import settings
from models.schemas import (
    GraphState,
    TripState,
    TripNode,
    NodeStatus,
    RoutingTier,
    EventType,
    VenueSearchResult,
)
from services.database_service import db_service
from services.cache_service import cache_service
from services.maps_service import maps_service
from agents.router_agent import router_agent
from services.llm_service import llm_service


class TripStateMachine:
    """LangGraph-style state machine for trip management.

    In production, this would use langgraph.graph.StateGraph.
    For MVP, implements the same logic with explicit state transitions.
    """

    def __init__(self):
        self.max_loop_depth = settings.max_loop_depth

    async def process_event(
        self,
        trip_state: TripState,
        event_type: str,
        message: str,
        target_node_id: Optional[str] = None,
        preferences: Optional[dict] = None,
    ) -> Dict:
        """Process a user event through the state machine."""
        state = {
            "trip_state": trip_state,
            "event_type": event_type,
            "message": message,
            "target_node_id": target_node_id,
            "preferences": preferences or {},
            "loop_depth": 0,
            "routing_tier": RoutingTier.LIGHT,
            "from_cache": False,
            "venues_found": [],
            "response": "",
        }

        state = self._node_classify_intent(state)
        state = self._node_check_cache(state)

        if not state["from_cache"]:
            state = self._node_venue_search(state)
            state = await self._node_generate_response(state)
            state = self._node_update_state(state)
            # Only cache LIGHT (informational) responses. A structural/heavy
            # response describes a one-off mutation and must never be replayed
            # to a later, semantically-similar query.
            if state["routing_tier"] == RoutingTier.LIGHT:
                cache_service.store_response(state["message"], state["response"])

        return {
            "updated_trip_state": state["trip_state"],
            "response": state["response"],
            "routing_tier_used": state["routing_tier"].value,
            "from_cache": state["from_cache"],
            "venues_found": state["venues_found"],
        }

    # =========================================================================
    # Graph Nodes
    # =========================================================================

    def _node_classify_intent(self, state: Dict) -> Dict:
        """Node 1: Classify intent and set routing tier."""
        tier, confidence = router_agent.classify_intent(
            state["message"], state["event_type"]
        )
        state["routing_tier"] = tier
        state["confidence"] = confidence
        return state

    def _node_check_cache(self, state: Dict) -> Dict:
        """Node 2: Check semantic cache (Lever 2).

        Only check cache for light requests. Heavy (structural) requests
        always need fresh processing since they modify state.
        """
        if state["routing_tier"] == RoutingTier.LIGHT:
            cache_result = cache_service.check_cache(state["message"])
            if cache_result:
                response_text, similarity = cache_result
                state["response"] = response_text
                state["from_cache"] = True

        return state

    def _node_venue_search(self, state: Dict) -> Dict:
        """Node 3: Search for replacement venues (for structural changes)."""
        if state["routing_tier"] != RoutingTier.HEAVY:
            return state

        # Determine search parameters from context
        trip_state: TripState = state["trip_state"]
        user_lat = trip_state.current_context.location_lat
        user_lng = trip_state.current_context.location_lng

        # Build search query from message and preferences
        search_query = state["message"]
        if state["preferences"].get("mood"):
            search_query += f" {state['preferences']['mood']}"
        if state["preferences"].get("vibe"):
            search_query += f" {state['preferences']['vibe']}"

        # Perform hybrid search
        venues = db_service.hybrid_venue_search(
            query=search_query,
            user_lat=user_lat,
            user_lng=user_lng,
            vibe_filter=state["preferences"].get("vibe_tags"),
            audience_filter=state["preferences"].get("audience"),
        )

        # Validate with maps service (Step 3 from BRD)
        if venues:
            venue_dicts = [
                {
                    "name": v.venue.name,
                    "lat": v.venue.lat,
                    "lng": v.venue.lng,
                    "opening_hours": v.venue.opening_hours,
                }
                for v in venues
            ]
            validated = maps_service.validate_venues(
                venue_dicts, user_lat, user_lng
            )
            # Keep only validated venues
            validated_names = {v["name"] for v in validated}
            venues = [v for v in venues if v.venue.name in validated_names]

        state["venues_found"] = venues[:3]  # Top 3 per BRD
        return state

    async def _node_generate_response(self, state: Dict) -> Dict:
        """Node 4: Generate the user-facing response.

        Uses the real LLM gateway when a provider key is configured; otherwise
        falls back to deterministic canned responses (key-free dev mode).
        Includes Lever 3 (Circuit Breaker): tracks loop depth.
        """
        state["loop_depth"] += 1
        if state["loop_depth"] > self.max_loop_depth:
            state["response"] = self._fallback_response(state)
            return state

        if settings.litellm_api_key or settings.gemini_api_key:
            try:
                if state["routing_tier"] == RoutingTier.HEAVY:
                    venues = [
                        {
                            "name": v.venue.name,
                            "micro_location": v.venue.micro_location,
                            "vibe_tags": v.venue.vibe_tags,
                            "lat": v.venue.lat,
                            "lng": v.venue.lng,
                        }
                        for v in state["venues_found"]
                    ]
                    state["response"] = await llm_service.generate_itinerary_response(
                        user_message=state["message"],
                        trip_state=state["trip_state"].model_dump(mode="json"),
                        venues_found=venues,
                        routing_tier="heavy",
                    )
                else:
                    state["response"] = await llm_service.generate_info_response(
                        state["message"]
                    )
                return state
            except Exception as exc:
                # Any provider/LLM failure -> deterministic fallback, never 500.
                print(f"LLM generation failed, using canned fallback: {exc}")

        context = {
            "venues_found": state["venues_found"],
            "target_node_id": state.get("target_node_id", ""),
            "trip_state": state["trip_state"].model_dump(mode="json"),
        }
        state["response"] = router_agent.generate_response(
            state["message"], state["routing_tier"], context
        )
        return state

    def _node_update_state(self, state: Dict) -> Dict:
        """Node 5: Update the trip state based on the event."""
        trip_state: TripState = state["trip_state"]
        event_type = state["event_type"]
        target_node_id = state.get("target_node_id")
        venues_found: List[VenueSearchResult] = state["venues_found"]

        if event_type == EventType.CANCEL_ACTIVITY.value and target_node_id:
            # Mark the target node as skipped
            for node in trip_state.nodes:
                if node.node_id == target_node_id and not node.is_locked:
                    node.status = NodeStatus.SKIPPED
                    break

        elif event_type == EventType.SWAP_ACTIVITY.value and target_node_id:
            # Replace target node with top venue result
            if venues_found:
                top_venue = venues_found[0].venue
                for i, node in enumerate(trip_state.nodes):
                    if node.node_id == target_node_id and not node.is_locked:
                        # Preserve the time slot, replace the venue
                        trip_state.nodes[i] = TripNode(
                            node_id=node.node_id,
                            venue_name=top_venue.name,
                            venue_id=top_venue.venue_id,
                            scheduled_start=node.scheduled_start,
                            duration_minutes=node.duration_minutes,
                            is_locked=False,
                            status=NodeStatus.PENDING,
                            micro_location=top_venue.micro_location,
                            vibe_tags=top_venue.vibe_tags,
                            lat=top_venue.lat,
                            lng=top_venue.lng,
                        )
                        break

        elif event_type == EventType.ADD_ACTIVITY.value:
            # Add a new node from top venue result
            if venues_found:
                top_venue = venues_found[0].venue
                # Find the next available time slot
                last_node = trip_state.nodes[-1] if trip_state.nodes else None
                if last_node:
                    next_start = last_node.scheduled_start + timedelta(
                        minutes=last_node.duration_minutes + 30  # 30 min buffer
                    )
                else:
                    next_start = datetime.now().replace(
                        hour=10, minute=0, second=0
                    )

                new_node = TripNode(
                    venue_name=top_venue.name,
                    venue_id=top_venue.venue_id,
                    scheduled_start=next_start,
                    duration_minutes=90,
                    micro_location=top_venue.micro_location,
                    vibe_tags=top_venue.vibe_tags,
                    lat=top_venue.lat,
                    lng=top_venue.lng,
                )
                trip_state.nodes.append(new_node)

        elif event_type == EventType.REROUTE.value:
            # Full reroute: replace all non-locked pending nodes
            venue_idx = 0
            for i, node in enumerate(trip_state.nodes):
                if (
                    not node.is_locked
                    and node.status == NodeStatus.PENDING
                    and venue_idx < len(venues_found)
                ):
                    top_venue = venues_found[venue_idx].venue
                    trip_state.nodes[i] = TripNode(
                        node_id=node.node_id,
                        venue_name=top_venue.name,
                        venue_id=top_venue.venue_id,
                        scheduled_start=node.scheduled_start,
                        duration_minutes=node.duration_minutes,
                        is_locked=False,
                        status=NodeStatus.PENDING,
                        micro_location=top_venue.micro_location,
                        vibe_tags=top_venue.vibe_tags,
                        lat=top_venue.lat,
                        lng=top_venue.lng,
                    )
                    venue_idx += 1

        # Update timestamp
        trip_state.updated_at = datetime.utcnow()
        state["trip_state"] = trip_state
        return state

    def _fallback_response(self, state: Dict) -> str:
        """Circuit breaker fallback: deterministic rule-based response."""
        return (
            "I've reached the maximum processing depth for this request. "
            "Here's a simplified suggestion: Based on your current location, "
            "I recommend checking nearby venues on the main strip. "
            "Your locked reservations remain unchanged."
        )


# Singleton instance
state_machine = TripStateMachine()
