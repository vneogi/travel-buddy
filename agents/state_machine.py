"""Travel Buddy MVP - State Machine

The core orchestration engine: maintains the active itinerary, processes
interruptions, and intelligently replaces activities.

Flow (non-cached):
  classify_intent -> check_cache -> venue_search -> apply_structural (with
  circuit breaker) -> generate_response

Lever 3 (Circuit Breaker): for structural edits, each candidate venue is
applied then re-scheduled+validated; if it makes a locked reservation
unreachable, the next candidate is tried, up to max_loop_depth attempts, after
which we fall back deterministically and leave the itinerary unchanged.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from config.settings import settings
from models.schemas import (
    TripState,
    TripNode,
    NodeStatus,
    RoutingTier,
    EventType,
    VenueSearchResult,
)
from services.db_provider import db_service
from services.cache_service import cache_service
from services.maps_service import maps_service
from services.scheduler import reschedule_and_validate
from agents.router_agent import router_agent
from services.llm_service import llm_service


STRUCTURAL_EDIT_EVENTS = {
    EventType.CANCEL_ACTIVITY.value,
    EventType.SWAP_ACTIVITY.value,
    EventType.ADD_ACTIVITY.value,
    EventType.REROUTE.value,
}
VENUE_REQUIRED_EVENTS = {
    EventType.SWAP_ACTIVITY.value,
    EventType.ADD_ACTIVITY.value,
    EventType.REROUTE.value,
}


class TripStateMachine:
    """State machine for trip management."""

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
            "schedule_warnings": [],
            "breaker_tripped": False,
            "no_candidates": False,
        }

        state = self._node_classify_intent(state)
        state = self._node_check_cache(state)

        if not state["from_cache"]:
            state = self._node_venue_search(state)
            state = self._node_apply_structural(state)
            state = await self._node_generate_response(state)
            # Only cache LIGHT (informational) responses \u2014 never mutations.
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
        tier, confidence = router_agent.classify_intent(
            state["message"], state["event_type"]
        )
        state["routing_tier"] = tier
        state["confidence"] = confidence
        return state

    def _node_check_cache(self, state: Dict) -> Dict:
        """Light requests only \u2014 structural edits always need fresh processing."""
        if state["routing_tier"] == RoutingTier.LIGHT:
            cache_result = cache_service.check_cache(state["message"])
            if cache_result:
                response_text, _ = cache_result
                state["response"] = response_text
                state["from_cache"] = True
        return state

    def _node_venue_search(self, state: Dict) -> Dict:
        if state["routing_tier"] != RoutingTier.HEAVY:
            return state

        trip_state: TripState = state["trip_state"]
        user_lat = trip_state.current_context.location_lat
        user_lng = trip_state.current_context.location_lng

        search_query = state["message"]
        if state["preferences"].get("mood"):
            search_query += f" {state['preferences']['mood']}"
        if state["preferences"].get("vibe"):
            search_query += f" {state['preferences']['vibe']}"

        venues = db_service.hybrid_venue_search(
            query=search_query,
            user_lat=user_lat,
            user_lng=user_lng,
            vibe_filter=state["preferences"].get("vibe_tags"),
            audience_filter=state["preferences"].get("audience"),
        )

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
            validated = maps_service.validate_venues(venue_dicts, user_lat, user_lng)
            validated_names = {v["name"] for v in validated}
            venues = [v for v in venues if v.venue.name in validated_names]

        # Keep several candidates so the circuit breaker has alternatives to try.
        state["venues_found"] = venues[:5]
        return state

    def _node_apply_structural(self, state: Dict) -> Dict:
        """Apply a structural edit with reschedule + circuit breaker.

        Non-structural HEAVY events (change_mood / weather_alert) and LIGHT
        events don\'t mutate the itinerary here.
        """
        event_type = state["event_type"]
        if event_type not in STRUCTURAL_EDIT_EVENTS:
            return state

        trip_state: TripState = state["trip_state"]
        venues: List[VenueSearchResult] = state["venues_found"]
        target = state.get("target_node_id")

        if event_type in VENUE_REQUIRED_EVENTS and not venues:
            state["no_candidates"] = True
            state["schedule_warnings"] = ["No suitable venues found for this change."]
            return state

        accepted = None
        attempt = 0
        while attempt < self.max_loop_depth:
            candidate_nodes = self._build_candidate_nodes(
                trip_state, event_type, target, venues, attempt
            )
            if candidate_nodes is None:
                break  # no further candidates to try
            result = reschedule_and_validate(candidate_nodes)
            state["loop_depth"] = attempt + 1
            if not result.has_hard_conflict:
                accepted = result
                break
            attempt += 1

        if accepted is not None:
            trip_state.nodes = accepted.nodes
            state["schedule_warnings"] = accepted.warnings
        else:
            # Circuit breaker: no feasible candidate within max_loop_depth.
            state["breaker_tripped"] = True
            state["schedule_warnings"] = [
                "Couldn\'t find a change that keeps your locked reservations reachable in time."
            ]

        trip_state.updated_at = datetime.now(tz=timezone.utc)
        state["trip_state"] = trip_state
        return state

    def _build_candidate_nodes(
        self,
        trip_state: TripState,
        event_type: str,
        target_node_id: Optional[str],
        venues: List[VenueSearchResult],
        attempt: int,
    ) -> Optional[List[TripNode]]:
        """Return a fresh node list with the edit applied for this attempt, or
        None when there is no further candidate to try."""
        nodes = [n.model_copy(deep=True) for n in trip_state.nodes]

        if event_type == EventType.CANCEL_ACTIVITY.value:
            if attempt > 0:
                return None
            for node in nodes:
                if node.node_id == target_node_id and not node.is_locked:
                    node.status = NodeStatus.SKIPPED
                    break
            return nodes

        if event_type == EventType.SWAP_ACTIVITY.value:
            if attempt >= len(venues):
                return None
            venue = venues[attempt].venue
            for i, node in enumerate(nodes):
                if node.node_id == target_node_id and not node.is_locked:
                    nodes[i] = self._node_from_venue(
                        venue, node.scheduled_start, node.duration_minutes, node.node_id
                    )
                    break
            return nodes

        if event_type == EventType.ADD_ACTIVITY.value:
            if attempt >= len(venues):
                return None
            venue = venues[attempt].venue
            insert_at = len(nodes)
            if target_node_id:
                for i, node in enumerate(nodes):
                    if node.node_id == target_node_id:
                        insert_at = i + 1
                        break
            anchor = (
                nodes[insert_at - 1].scheduled_start
                if insert_at > 0 and nodes
                else datetime.now(tz=timezone.utc)
            )
            nodes.insert(
                insert_at,
                self._node_from_venue(venue, anchor, 90, None),
            )
            return nodes

        if event_type == EventType.REROUTE.value:
            window = venues[attempt:]
            if not window:
                return None
            vi = 0
            for i, node in enumerate(nodes):
                if (
                    not node.is_locked
                    and node.status == NodeStatus.PENDING
                    and vi < len(window)
                ):
                    nodes[i] = self._node_from_venue(
                        window[vi].venue,
                        node.scheduled_start,
                        node.duration_minutes,
                        node.node_id,
                    )
                    vi += 1
            return nodes

        return None

    @staticmethod
    def _node_from_venue(venue, scheduled_start, duration_minutes, node_id) -> TripNode:
        kwargs = dict(
            venue_name=venue.name,
            venue_id=venue.venue_id,
            scheduled_start=scheduled_start or datetime.now(tz=timezone.utc),
            duration_minutes=duration_minutes,
            is_locked=False,
            status=NodeStatus.PENDING,
            micro_location=venue.micro_location,
            vibe_tags=venue.vibe_tags,
            lat=venue.lat,
            lng=venue.lng,
            opening_hours=getattr(venue, "opening_hours", None),
        )
        if node_id is not None:
            kwargs["node_id"] = node_id
        return TripNode(**kwargs)

    async def _node_generate_response(self, state: Dict) -> Dict:
        """Node: produce the user-facing text (LLM when configured, else canned)."""
        if state.get("breaker_tripped"):
            state["response"] = self._fallback_response(state)
            return state

        if state.get("no_candidates"):
            state["response"] = (
                "I couldn\'t find a suitable alternative nearby that fits your "
                "preferences and transit range, so your itinerary is unchanged."
            )
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
                    base = await llm_service.generate_itinerary_response(
                        user_message=state["message"],
                        trip_state=state["trip_state"].model_dump(mode="json"),
                        venues_found=venues,
                        routing_tier="heavy",
                    )
                else:
                    base = await llm_service.generate_info_response(state["message"])
                state["response"] = base
            except Exception as exc:
                print(f"LLM generation failed, using canned fallback: {exc}")
                state["response"] = router_agent.generate_response(
                    state["message"],
                    state["routing_tier"],
                    {"venues_found": state["venues_found"]},
                )
        else:
            state["response"] = router_agent.generate_response(
                state["message"],
                state["routing_tier"],
                {
                    "venues_found": state["venues_found"],
                    "target_node_id": state.get("target_node_id", ""),
                },
            )

        warnings = state.get("schedule_warnings") or []
        if warnings:
            state["response"] += "\n\nHeads up: " + " ".join(warnings)
        return state

    def _fallback_response(self, state: Dict) -> str:
        return (
            "I couldn\'t safely rework the schedule around your locked "
            "reservations for this request, so nothing was changed. Try a "
            "different activity, a nearer venue, or freeing up a locked slot. "
            "Your locked reservations remain intact."
        )


# Singleton instance
state_machine = TripStateMachine()
