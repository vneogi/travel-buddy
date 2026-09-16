"""SPEC-25: Grounded trip-scoped Ask service.

Retrieval-first query: classify -> retrieve -> answer (or refuse).
Ask never persists itinerary rows. Mutations stay HITL on the
existing event path.

Guard order: exact cache -> per-identity budget -> circuit breaker -> model.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Closed intent set (SPEC-25 design decision 2)
# ---------------------------------------------------------------------------


class AskIntent(str, Enum):
    """Closed intent set for trip-scoped Ask."""

    PLACE_IDENTITY = "place_identity"
    OPENING_HOURS = "opening_hours"
    DISH_FACT = "dish_fact"
    TRIP_CURRENT_NEXT = "trip_current_next"
    PLAN_CHANGE = "plan_change"
    OUT_OF_SCOPE = "out_of_scope"


# ---------------------------------------------------------------------------
# SPEC-17 trust tier (interim -- five tiers)
# ---------------------------------------------------------------------------


class TrustTier(str, Enum):
    ASSERT = "assert"
    HEDGE = "hedge"
    ASK = "ask"
    DEFER = "defer"
    REFUSE = "refuse"


# ---------------------------------------------------------------------------
# Response envelope
# ---------------------------------------------------------------------------


class AskPath(str, Enum):
    """Named response paths (SPEC-25 remainder)."""

    GROUNDED_DETERMINISTIC = "grounded_deterministic"
    GROUNDED_MODEL_PHRASED = "grounded_model_phrased"
    CACHE_HIT = "cache_hit"
    NO_KEY = "no_key"
    RETRIEVAL_MISS = "retrieval_miss"
    BUDGET_EXHAUSTED = "budget_exhausted"
    BREAKER_OPEN = "breaker_open"
    MODEL_ERROR_FALLBACK = "model_error_fallback"


@dataclass
class AskResponse:
    """Structured Ask response with trust envelope."""

    answer: str
    tier: TrustTier
    path: AskPath
    intent: AskIntent
    source_ids: List[str] = field(default_factory=list)
    source_class: str = ""
    from_cache: bool = False
    fallback_reason: str = ""


# ---------------------------------------------------------------------------
# Telemetry (SPEC-25: record without question text or secrets)
# ---------------------------------------------------------------------------


@dataclass
class AskTelemetry:
    """Cost and observability record for one Ask call."""

    intent: str = ""
    path: str = ""
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    cache_status: str = "miss"
    fallback_reason: str = ""
    geo_region: str = ""
    source_ids: List[str] = field(default_factory=list)
    prompt_version: str = "v1"
    policy_version: str = "v1"
    # SPEC-43: question_text is NEVER recorded here


# ---------------------------------------------------------------------------
# Per-identity budget (SPEC-25 design decision 6)
# ---------------------------------------------------------------------------

_BUDGET_SIGNED_IN = 20
_BUDGET_ANONYMOUS = 5


class AskBudget:
    """In-memory per-identity Ask budget.

    Anonymous identities get a lower ceiling.
    Budget is consumed *before* the model call.
    """

    def __init__(self) -> None:
        self._counts: Dict[str, int] = {}

    def remaining(self, user_id: str, is_anonymous: bool = False) -> int:
        limit = _BUDGET_ANONYMOUS if is_anonymous else _BUDGET_SIGNED_IN
        return max(0, limit - self._counts.get(user_id, 0))

    def consume(self, user_id: str, is_anonymous: bool = False) -> bool:
        """Consume one ask. Returns True if allowed, False if exhausted."""
        if self.remaining(user_id, is_anonymous) <= 0:
            return False
        self._counts[user_id] = self._counts.get(user_id, 0) + 1
        return True

    def reset(self, user_id: str) -> None:
        self._counts.pop(user_id, None)


# ---------------------------------------------------------------------------
# Exact-match response cache (SPEC-25: semantic similarity insufficient)
# ---------------------------------------------------------------------------


def _cache_key(question: str, geo_region: str, venue_id: str) -> str:
    """Deterministic cache key scoped to question + region + venue."""
    raw = f"{question.strip().lower()}|{geo_region}|{venue_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


class AskCache:
    """Exact-match public-fact cache. Not identity-scoped (public catalog only)."""

    def __init__(self) -> None:
        self._store: Dict[str, AskResponse] = {}

    def get(self, question: str, geo_region: str, venue_id: str) -> Optional[AskResponse]:
        key = _cache_key(question, geo_region, venue_id)
        hit = self._store.get(key)
        if hit is not None:
            # Return a copy marked as cache hit
            return AskResponse(
                answer=hit.answer,
                tier=hit.tier,
                path=AskPath.CACHE_HIT,
                intent=hit.intent,
                source_ids=list(hit.source_ids),
                source_class=hit.source_class,
                from_cache=True,
            )
        return None

    def put(self, question: str, geo_region: str, venue_id: str, response: AskResponse) -> None:
        key = _cache_key(question, geo_region, venue_id)
        self._store[key] = response

    def size(self) -> int:
        return len(self._store)


# ---------------------------------------------------------------------------
# Intent classifier (closed, keyword-based -- SPEC-25 DD7: cheap model)
# ---------------------------------------------------------------------------

_HOURS_KEYWORDS = {
    "open",
    "close",
    "hours",
    "timing",
    "when does",
    "opening",
    "closing",
    "what time",
    "schedule",
}
_DISH_KEYWORDS = {
    "dish",
    "food",
    "eat",
    "menu",
    "cuisine",
    "ingredient",
    "try",
    "taste",
    "recommend food",
    "street food",
    "what should i eat",
    "halal",
    "vegetarian",
    "vegan",
    "allergy",
    "allergen",
}
_PLACE_KEYWORDS = {
    "where is",
    "location",
    "how to get",
    "directions",
    "address",
    "what is",
    "tell me about",
    "describe",
    "information about",
    "nearby",
}
_CURRENT_NEXT_KEYWORDS = {
    "current",
    "next",
    "what's next",
    "where am i",
    "what now",
    "after this",
    "upcoming",
}
_PLAN_CHANGE_KEYWORDS = {
    "swap",
    "replace",
    "cancel",
    "change plan",
    "reschedule",
    "reroute",
    "add activity",
    "different place",
    "something else",
    "move",
    "skip",
}


def classify_ask_intent(message: str) -> AskIntent:
    """Classify a free-text question into the closed intent set."""
    lower = message.lower()

    def _score(keywords: set) -> int:
        return sum(1 for kw in keywords if kw in lower)

    scores = {
        AskIntent.PLAN_CHANGE: _score(_PLAN_CHANGE_KEYWORDS),
        AskIntent.OPENING_HOURS: _score(_HOURS_KEYWORDS),
        AskIntent.DISH_FACT: _score(_DISH_KEYWORDS),
        AskIntent.PLACE_IDENTITY: _score(_PLACE_KEYWORDS),
        AskIntent.TRIP_CURRENT_NEXT: _score(_CURRENT_NEXT_KEYWORDS),
    }

    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    if scores[best] == 0:
        return AskIntent.OUT_OF_SCOPE
    return best


# ---------------------------------------------------------------------------
# Catalog retrieval
# ---------------------------------------------------------------------------


@dataclass
class CatalogFact:
    """A single retrieved fact from the curated catalog."""

    fact_type: str  # e.g. "venue_description", "opening_hours", "dish"
    text: str
    source_id: str  # venue_id or dish_key
    source_class: str  # e.g. "curated_catalog"
    geo_region: str


def retrieve_catalog_facts(
    intent: AskIntent,
    geo_region: str,
    venue_name: Optional[str],
    question: str,
    db: Any,
    dish_glossary: Optional[Dict] = None,
) -> List[CatalogFact]:
    """Retrieve curated catalog facts for the given intent and context.

    Returns an empty list when no facts match (retrieval miss).
    Region-scoping: only returns facts matching geo_region.
    """
    facts: List[CatalogFact] = []

    # Find the venue in the catalog by name + region
    venue = None
    if venue_name:
        venues = db.list_venues_for_region(geo_region) if geo_region else []
        for v in venues:
            if v.get("name", "").lower() == venue_name.lower():
                venue = v
                break
            # Partial match fallback
            if venue_name.lower() in v.get("name", "").lower():
                venue = v

    if intent == AskIntent.PLACE_IDENTITY and venue:
        facts.append(
            CatalogFact(
                fact_type="venue_description",
                text=(
                    f"{venue['name']} is located at {venue.get('micro_location', 'unknown location')}. "
                    f"{venue.get('description', '')}"
                ),
                source_id=venue.get("venue_id", venue["name"]),
                source_class="curated_catalog",
                geo_region=geo_region,
            )
        )

    elif intent == AskIntent.OPENING_HOURS and venue:
        hours = venue.get("opening_hours", "")
        if hours:
            facts.append(
                CatalogFact(
                    fact_type="opening_hours",
                    text=(
                        f"{venue['name']} recorded hours: {hours}. "
                        "These are catalog hours and may not reflect holidays or "
                        "temporary closures -- verify locally."
                    ),
                    source_id=venue.get("venue_id", venue["name"]),
                    source_class="curated_catalog",
                    geo_region=geo_region,
                )
            )

    elif intent == AskIntent.DISH_FACT:
        # Search dish glossary by region
        if dish_glossary and dish_glossary.get("dishes"):
            region_key = dish_glossary.get("geo_region", dish_glossary.get("region", ""))
            # Only return dishes if glossary region matches trip region
            if _region_matches(region_key, geo_region):
                lower_q = question.lower()
                for dish in dish_glossary["dishes"]:
                    name_en = dish.get("name_en", "").lower()
                    name_roman = dish.get("name_roman", "").lower()
                    if (
                        name_en in lower_q
                        or name_roman in lower_q
                        or (
                            # Broad food question -- return top matches
                            any(
                                kw in lower_q
                                for kw in ["food", "eat", "dish", "try", "street food"]
                            )
                        )
                    ):
                        desc = dish.get("description", "")
                        contains = dish.get("contains", [])
                        suitable = dish.get("suitable_for", [])
                        text_parts = [f"{dish.get('name_en', '')}: {desc}"]
                        if contains:
                            text_parts.append(f"Contains: {', '.join(contains)}")
                        if suitable:
                            text_parts.append(f"Suitable for: {', '.join(suitable)}")
                        facts.append(
                            CatalogFact(
                                fact_type="dish",
                                text=". ".join(text_parts),
                                source_id=dish.get("dish_key", dish.get("name_en", "unknown")),
                                source_class="curated_catalog",
                                geo_region=geo_region,
                            )
                        )
                        if len(facts) >= 3:
                            break

    elif intent == AskIntent.PLACE_IDENTITY and not venue:
        # No venue found -- retrieval miss
        pass

    return facts


def _region_matches(glossary_region: str, trip_region: str) -> bool:
    """Check if a glossary region matches the trip region.

    The glossary uses 'laos', the trip uses 'vientiane_laos' etc.
    """
    if not glossary_region or not trip_region:
        return False
    return (
        glossary_region == trip_region
        or glossary_region in trip_region
        or trip_region in glossary_region
    )


# ---------------------------------------------------------------------------
# Deterministic answer templates (SPEC-25: templates first)
# ---------------------------------------------------------------------------


def format_deterministic_answer(
    intent: AskIntent,
    facts: List[CatalogFact],
    venue_name: Optional[str] = None,
    next_venue_name: Optional[str] = None,
    current_node_summary: Optional[str] = None,
    next_node_summary: Optional[str] = None,
) -> Optional[str]:
    """Format a deterministic answer from retrieved facts.

    Returns None if facts are insufficient for a complete answer.
    """
    if not facts and intent != AskIntent.TRIP_CURRENT_NEXT:
        return None

    if intent == AskIntent.PLACE_IDENTITY:
        return facts[0].text

    if intent == AskIntent.OPENING_HOURS:
        return facts[0].text

    if intent == AskIntent.DISH_FACT:
        lines = [f.text for f in facts]
        return "\n".join(lines)

    if intent == AskIntent.TRIP_CURRENT_NEXT:
        parts = []
        if current_node_summary:
            parts.append(f"Current: {current_node_summary}")
        if next_node_summary:
            parts.append(f"Next: {next_node_summary}")
        if parts:
            return "\n".join(parts)
        return None

    return None


# ---------------------------------------------------------------------------
# Core Ask handler
# ---------------------------------------------------------------------------


class AskService:
    """SPEC-25 grounded trip-scoped Ask.

    Guard order: exact cache -> budget -> circuit breaker -> model.
    """

    def __init__(
        self,
        llm_service: Any = None,
        db: Any = None,
        dish_glossary: Optional[Dict] = None,
    ) -> None:
        self.llm = llm_service
        self.db = db
        self.dish_glossary = dish_glossary
        self.cache = AskCache()
        self.budget = AskBudget()
        self._breaker_failures = 0
        self._breaker_threshold = 3
        self._telemetry_log: List[AskTelemetry] = []

    @property
    def telemetry_log(self) -> List[AskTelemetry]:
        return self._telemetry_log

    def _breaker_open(self) -> bool:
        return self._breaker_failures >= self._breaker_threshold

    def _record_telemetry(self, t: AskTelemetry) -> None:
        self._telemetry_log.append(t)

    async def handle_ask(
        self,
        question: str,
        geo_region: str,
        user_id: str,
        is_anonymous: bool = False,
        venue_name: Optional[str] = None,
        venue_id: Optional[str] = None,
        next_venue_name: Optional[str] = None,
        current_node_summary: Optional[str] = None,
        next_node_summary: Optional[str] = None,
        llm_key_present: bool = False,
    ) -> AskResponse:
        """Handle a trip-scoped Ask question.

        Returns a grounded response or a named refusal.
        Never persists itinerary nodes.
        """
        t0 = time.monotonic()
        tel = AskTelemetry(geo_region=geo_region)

        # 1. Classify intent
        intent = classify_ask_intent(question)
        tel.intent = intent.value

        # Plan-change: return proposal for confirmation sheet
        if intent == AskIntent.PLAN_CHANGE:
            resp = AskResponse(
                answer=(
                    "That sounds like a plan change. Use the trip controls to "
                    "swap, cancel, or add activities -- changes require your "
                    "confirmation before they take effect."
                ),
                tier=TrustTier.DEFER,
                path=AskPath.GROUNDED_DETERMINISTIC,
                intent=intent,
            )
            tel.path = resp.path.value
            tel.latency_ms = (time.monotonic() - t0) * 1000
            self._record_telemetry(tel)
            return resp

        # 2. Exact cache check
        cached = self.cache.get(question, geo_region, venue_id or "")
        if cached is not None:
            tel.path = AskPath.CACHE_HIT.value
            tel.cache_status = "hit"
            tel.latency_ms = (time.monotonic() - t0) * 1000
            self._record_telemetry(tel)
            return cached

        # 3. Retrieve catalog facts
        facts = retrieve_catalog_facts(
            intent=intent,
            geo_region=geo_region,
            venue_name=venue_name,
            question=question,
            db=self.db,
            dish_glossary=self.dish_glossary,
        )
        tel.source_ids = [f.source_id for f in facts]

        # 4. Retrieval miss -> hedge/refuse, no model call
        if not facts and intent != AskIntent.TRIP_CURRENT_NEXT:
            resp = AskResponse(
                answer=(
                    "I don't have verified information for that question in "
                    "this region. Check with the venue directly for the most "
                    "accurate answer."
                ),
                tier=TrustTier.REFUSE,
                path=AskPath.RETRIEVAL_MISS,
                intent=intent,
            )
            tel.path = resp.path.value
            tel.latency_ms = (time.monotonic() - t0) * 1000
            self._record_telemetry(tel)
            return resp

        # 5. Try deterministic template first
        det_answer = format_deterministic_answer(
            intent=intent,
            facts=facts,
            venue_name=venue_name,
            next_venue_name=next_venue_name,
            current_node_summary=current_node_summary,
            next_node_summary=next_node_summary,
        )
        if det_answer is not None:
            source_class = facts[0].source_class if facts else "trip_state"
            resp = AskResponse(
                answer=det_answer,
                tier=TrustTier.HEDGE,
                path=AskPath.GROUNDED_DETERMINISTIC,
                intent=intent,
                source_ids=[f.source_id for f in facts],
                source_class=source_class,
            )
            # Cache grounded deterministic answers
            self.cache.put(question, geo_region, venue_id or "", resp)
            tel.path = resp.path.value
            tel.cache_status = "miss_then_store"
            tel.latency_ms = (time.monotonic() - t0) * 1000
            self._record_telemetry(tel)
            return resp

        # --- Guards before model call ---

        # 6. No LLM key
        if not llm_key_present:
            resp = AskResponse(
                answer=(
                    "Ask is available but the model service is not configured. "
                    "Try again when the service is fully set up."
                ),
                tier=TrustTier.REFUSE,
                path=AskPath.NO_KEY,
                intent=intent,
                fallback_reason="TB_LITELLM_API_KEY not set",
            )
            tel.path = resp.path.value
            tel.fallback_reason = resp.fallback_reason
            tel.latency_ms = (time.monotonic() - t0) * 1000
            self._record_telemetry(tel)
            return resp

        # 7. Budget check
        if not self.budget.consume(user_id, is_anonymous):
            resp = AskResponse(
                answer="You've reached your Ask limit for now. Try again later.",
                tier=TrustTier.REFUSE,
                path=AskPath.BUDGET_EXHAUSTED,
                intent=intent,
                fallback_reason="ask_budget_exhausted",
            )
            tel.path = resp.path.value
            tel.fallback_reason = resp.fallback_reason
            tel.latency_ms = (time.monotonic() - t0) * 1000
            self._record_telemetry(tel)
            return resp

        # 8. Circuit breaker
        if self._breaker_open():
            resp = AskResponse(
                answer="The Ask service is temporarily unavailable. Please try again shortly.",
                tier=TrustTier.REFUSE,
                path=AskPath.BREAKER_OPEN,
                intent=intent,
                fallback_reason="circuit_breaker_open",
            )
            tel.path = resp.path.value
            tel.fallback_reason = resp.fallback_reason
            tel.latency_ms = (time.monotonic() - t0) * 1000
            self._record_telemetry(tel)
            return resp

        # 9. Model call (light model only, SPEC-25 DD7)
        # Only used to phrase retrieved facts -- never to generate facts.
        try:
            fact_context = "\n".join(f.text for f in facts)
            result = await self.llm.complete(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are Travel Buddy AI. Rephrase the following "
                            "verified facts into a concise, helpful answer. "
                            "Do not add any information not present in the facts. "
                            f"Region: {geo_region}."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Question: {question}\n\nFacts:\n{fact_context}",
                    },
                ],
                routing_tier="light",
                temperature=0.3,
                max_tokens=150,
            )
            tel.model = result.get("model_used", "")
            tel.tokens_in = result.get("tokens", {}).get("input", 0)
            tel.tokens_out = result.get("tokens", {}).get("output", 0)
            tel.cost_usd = result.get("cost_usd", 0.0)

            resp = AskResponse(
                answer=result["content"],
                tier=TrustTier.HEDGE,
                path=AskPath.GROUNDED_MODEL_PHRASED,
                intent=intent,
                source_ids=[f.source_id for f in facts],
                source_class=facts[0].source_class if facts else "",
            )
            self.cache.put(question, geo_region, venue_id or "", resp)
            self._breaker_failures = 0  # reset on success
            tel.path = resp.path.value
            tel.latency_ms = (time.monotonic() - t0) * 1000
            self._record_telemetry(tel)
            return resp

        except Exception as exc:
            self._breaker_failures += 1
            resp = AskResponse(
                answer=(
                    "I couldn't process that question right now. "
                    "The information may be available -- please try again."
                ),
                tier=TrustTier.REFUSE,
                path=AskPath.MODEL_ERROR_FALLBACK,
                intent=intent,
                fallback_reason=f"model_error: {type(exc).__name__}",
            )
            tel.path = resp.path.value
            tel.fallback_reason = resp.fallback_reason
            tel.latency_ms = (time.monotonic() - t0) * 1000
            self._record_telemetry(tel)
            return resp
