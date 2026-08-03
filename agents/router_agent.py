"""Travel Buddy MVP - Router Agent

Implements Lever 4 (Asymmetric Route Switcher) from the BRD.
Classifies user intent to determine whether to route to the heavy
(frontier) model or the light (cheap/free) model.

Also handles the mock LLM response generation for MVP testing.
"""

from typing import Dict, Tuple

from config.settings import settings
from models.schemas import EventType, RoutingTier


# Intent keywords for classification
STRUCTURAL_INTENTS = {
    "reschedule", "reroute", "replace", "swap", "cancel", "change plan",
    "add activity", "move", "shift", "reorganize", "different place",
    "something else", "too tired", "weather", "raining", "too hot",
}

LIGHT_INTENTS = {
    "translate", "what is", "dress code", "how to get", "directions",
    "price", "cost", "menu", "phone number", "hours", "open",
    "tell me about", "information", "history", "culture", "tip",
    "recommend food", "wifi", "parking", "nearby",
}


class RouterAgent:
    """Classifies intent and routes to appropriate model tier."""

    def classify_intent(self, message: str, event_type: str) -> Tuple[RoutingTier, float]:
        """Classify the user's message to determine routing tier.

        Returns:
            Tuple of (RoutingTier, confidence_score)
        """
        message_lower = message.lower()

        # Event-type based classification (highest priority)
        structural_events = {
            EventType.CANCEL_ACTIVITY,
            EventType.SWAP_ACTIVITY,
            EventType.ADD_ACTIVITY,
            EventType.REROUTE,
            EventType.WEATHER_ALERT,
            EventType.CHANGE_MOOD,
        }

        if event_type in [e.value for e in structural_events]:
            return (RoutingTier.HEAVY, 0.95)

        light_events = {EventType.TRANSLATE, EventType.ASK_INFO}
        if event_type in [e.value for e in light_events]:
            return (RoutingTier.LIGHT, 0.95)

        # Keyword-based classification (fallback)
        structural_score = sum(
            1 for keyword in STRUCTURAL_INTENTS
            if keyword in message_lower
        )
        light_score = sum(
            1 for keyword in LIGHT_INTENTS
            if keyword in message_lower
        )

        total = structural_score + light_score
        if total == 0:
            # Default to light for unknown intents (cost-safe)
            return (RoutingTier.LIGHT, 0.5)

        structural_confidence = structural_score / total

        if structural_confidence >= settings.structural_intent_confidence:
            return (RoutingTier.HEAVY, structural_confidence)
        else:
            return (RoutingTier.LIGHT, 1.0 - structural_confidence)

    def generate_response(
        self,
        message: str,
        routing_tier: RoutingTier,
        context: Dict = None,
    ) -> str:
        """Generate a response using the appropriate model.

        For MVP: Returns structured synthetic responses.
        In production: Calls LiteLLM with the appropriate model.
        """
        if routing_tier == RoutingTier.LIGHT:
            return self._light_response(message, context or {})
        else:
            return self._heavy_response(message, context or {})

    def _light_response(self, message: str, context: Dict) -> str:
        """Generate a light-model response (info, translations, etc.)"""
        message_lower = message.lower()

        if "translate" in message_lower:
            return (
                "Translation: In Arabic, common phrases include: "
                "'Shukran' (Thank you), 'Marhaba' (Hello), "
                "'La shukran' (No thank you), 'Kam hatha?' (How much?). "
                "Most Dubai venues have English-speaking staff."
            )
        elif "dress code" in message_lower:
            return (
                "Dubai Dress Code: Smart casual is standard for most venues. "
                "For mosques and government buildings, cover shoulders and knees. "
                "Beach clubs allow swimwear poolside only. Fine dining typically "
                "requires smart attire - no shorts or flip-flops."
            )
        elif "price" in message_lower or "cost" in message_lower:
            return (
                "Pricing Guide: Average meal at a mid-range restaurant: AED 80-150. "
                "Coffee at specialty cafe: AED 25-40. Taxi ride across Dubai: AED 40-80. "
                "Metro single trip: AED 4-8.50. Museum entry: AED 50-85."
            )
        else:
            return (
                f"Based on your query about '{message[:50]}...': "
                "I'd recommend checking with the venue directly for the most "
                "current information. Dubai venues are generally very accommodating "
                "to tourists and most staff speak English fluently."
            )

    def _heavy_response(self, message: str, context: Dict) -> str:
        """Generate a heavy-model response (structural changes).

        In MVP, returns a structured JSON-like response indicating
        the itinerary changes to make.
        """
        venues_found = context.get("venues_found", [])
        target_node = context.get("target_node_id", "")

        if venues_found:
            top_venue = venues_found[0] if venues_found else None
            venue_name = top_venue.venue.name if top_venue else "Alternative Venue"
            return (
                f"Itinerary updated: Replaced node '{target_node}' with "
                f"'{venue_name}'. Remaining schedule has been shifted to "
                f"accommodate the change. All locked reservations preserved."
            )
        else:
            return (
                f"Processing your request: '{message[:80]}'. "
                "Searching for suitable alternatives within your transit radius "
                "that match your current mood and preferences. "
                "The schedule will be adjusted while preserving locked items."
            )

    def get_model_info(self, tier: RoutingTier) -> Dict:
        """Get info about which model would be used for this tier."""
        if tier == RoutingTier.HEAVY:
            return {
                "model": settings.heavy_model,
                "estimated_cost_per_1k_tokens": 0.005,
                "tier": "heavy",
            }
        else:
            return {
                "model": settings.light_model,
                "estimated_cost_per_1k_tokens": 0.0001,
                "tier": "light",
            }


# Singleton instance
router_agent = RouterAgent()
