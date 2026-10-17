"""SPEC-25: Grounded trip-scoped Ask service (correction pass).

Retrieval-first query: classify -> retrieve -> template (or refuse).
Ask never persists itinerary rows. Mutations stay HITL.

This slice: NO llm.complete calls. Deterministic templates or refuse.
SPEC-14: never emit suitable_for / dietary suitability claims.
SPEC-43: question text never stored in telemetry or cache keys.
SPEC-41: prefer structured hours; flat defaults get hedge/refuse.

Status: PARTIAL -- model fallback, budget gating, circuit breaker
activation, Flutter acceptance, and offline acceptance remain deferred
in this deterministic-only slice.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional

from pydantic import BaseModel, ConfigDict

from services.opening_hours import is_valid_structured_hours as _validate_structured_hours

logger = logging.getLogger("ask_service")


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
    TODAY_TONIGHT = "today_tonight"
    NEARBY_OPTION = "nearby_option"
    PRACTICAL_RULE = "practical_rule"
    COMPARE = "compare"
    WHAT_NOW = "what_now"
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
    OUT_OF_SCOPE = "out_of_scope"


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
    proposal: Optional[Dict[str, Any]] = None
    food_disclaimer: Optional[str] = None
    what_now: Optional[Dict[str, Any]] = None


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
    Deterministic/cache answers never consume budget.
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


# Bump when venue/dish catalog data changes to invalidate stale cache.
_CATALOG_VERSION = "2026-09-16-v1"


def _cache_key(question: str, geo_region: str, venue_id: str, catalog_version: str = "") -> str:
    """Deterministic cache key scoped to question + region + venue + catalog."""
    cv = catalog_version or _CATALOG_VERSION
    raw = f"{question.strip().lower()}|{geo_region}|{venue_id}|{cv}"
    return hashlib.sha256(raw.encode()).hexdigest()


_CACHEABLE_INTENTS = frozenset(
    {AskIntent.PLACE_IDENTITY, AskIntent.OPENING_HOURS, AskIntent.DISH_FACT}
)


class AskCache:
    """Exact-match public-fact cache.

    Never caches TRIP_CURRENT_NEXT, PLAN_CHANGE, OUT_OF_SCOPE,
    refusals, or model-phrased prose.
    """

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
                food_disclaimer=hit.food_disclaimer,
            )
        return None

    def put(
        self,
        question: str,
        geo_region: str,
        venue_id: str,
        response: AskResponse,
    ) -> None:
        """Store only if the response is safe to cache."""
        if response.intent not in _CACHEABLE_INTENTS:
            return
        if response.path != AskPath.GROUNDED_DETERMINISTIC:
            return
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
}
_DIETARY_KEYWORDS = {
    "halal",
    "vegetarian",
    "vegan",
    "allergy",
    "allergen",
    "gluten free",
    "kosher",
    "dairy free",
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
    # Must be a superset of all sub-classifier keywords so the main
    # classifier can reach PLAN_CHANGE for every phrase the sub-classifier
    # handles.
    "swap",
    "replace",
    "switch",
    "something else",
    "different place",
    "cancel",
    "remove",
    "delete",
    "drop",
    "skip",
    "add",
    "insert",
    "include",
    "add activity",
    "move",
    "reschedule",
    "shift",
    "earlier",
    "later",
    "push",
    "reroute",
    "change plan",
}


_TODAY_TONIGHT_KEYWORDS = {
    "today",
    "tonight",
    "this evening",
    "rest of the day",
    "remaining today",
    "what's left",
    "left today",
    "still to do",
    "this afternoon",
}
_NEARBY_OPTION_KEYWORDS = {
    "where can i",
    "nearby",
    "close by",
    "walking distance",
    "somewhere to",
    "find a",
    "work",
    "coffee",
    "wifi",
    "indoor",
    "low effort",
    "quick meal",
    "grab food",
    "lunch spot",
    "dinner spot",
    "breakfast",
}
_PRACTICAL_RULE_KEYWORDS = {
    "temple",
    "wat",
    "dress code",
    "wear",
    "etiquette",
    "tuk tuk",
    "transport",
    "how to get",
    "get around",
    "atm",
    "cash",
    "payment",
    "pay",
    "kip",
    "sim card",
    "internet",
    "connectivity",
    "book",
    "booking",
    "reserve",
    "how to book",
}
_COMPARE_KEYWORDS = {
    "compare",
    "versus",
    "vs",
    "which is better",
    "difference between",
    "which one",
    "best of",
    "options for",
    "alternatives",
    "x or y",
}


def classify_ask_intent(message: str) -> AskIntent:
    """Classify a free-text question into the closed intent set."""
    lower = message.lower()

    def _score(keywords: set) -> int:
        return sum(1 for kw in keywords if kw in lower)

    scores = {
        AskIntent.PLAN_CHANGE: _score(_PLAN_CHANGE_KEYWORDS),
        AskIntent.OPENING_HOURS: _score(_HOURS_KEYWORDS),
        AskIntent.DISH_FACT: _score(_DISH_KEYWORDS) + _score(_DIETARY_KEYWORDS),
        AskIntent.PLACE_IDENTITY: _score(_PLACE_KEYWORDS),
        AskIntent.TRIP_CURRENT_NEXT: _score(_CURRENT_NEXT_KEYWORDS),
        AskIntent.TODAY_TONIGHT: _score(_TODAY_TONIGHT_KEYWORDS),
        AskIntent.NEARBY_OPTION: _score(_NEARBY_OPTION_KEYWORDS),
        AskIntent.PRACTICAL_RULE: _score(_PRACTICAL_RULE_KEYWORDS),
        AskIntent.COMPARE: _score(_COMPARE_KEYWORDS),
    }

    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    if scores[best] == 0:
        return AskIntent.OUT_OF_SCOPE
    return best


def _is_dietary_question(message: str) -> bool:
    """Check if the question is specifically about dietary suitability."""
    lower = message.lower()
    return any(kw in lower for kw in _DIETARY_KEYWORDS)


# ---------------------------------------------------------------------------
# Plan-change sub-classifier (blocker 3)
# ---------------------------------------------------------------------------

_CANCEL_KEYWORDS = {"cancel", "remove", "delete", "drop"}
_ADD_KEYWORDS = {"add", "insert", "include", "add activity"}
_MOVE_KEYWORDS = {"move", "reschedule", "shift", "earlier", "later", "push"}
_SWAP_KEYWORDS = {"swap", "replace", "switch", "something else", "different place"}


def _classify_plan_change(message: str) -> Optional[str]:
    """Sub-classify a PLAN_CHANGE into an unambiguous command.

    Returns one of 'cancel_activity', 'add_activity', 'reroute',
    'swap_activity', or None when ambiguous.

    Uses word-boundary matching so 'remove' does not false-hit 'move'.
    """
    import re

    lower = message.lower()

    def _hits(keywords: set) -> int:
        total = 0
        for kw in keywords:
            if " " in kw:
                # Multi-word: plain substring
                if kw in lower:
                    total += 1
            else:
                # Single-word: word-boundary
                if re.search(r"\b" + re.escape(kw) + r"\b", lower):
                    total += 1
        return total

    scores = {
        "cancel_activity": _hits(_CANCEL_KEYWORDS),
        "add_activity": _hits(_ADD_KEYWORDS),
        "reroute": _hits(_MOVE_KEYWORDS),
        "swap_activity": _hits(_SWAP_KEYWORDS),
    }
    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    if scores[best] == 0:
        return None  # no keyword hit at all
    # Ambiguous: two commands score equally
    top_score = scores[best]
    if sum(1 for v in scores.values() if v == top_score) > 1:
        return None
    return best


# ---------------------------------------------------------------------------
# Structured-hours renderer (blocker 4)
# ---------------------------------------------------------------------------

_DAY_ORDER = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# Hours validation delegates to the canonical SPEC-41 evaluator
# (imported at module top as _validate_structured_hours).


def _render_structured_hours(structured: Dict[str, Any]) -> str:
    """Render a validated opening_hours_structured dict to human-readable text.

    Caller must validate first; this function assumes valid input.
    Example input:  {"mon": [["17:00", "23:00"]], "tue": [["17:00", "23:00"]]}
    Example output: "Mon 17:00-23:00, Tue 17:00-23:00"
    """
    parts = []
    for day in _DAY_ORDER:
        slots = structured.get(day)
        if not slots:
            continue
        slot_strs = [f"{s[0]}-{s[1]}" for s in slots]
        parts.append(f"{day.capitalize()} {', '.join(slot_strs)}")
    return ", ".join(parts) if parts else "hours not specified"


# ---------------------------------------------------------------------------
# Catalog retrieval (SPEC-14: no suitable_for, SPEC-41: structured hours)
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

    if not geo_region:
        return facts  # Empty region is always a miss

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
        structured = venue.get("opening_hours_structured")
        flat_hours = venue.get("opening_hours", "")
        _dflt = {"09:00-23:00", "09:00-22:00", "08:00-22:00"}

        if structured is not None:
            # Structured data present: use it only if SPEC-41-valid.
            # Malformed/partial structured -> RETRIEVAL_MISS (no fallback
            # to flat_hours, because flat is the legacy format for the
            # same data; the structured form is canonical).
            if _validate_structured_hours(structured):
                rendered = _render_structured_hours(structured)
                facts.append(
                    CatalogFact(
                        fact_type="opening_hours",
                        text=(
                            f"{venue['name']} hours: {rendered}. "
                            "These are catalog hours and may not reflect "
                            "holidays or temporary closures -- verify locally."
                        ),
                        source_id=venue.get("venue_id", venue["name"]),
                        source_class="curated_catalog",
                        geo_region=geo_region,
                    )
                )
            # else: malformed structured -> facts stays empty -> miss
        elif flat_hours and flat_hours not in _dflt:
            facts.append(
                CatalogFact(
                    fact_type="opening_hours",
                    text=(
                        f"{venue['name']} recorded hours: {flat_hours}. "
                        "These are catalog hours and may not reflect "
                        "holidays or temporary closures -- verify locally."
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
                        # SPEC-14: NEVER include suitable_for
                        text_parts = [f"{dish.get('name_en', '')}: {desc}"]
                        if contains:
                            text_parts.append(f"Contains: {', '.join(contains)}")
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
    if glossary_region == trip_region:
        return True
    return glossary_region in trip_region.split("_")


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
# Dish glossary loader (per-request, exact region match)
# ---------------------------------------------------------------------------


def load_dish_glossary(geo_region: str) -> Optional[Dict]:
    """Load the dish glossary for the given region."""
    if not geo_region:
        return None
    data_dir = Path(__file__).resolve().parent.parent / "data"
    exact = data_dir / f"{geo_region}_dish_glossary.json"
    if exact.exists():
        with open(exact) as f:
            return json.load(f)
    for candidate in sorted(data_dir.glob("*_dish_glossary.json")):
        with open(candidate) as f:
            glossary = json.load(f)
        region_key = glossary.get("geo_region", glossary.get("region", ""))
        if _region_matches(region_key, geo_region):
            return glossary
    return None


# ---------------------------------------------------------------------------
# Practical rules loader (SPEC-25 Phase B)
# ---------------------------------------------------------------------------


def load_practical_rules() -> list:
    """Load the practical rules catalog."""
    rules_path = Path(__file__).resolve().parent.parent / "data" / "practical_rules.json"
    if not rules_path.exists():
        return []
    with open(rules_path) as f:
        data = json.load(f)
    return data.get("rules", [])


def retrieve_practical_rule(question: str, geo_region: str) -> Optional[CatalogFact]:
    """Retrieve a matching practical rule for the question and region."""
    rules = load_practical_rules()
    if not rules:
        return None
    lower = question.lower()
    best = None
    best_score = 0
    for rule in rules:
        if geo_region not in rule.get("geo_regions", []):
            continue
        score = sum(1 for kw in rule.get("keywords", []) if kw in lower)
        if score > best_score:
            best_score = score
            best = rule
    if best is None:
        return None
    return CatalogFact(
        fact_type="practical_rule",
        text=best["text"],
        source_id=best["source_id"],
        source_class=best.get("source_class", "curated_static"),
        geo_region=geo_region,
    )


# ---------------------------------------------------------------------------
# NEARBY_OPTION retrieval (SPEC-25 Phase B)
# ---------------------------------------------------------------------------

_NEARBY_CATEGORY_MAP = {
    "coffee": ["cafe"],
    "work": ["cafe"],
    "wifi": ["cafe"],
    "food": ["restaurant", "street_food"],
    "eat": ["restaurant", "street_food"],
    "lunch": ["restaurant", "street_food"],
    "dinner": ["restaurant", "street_food"],
    "breakfast": ["cafe", "restaurant"],
    "quick meal": ["street_food", "restaurant"],
    "grab food": ["street_food", "restaurant"],
    "indoor": ["cafe", "museum", "massage_spa"],
    "low effort": ["cafe", "massage_spa"],
}


def retrieve_nearby_options(
    question: str,
    geo_region: str,
    db: Any,
) -> list[CatalogFact]:
    """Retrieve nearby catalog venues matching the question category."""
    if not geo_region or db is None:
        return []
    lower = question.lower()
    target_cats: set[str] = set()
    for keyword, cats in _NEARBY_CATEGORY_MAP.items():
        if keyword in lower:
            target_cats.update(cats)
    if not target_cats:
        target_cats = {"cafe", "restaurant"}

    venues = db.list_venues_for_region(geo_region)
    facts = []
    for v in venues:
        cat = v.get("category", "")
        if cat not in target_cats:
            continue
        name = v.get("name", "")
        desc = v.get("description", "")
        micro = v.get("micro_location", "")
        facts.append(
            CatalogFact(
                fact_type="nearby_option",
                text=f"{name} ({cat}) -- {micro}. {desc[:120]}",
                source_id=v.get("venue_id", name),
                source_class="curated_catalog",
                geo_region=geo_region,
            )
        )
        if len(facts) >= 3:
            break
    return facts


# ---------------------------------------------------------------------------
# COMPARE retrieval (SPEC-25 Phase B)
# ---------------------------------------------------------------------------


def retrieve_compare_options(
    question: str,
    geo_region: str,
    db: Any,
) -> list[CatalogFact]:
    """Retrieve at most 3 catalog venues for comparison."""
    if not geo_region or db is None:
        return []
    lower = question.lower()
    venues = db.list_venues_for_region(geo_region)
    matches = []
    for v in venues:
        name = v.get("name", "").lower()
        if name and name in lower:
            matches.append(v)
    if not matches:
        # Broad match: pick venues from the same category as hint words
        target_cats: set[str] = set()
        for keyword, cats in _NEARBY_CATEGORY_MAP.items():
            if keyword in lower:
                target_cats.update(cats)
        if target_cats:
            for v in venues:
                if v.get("category", "") in target_cats:
                    matches.append(v)
                    if len(matches) >= 3:
                        break

    facts = []
    for v in matches[:3]:
        name = v.get("name", "")
        desc = v.get("description", "")
        micro = v.get("micro_location", "")
        facts.append(
            CatalogFact(
                fact_type="compare_option",
                text=f"{name} -- {micro}. {desc[:120]}",
                source_id=v.get("venue_id", name),
                source_class="curated_catalog",
                geo_region=geo_region,
            )
        )
    return facts


# ---------------------------------------------------------------------------
# TODAY_TONIGHT: filter trip nodes to today's remaining (SPEC-25 Phase B)
# ---------------------------------------------------------------------------


def format_today_tonight(
    trip_nodes: list,
    now_utc: Any,
    geo_region: str,
) -> Optional[tuple[str, list[str]]]:
    """Format remaining stops today/this evening.

    Returns (answer_text, source_ids) or None if no remaining nodes today.
    Uses destination-local date comparison.
    """
    if not trip_nodes:
        return None

    from services.destination_tz import to_destination_local

    remaining = []
    for node in trip_nodes:
        start = node.get("scheduled_start") or node.get("scheduledStart")
        if start is None:
            continue
        if hasattr(start, "timestamp"):
            node_time = start
        else:
            from datetime import datetime as _dt

            try:
                node_time = _dt.fromisoformat(str(start).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue

        # Check destination-local date is today
        node_region = node.get("geo_region") or geo_region
        node_local = to_destination_local(node_time, node_region)
        now_local = to_destination_local(now_utc, node_region)

        if node_local.date() != now_local.date():
            continue

        # Only remaining (not ended)
        duration = node.get("duration_minutes") or node.get("durationMinutes") or 60
        end = node_time + __import__("datetime").timedelta(minutes=duration)
        if now_utc >= end:
            continue

        status = node.get("status", "pending")
        if status in ("completed", "skipped"):
            continue

        remaining.append(node)

    if not remaining:
        return None

    lines = []
    source_ids = []
    for n in remaining:
        name = n.get("venue_name") or n.get("venueName") or "Unknown"
        start = n.get("scheduled_start") or n.get("scheduledStart")
        start_str = ""
        if hasattr(start, "strftime"):
            start_str = f" at {start.strftime('%H:%M')}"
        lines.append(f"- {name}{start_str}")
        sid = n.get("venue_id") or n.get("venueId") or name
        source_ids.append(sid)

    answer = "Remaining today:\n" + "\n".join(lines)
    return answer, source_ids


# ---------------------------------------------------------------------------
# Core Ask handler (no llm.complete this slice)
# ---------------------------------------------------------------------------

try:
    from config.disclaimers import FOOD_DISCLAIMER as _FOOD_DISCLAIMER
except ImportError:
    _FOOD_DISCLAIMER = "Confirm ingredients with the venue."


# ---------------------------------------------------------------------------
# Module-level singletons (survive across HTTP requests -- blocker 1)
# ---------------------------------------------------------------------------

_shared_cache = AskCache()
_shared_budget = AskBudget()


# ---------------------------------------------------------------------------
# SPEC-46 What Now -- closed request context and deterministic handler
# ---------------------------------------------------------------------------

_WHAT_NOW_INTENT_MAP: Dict[str, set] = {
    "quiet": {"temple", "viewpoint", "nature", "walking_area", "museum"},
    "food": {"restaurant", "street_food", "cafe"},
    "indoors": {"museum", "cafe", "restaurant", "massage_spa"},
    "culture": {"temple", "museum"},
    "anything": set(),
}

_WALKING_CAPS: Dict[str, int] = {"short": 15, "normal": 25, "longer": 45}
_ENERGY_DWELL_CAPS: Dict[str, int] = {"low": 60, "normal": 120, "high": 180}


class WhatNowRequest(BaseModel):
    """Validated What Now request context (Pydantic)."""

    model_config = ConfigDict(extra="ignore")

    mode: str = "what_now"
    available_minutes: int
    energy: str = "normal"
    walking: str = "normal"
    intent: str = "anything"
    context_node_id: Optional[str] = None

    ALLOWED_MINUTES: ClassVar = {45, 90, 120}
    ALLOWED_ENERGY: ClassVar = {"low", "normal", "high"}
    ALLOWED_WALKING: ClassVar = {"short", "normal", "longer"}
    ALLOWED_INTENT: ClassVar = {"quiet", "food", "indoors", "culture", "anything"}

    def model_post_init(self, __context: Any) -> None:
        if self.available_minutes not in self.ALLOWED_MINUTES:
            raise ValueError(
                f"available_minutes must be one of {sorted(self.ALLOWED_MINUTES)}, "
                f"got {self.available_minutes}"
            )
        if self.energy not in self.ALLOWED_ENERGY:
            raise ValueError(
                f"energy must be one of {sorted(self.ALLOWED_ENERGY)}, got {self.energy!r}"
            )
        if self.walking not in self.ALLOWED_WALKING:
            raise ValueError(
                f"walking must be one of {sorted(self.ALLOWED_WALKING)}, got {self.walking!r}"
            )
        if self.intent not in self.ALLOWED_INTENT:
            raise ValueError(
                f"intent must be one of {sorted(self.ALLOWED_INTENT)}, got {self.intent!r}"
            )


def _resolve_what_now_context(
    request: WhatNowRequest,
    trip_nodes: List[Dict[str, Any]],
    now_utc,
    geo_region: str,
) -> Optional[Dict[str, Any]]:
    """Resolve context node and location source for What Now."""
    from datetime import timedelta

    from services.destination_tz import to_destination_local

    if request.context_node_id:
        for n in trip_nodes:
            if n.get("node_id") == request.context_node_id:
                node_region = n.get("geo_region") or geo_region
                if node_region:
                    return {
                        "node": n,
                        "location_source": "trip_position",
                        "context_label": "Using your trip position",
                        "geo_region": node_region,
                    }
                return None
        return None

    local_now = to_destination_local(now_utc, geo_region)
    best_node = None
    best_distance = None
    for n in trip_nodes:
        start_raw = n.get("scheduled_start")
        if not start_raw:
            continue
        if isinstance(start_raw, str):
            from datetime import datetime as _dt

            try:
                start = _dt.fromisoformat(start_raw.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
        else:
            start = start_raw
        node_region = n.get("geo_region") or geo_region
        node_local = to_destination_local(start, node_region)
        dur = n.get("duration_minutes", 90)
        end_local = node_local + timedelta(minutes=dur)
        if node_local <= local_now < end_local:
            return {
                "node": n,
                "location_source": "trip_position",
                "context_label": "Using your trip position",
                "geo_region": node_region,
            }
        dist = abs((node_local - local_now).total_seconds())
        if best_distance is None or dist < best_distance:
            best_distance = dist
            best_node = n
    if best_node:
        node_region = best_node.get("geo_region") or geo_region
        return {
            "node": best_node,
            "location_source": "trip_position",
            "context_label": "Using your trip position",
            "geo_region": node_region,
        }

    if geo_region:
        from config.regions import REGIONS

        region = REGIONS.get(geo_region)
        display = region.display_name if region else geo_region
        return {
            "node": None,
            "location_source": "region_anchor",
            "context_label": f"Browsing in {display}",
            "geo_region": geo_region,
        }
    return None


def _compute_walking_minutes(
    context_node: Optional[Dict[str, Any]], candidate: Dict[str, Any]
) -> Optional[int]:
    if context_node is None:
        return None
    from services.transit import walking_minutes as _walking

    try:
        return _walking(
            context_node.get("lat"),
            context_node.get("lng"),
            candidate.get("lat"),
            candidate.get("lng"),
        )
    except (ValueError, TypeError):
        return None


def _candidate_reason_codes(
    candidate: Dict[str, Any],
    request: "WhatNowRequest",
    context_node: Optional[Dict[str, Any]],
    walk_min: Optional[int],
    hours_ok: bool,
    has_next_booking: bool,
    trip_vibe_tags: set,
) -> List[str]:
    codes: List[str] = []
    dwell = candidate.get("typical_dwell_minutes")
    total = (dwell or 0) + (walk_min or 0)
    if dwell is not None and total <= request.available_minutes:
        codes.append("fits_available_window")
    if hours_ok:
        codes.append("open_for_planned_time")
    if has_next_booking:
        codes.append("keeps_next_booking_reachable")
    cat = candidate.get("category", "")
    intent_cats = _WHAT_NOW_INTENT_MAP.get(request.intent, set())
    if intent_cats and cat in intent_cats:
        codes.append("matches_requested_type")
    cand_vibes = set(candidate.get("vibe_tags") or [])
    if trip_vibe_tags and cand_vibes & trip_vibe_tags:
        codes.append("matches_trip_interest")
    if context_node and candidate.get("micro_location"):
        ctx_micro = context_node.get("micro_location", "")
        if ctx_micro and ctx_micro == candidate.get("micro_location"):
            codes.append("same_neighbourhood")
    if walk_min is not None and walk_min <= 15:
        codes.append("short_walk_from_context")
    if dwell is not None and dwell <= 45:
        codes.append("lower_typical_dwell")
    indoor = candidate.get("indoor_outdoor", "")
    has_ac = candidate.get("has_aircon", False)
    if indoor in ("indoor", "mixed") or has_ac:
        codes.append("indoor_option")
    return codes


def _candidate_unknown_fields(
    candidate: Dict[str, Any], walk_min: Optional[int], hours_ok
) -> List[str]:
    unknowns: List[str] = []
    if candidate.get("typical_dwell_minutes") is None:
        unknowns.append("typical_dwell")
    if walk_min is None:
        unknowns.append("walking_time")
    if hours_ok is None:
        unknowns.append("opening_hours")
    unknowns.extend(["price", "live_crowds", "traffic"])
    return unknowns


def handle_what_now(
    request: "WhatNowRequest",
    trip_nodes: List[Dict[str, Any]],
    now_utc,
    geo_region: str,
    db: Any,
) -> "AskResponse":
    """Deterministic What Now handler. No LLM calls."""
    from datetime import timedelta

    from services.destination_tz import to_destination_local

    ctx = _resolve_what_now_context(request, trip_nodes, now_utc, geo_region)
    if ctx is None:
        return AskResponse(
            answer="I could not determine your current location from the trip.",
            tier=TrustTier.REFUSE,
            path=AskPath.RETRIEVAL_MISS,
            intent=AskIntent.WHAT_NOW,
        )

    context_node = ctx["node"]
    location_source = ctx["location_source"]
    context_label = ctx["context_label"]
    resolved_region = ctx["geo_region"]

    all_venues = db.list_venues_for_region(resolved_region) if db else []
    itinerary_ids = set()
    itinerary_names = set()
    trip_vibe_tags: set = set()
    for n in trip_nodes:
        vid = n.get("venue_id")
        if vid:
            itinerary_ids.add(vid)
        vname = n.get("venue_name", "")
        if vname:
            itinerary_names.add(vname.lower())
        trip_vibe_tags.update(n.get("vibe_tags") or [])

    ctx_name = (context_node.get("venue_name", "") if context_node else "").lower()
    ctx_vid = (context_node.get("venue_id") or "") if context_node else ""

    local_now = to_destination_local(now_utc, resolved_region)
    next_booking_start = None
    for n in trip_nodes:
        if n.get("is_locked") and n.get("node_kind") == "booking":
            raw = n.get("scheduled_start")
            if not raw:
                continue
            if isinstance(raw, str):
                from datetime import datetime as _dt

                try:
                    bstart = _dt.fromisoformat(raw.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    continue
            else:
                bstart = raw
            bl = to_destination_local(bstart, resolved_region)
            if bl > local_now and (next_booking_start is None or bl < next_booking_start):
                next_booking_start = bl

    intent_cats = _WHAT_NOW_INTENT_MAP.get(request.intent, set())
    walking_cap = _WALKING_CAPS.get(request.walking, 25)
    energy_dwell_cap = _ENERGY_DWELL_CAPS.get(request.energy, 120)
    candidates = []

    for venue in all_venues:
        cat = venue.get("category", "")
        name = venue.get("name", "")
        venue_id = str(venue.get("venue_id") or name)
        if cat in ("hospital", "pharmacy", "transport_hub"):
            continue
        if not name.strip():
            continue
        if venue_id in itinerary_ids or name.lower() in itinerary_names:
            continue
        if ctx_name and name.lower() == ctx_name:
            continue
        if ctx_vid and venue_id == ctx_vid:
            continue
        if intent_cats and cat not in intent_cats:
            continue

        walk_min = None
        if location_source == "trip_position" and context_node:
            walk_min = _compute_walking_minutes(context_node, venue)
        if walk_min is not None and walk_min > walking_cap:
            continue

        dwell = venue.get("typical_dwell_minutes")
        if dwell is not None and dwell > energy_dwell_cap:
            continue
        if dwell is not None and (dwell + (walk_min or 0)) > request.available_minutes:
            continue

        hours_struct = venue.get("opening_hours")
        hours_ok = None
        if isinstance(hours_struct, dict):
            from services.opening_hours import HoursResult, check_slot

            proposed_local = local_now + timedelta(minutes=walk_min or 0)
            try:
                result = check_slot(hours_struct, proposed_local, dwell or 60)
                if result == HoursResult.CLOSED:
                    continue
                hours_ok = result == HoursResult.FITS
            except (ValueError, TypeError):
                pass

        has_next_booking = False
        if next_booking_start is not None:
            total_dur = (dwell or 60) + (walk_min or 0)
            if local_now + timedelta(minutes=total_dur) > next_booking_start:
                continue
            has_next_booking = True

        reason_codes = _candidate_reason_codes(
            venue,
            request,
            context_node,
            walk_min,
            hours_ok or False,
            has_next_booking,
            trip_vibe_tags,
        )
        unknown_fields = _candidate_unknown_fields(venue, walk_min, hours_ok)
        proposed_start_local = local_now + timedelta(minutes=walk_min or 0)

        candidates.append(
            {
                "candidate_id": f"what_now:{venue_id}",
                "venue_id": venue_id,
                "name": name,
                "micro_location_display": venue.get("micro_location", ""),
                "category": cat,
                "typical_dwell_minutes": dwell,
                "scheduled_start": proposed_start_local.isoformat(),
                "reason_codes": reason_codes,
                "unknown_fields": unknown_fields,
                "_rc": len(reason_codes),
                "_dw": dwell or 999,
                "_wk": walk_min if walk_min is not None else 999,
                "_nm": name.lower(),
            }
        )

    candidates.sort(key=lambda c: (-c["_rc"], c["_dw"], c["_wk"], c["_nm"]))
    result_candidates = [
        {k: v for k, v in c.items() if not k.startswith("_")} for c in candidates[:5]
    ]

    if not result_candidates:
        return AskResponse(
            answer=(
                f"No feasible options found for {request.available_minutes} minutes "
                "with your current filters. Try a longer window or different activity type."
            ),
            tier=TrustTier.REFUSE,
            path=AskPath.RETRIEVAL_MISS,
            intent=AskIntent.WHAT_NOW,
        )

    what_now_result = {
        "location_source": location_source,
        "context_label": context_label,
        "candidates": result_candidates,
    }
    count = len(result_candidates)
    names_str = ", ".join(c["name"] for c in result_candidates[:3])
    suffix = f" and {count - 3} more" if count > 3 else ""
    answer = f"Found {count} option{'s' if count != 1 else ''} nearby: {names_str}{suffix}."
    return AskResponse(
        answer=answer,
        tier=TrustTier.HEDGE,
        path=AskPath.GROUNDED_DETERMINISTIC,
        intent=AskIntent.WHAT_NOW,
        source_ids=[c["venue_id"] for c in result_candidates],
        source_class="curated_catalog",
        what_now=what_now_result,
    )


class AskService:
    """SPEC-25 grounded trip-scoped Ask.

    This slice: deterministic templates or refuse. No llm.complete.

    Cache, budget, and breaker are module-level singletons so they
    survive across HTTP requests.  Unit tests may inject their own.
    """

    def __init__(
        self,
        llm_service: Any = None,
        db: Any = None,
        dish_glossary: Optional[Dict] = None,
        cache: Optional[AskCache] = None,
        budget: Optional[AskBudget] = None,
    ) -> None:
        self.llm = llm_service
        self.db = db
        self.dish_glossary = dish_glossary
        self.cache = cache if cache is not None else _shared_cache
        self.budget = budget if budget is not None else _shared_budget
        self._breaker_failures = 0
        self._breaker_threshold = 3
        self._telemetry_log: List[AskTelemetry] = []

    @property
    def telemetry_log(self) -> List[AskTelemetry]:
        return self._telemetry_log

    def _breaker_open(self) -> bool:
        return self._breaker_failures >= self._breaker_threshold

    def _emit_telemetry(self, t: AskTelemetry) -> None:
        """Emit telemetry record. SPEC-43: no question text."""
        self._telemetry_log.append(t)
        logger.info(
            "ask_telemetry",
            extra={
                "intent": t.intent,
                "path": t.path,
                "geo_region": t.geo_region,
                "source_ids": t.source_ids,
                "cache_status": t.cache_status,
                "fallback_reason": t.fallback_reason,
                "latency_ms": t.latency_ms,
            },
        )

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
        target_node_id: Optional[str] = None,
        **kwargs: Any,
    ) -> AskResponse:
        """Handle a trip-scoped Ask question.

        No llm.complete this slice. Deterministic templates or refuse.
        """
        t0 = time.monotonic()
        tel = AskTelemetry(geo_region=geo_region)

        # 1. Classify intent
        intent = classify_ask_intent(question)
        tel.intent = intent.value

        # OUT_OF_SCOPE: refuse immediately
        if intent == AskIntent.OUT_OF_SCOPE:
            resp = AskResponse(
                answer=(
                    "I can help with questions about your trip venues, "
                    "hours, and local food. For other topics, try a "
                    "general search."
                ),
                tier=TrustTier.REFUSE,
                path=AskPath.OUT_OF_SCOPE,
                intent=intent,
            )
            tel.path = resp.path.value
            tel.latency_ms = (time.monotonic() - t0) * 1000
            self._emit_telemetry(tel)
            return resp

        # PLAN_CHANGE: typed HITL proposal, never mutate
        if intent == AskIntent.PLAN_CHANGE:
            sub_cmd = _classify_plan_change(question)
            if sub_cmd is not None:
                proposal = {
                    "event_type": sub_cmd,
                    "target_node_id": target_node_id or "",
                    "summary": (
                        f"Proposed: {sub_cmd.replace('_', ' ')}. "
                        "Confirm on the trip controls to apply."
                    ),
                }
                answer = (
                    f"That sounds like a plan change ({sub_cmd.replace('_', ' ')}). "
                    "I'll prepare a proposal for your review."
                )
            else:
                # Ambiguous -- defer without executable proposal
                proposal = None
                answer = (
                    "That sounds like a plan change, but I'm not sure "
                    "exactly what you'd like. Could you clarify whether "
                    "you want to swap, cancel, add, or reschedule?"
                )
            resp = AskResponse(
                answer=answer,
                tier=TrustTier.DEFER,
                path=AskPath.GROUNDED_DETERMINISTIC,
                intent=intent,
                proposal=proposal,
            )
            tel.path = resp.path.value
            tel.latency_ms = (time.monotonic() - t0) * 1000
            self._emit_telemetry(tel)
            return resp

        # TODAY_TONIGHT: remaining stops today from trip nodes
        if intent == AskIntent.TODAY_TONIGHT:
            trip_nodes_raw = kwargs.get("trip_nodes") or []
            from datetime import datetime, timezone

            now_utc = kwargs.get("now_utc") or datetime.now(tz=timezone.utc)
            result = format_today_tonight(trip_nodes_raw, now_utc, geo_region)
            if result is not None:
                answer_text, sids = result
                resp = AskResponse(
                    answer=answer_text,
                    tier=TrustTier.HEDGE,
                    path=AskPath.GROUNDED_DETERMINISTIC,
                    intent=intent,
                    source_ids=sids,
                    source_class="trip_state",
                )
            else:
                resp = AskResponse(
                    answer=(
                        "No remaining stops scheduled for today. "
                        "Check tomorrow's plan or ask about nearby options."
                    ),
                    tier=TrustTier.REFUSE,
                    path=AskPath.RETRIEVAL_MISS,
                    intent=intent,
                )
            tel.path = resp.path.value
            tel.source_ids = resp.source_ids
            tel.latency_ms = (time.monotonic() - t0) * 1000
            self._emit_telemetry(tel)
            return resp

        # NEARBY_OPTION: catalog venues by category in geo_region
        if intent == AskIntent.NEARBY_OPTION:
            facts = retrieve_nearby_options(question, geo_region, self.db)
            if facts:
                lines = [f.text for f in facts]
                resp = AskResponse(
                    answer="\n".join(lines),
                    tier=TrustTier.HEDGE,
                    path=AskPath.GROUNDED_DETERMINISTIC,
                    intent=intent,
                    source_ids=[f.source_id for f in facts],
                    source_class="curated_catalog",
                )
            else:
                resp = AskResponse(
                    answer=("I don't have catalog options matching that in this region right now."),
                    tier=TrustTier.REFUSE,
                    path=AskPath.RETRIEVAL_MISS,
                    intent=intent,
                )
            tel.path = resp.path.value
            tel.source_ids = resp.source_ids
            tel.latency_ms = (time.monotonic() - t0) * 1000
            self._emit_telemetry(tel)
            return resp

        # PRACTICAL_RULE: sourced region rules from static catalog
        if intent == AskIntent.PRACTICAL_RULE:
            rule_fact = retrieve_practical_rule(question, geo_region)
            if rule_fact is not None:
                resp = AskResponse(
                    answer=rule_fact.text,
                    tier=TrustTier.HEDGE,
                    path=AskPath.GROUNDED_DETERMINISTIC,
                    intent=intent,
                    source_ids=[rule_fact.source_id],
                    source_class=rule_fact.source_class,
                )
            else:
                resp = AskResponse(
                    answer=(
                        "I don't have verified information for that "
                        "in this region. Check with local sources."
                    ),
                    tier=TrustTier.REFUSE,
                    path=AskPath.RETRIEVAL_MISS,
                    intent=intent,
                )
            tel.path = resp.path.value
            tel.source_ids = resp.source_ids
            tel.latency_ms = (time.monotonic() - t0) * 1000
            self._emit_telemetry(tel)
            return resp

        # COMPARE: at most 3 catalog-backed options with source_ids
        if intent == AskIntent.COMPARE:
            facts = retrieve_compare_options(question, geo_region, self.db)
            if facts:
                lines = [f.text for f in facts]
                resp = AskResponse(
                    answer="\n".join(lines),
                    tier=TrustTier.HEDGE,
                    path=AskPath.GROUNDED_DETERMINISTIC,
                    intent=intent,
                    source_ids=[f.source_id for f in facts],
                    source_class="curated_catalog",
                )
            else:
                resp = AskResponse(
                    answer=("I don't have enough catalog data to compare options in this region."),
                    tier=TrustTier.REFUSE,
                    path=AskPath.RETRIEVAL_MISS,
                    intent=intent,
                )
            tel.path = resp.path.value
            tel.source_ids = resp.source_ids
            tel.latency_ms = (time.monotonic() - t0) * 1000
            self._emit_telemetry(tel)
            return resp

        # Cache check (only catalog intents)
        if intent in _CACHEABLE_INTENTS:
            cached = self.cache.get(question, geo_region, venue_id or "")
            if cached is not None:
                tel.path = AskPath.CACHE_HIT.value
                tel.cache_status = "hit"
                tel.source_ids = list(cached.source_ids)
                tel.latency_ms = (time.monotonic() - t0) * 1000
                self._emit_telemetry(tel)
                return cached

        # TRIP_CURRENT_NEXT: template from node summaries, never cached
        if intent == AskIntent.TRIP_CURRENT_NEXT:
            det = format_deterministic_answer(
                intent=intent,
                facts=[],
                current_node_summary=current_node_summary,
                next_node_summary=next_node_summary,
            )
            if det is not None:
                resp = AskResponse(
                    answer=det,
                    tier=TrustTier.HEDGE,
                    path=AskPath.GROUNDED_DETERMINISTIC,
                    intent=intent,
                    source_class="trip_state",
                )
                tel.path = resp.path.value
                tel.latency_ms = (time.monotonic() - t0) * 1000
                self._emit_telemetry(tel)
                return resp
            resp = AskResponse(
                answer="I don't have enough trip context to answer that right now.",
                tier=TrustTier.REFUSE,
                path=AskPath.RETRIEVAL_MISS,
                intent=intent,
            )
            tel.path = resp.path.value
            tel.latency_ms = (time.monotonic() - t0) * 1000
            self._emit_telemetry(tel)
            return resp

        # Retrieve catalog facts
        facts = retrieve_catalog_facts(
            intent=intent,
            geo_region=geo_region,
            venue_name=venue_name,
            question=question,
            db=self.db,
            dish_glossary=self.dish_glossary,
        )
        tel.source_ids = [f.source_id for f in facts]

        # Retrieval miss -> refuse
        if not facts:
            resp = AskResponse(
                answer=(
                    "I don't have verified information for that "
                    "question in this region. Check with the venue "
                    "directly for the most accurate answer."
                ),
                tier=TrustTier.REFUSE,
                path=AskPath.RETRIEVAL_MISS,
                intent=intent,
            )
            tel.path = resp.path.value
            tel.latency_ms = (time.monotonic() - t0) * 1000
            self._emit_telemetry(tel)
            return resp

        # SPEC-14: dietary questions get hedge with disclaimer
        dietary_q = _is_dietary_question(question)
        if dietary_q and intent == AskIntent.DISH_FACT:
            ingredient_lines = [f.text for f in facts]
            source_ids = [f.source_id for f in facts]
            resp = AskResponse(
                answer=(
                    "I have ingredient information but cannot confirm "
                    "dietary suitability. " + "\n".join(ingredient_lines)
                ),
                tier=TrustTier.HEDGE,
                path=AskPath.GROUNDED_DETERMINISTIC,
                intent=intent,
                source_ids=source_ids,
                source_class="curated_catalog",
                food_disclaimer=_FOOD_DISCLAIMER,
            )
            self.cache.put(question, geo_region, venue_id or "", resp)
            tel.path = resp.path.value
            tel.latency_ms = (time.monotonic() - t0) * 1000
            self._emit_telemetry(tel)
            return resp

        # Deterministic template
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
            food_disc = _FOOD_DISCLAIMER if intent == AskIntent.DISH_FACT else None
            resp = AskResponse(
                answer=det_answer,
                tier=TrustTier.HEDGE,
                path=AskPath.GROUNDED_DETERMINISTIC,
                intent=intent,
                source_ids=[f.source_id for f in facts],
                source_class=source_class,
                food_disclaimer=food_disc,
            )
            self.cache.put(question, geo_region, venue_id or "", resp)
            tel.path = resp.path.value
            tel.cache_status = "miss_then_store"
            tel.latency_ms = (time.monotonic() - t0) * 1000
            self._emit_telemetry(tel)
            return resp

        # Facts found but no template -- refuse this slice
        resp = AskResponse(
            answer=(
                "I found some information but cannot format a "
                "verified answer right now. Check with the venue "
                "directly."
            ),
            tier=TrustTier.REFUSE,
            path=AskPath.RETRIEVAL_MISS,
            intent=intent,
        )
        tel.path = resp.path.value
        tel.latency_ms = (time.monotonic() - t0) * 1000
        self._emit_telemetry(tel)
        return resp
