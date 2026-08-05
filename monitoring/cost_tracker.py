"""Travel Buddy MVP - Cost Monitoring & Analytics

⚠️  STATUS: SCAFFOLDED — NOT WIRED INTO THE REQUEST PATH.
    This module is not imported by any router/agent/main.py.
    Cost data is not surfaced by any endpoint (/stats reports
    cache/event counts from db_service, not cost).

Tracks LLM token usage, API costs, and user-level attribution.
Provides:
  - Real-time cost dashboards
  - Per-user cost attribution (for tier pricing validation)
  - Daily spend alerts
  - Model efficiency comparisons
  - Cache savings calculator

Designed to answer: "Are we spending more per user than they pay us?"
"""

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from config.settings import settings


# API cost reference (USD per unit)
API_COSTS = {
    # LLM costs (per 1K tokens)
    "gpt-4o_input": 0.0025,
    "gpt-4o_output": 0.010,
    "gpt-4o-mini_input": 0.00015,
    "gpt-4o-mini_output": 0.0006,
    "gemini-1.5-flash_input": 0.000075,
    "gemini-1.5-flash_output": 0.0003,
    "text-embedding-3-small": 0.00002,  # per 1K tokens

    # External API costs (per call)
    "google_distance_matrix": 0.005,  # per element
    "google_places_nearby": 0.032,    # per request
    "google_places_details": 0.017,   # per request
    "openweather_current": 0.0,       # free tier
    "openweather_forecast": 0.0,      # free tier
}

# Revenue reference
REVENUE = {
    "pro_monthly": 4.99,
    "pro_yearly_monthly": 3.33,  # $39.99/12
    "sponsored_impression": 0.01,  # per sponsored venue shown
}


class CostEvent:
    """A single cost event."""

    def __init__(
        self,
        user_id: str,
        event_type: str,
        model_or_api: str,
        cost_usd: float,
        tokens_used: int = 0,
        from_cache: bool = False,
    ):
        self.user_id = user_id
        self.event_type = event_type
        self.model_or_api = model_or_api
        self.cost_usd = cost_usd
        self.tokens_used = tokens_used
        self.from_cache = from_cache
        self.timestamp = datetime.now(tz=timezone.utc)


class CostTracker:
    """Tracks and analyzes costs across the system."""

    MAX_EVENTS = 10_000  # Cap to prevent unbounded memory growth

    def __init__(self):
        self._events: List[CostEvent] = []
        self._daily_budget_usd = 50.0  # Alert threshold
        self._alert_callbacks = []

    # =========================================================================
    # Event Recording
    # =========================================================================

    def record_llm_call(
        self,
        user_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        routing_tier: str = "light",
    ) -> float:
        """Record an LLM call and return its cost."""
        input_cost = (input_tokens / 1000) * API_COSTS.get(f"{model}_input", 0.001)
        output_cost = (output_tokens / 1000) * API_COSTS.get(f"{model}_output", 0.002)
        total_cost = input_cost + output_cost

        self._events.append(CostEvent(
            user_id=user_id,
            event_type=f"llm_{routing_tier}",
            model_or_api=model,
            cost_usd=total_cost,
            tokens_used=input_tokens + output_tokens,
        ))

        # Rotate: keep only recent events to prevent memory leak
        if len(self._events) > self.MAX_EVENTS:
            cutoff = datetime.now(tz=timezone.utc) - timedelta(days=2)
            self._events = [e for e in self._events if e.timestamp > cutoff]
        self._check_budget_alert()
        return total_cost

    def record_api_call(
        self, user_id: str, api_name: str, call_count: int = 1
    ) -> float:
        """Record an external API call."""
        unit_cost = API_COSTS.get(api_name, 0.0)
        total_cost = unit_cost * call_count

        self._events.append(CostEvent(
            user_id=user_id,
            event_type="api_call",
            model_or_api=api_name,
            cost_usd=total_cost,
        ))

        return total_cost

    def record_cache_hit(self, user_id: str) -> None:
        """Record a cache hit (zero cost, but track savings)."""
        self._events.append(CostEvent(
            user_id=user_id,
            event_type="cache_hit",
            model_or_api="semantic_cache",
            cost_usd=0.0,
            from_cache=True,
        ))

    def record_embedding(
        self, user_id: str, token_count: int
    ) -> float:
        """Record an embedding generation."""
        cost = (token_count / 1000) * API_COSTS["text-embedding-3-small"]
        self._events.append(CostEvent(
            user_id=user_id,
            event_type="embedding",
            model_or_api="text-embedding-3-small",
            cost_usd=cost,
            tokens_used=token_count,
        ))
        return cost

    # =========================================================================
    # Analytics
    # =========================================================================

    def get_daily_summary(self, target_date: datetime = None) -> Dict:
        """Get cost summary for a specific day."""
        if target_date is None:
            target_date = datetime.now(tz=timezone.utc)

        day_start = target_date.replace(hour=0, minute=0, second=0)
        day_end = day_start + timedelta(days=1)

        day_events = [
            e for e in self._events
            if day_start <= e.timestamp < day_end
        ]

        total_cost = sum(e.cost_usd for e in day_events)
        total_tokens = sum(e.tokens_used for e in day_events)
        cache_hits = sum(1 for e in day_events if e.from_cache)
        unique_users = len(set(e.user_id for e in day_events))

        # Estimate cache savings (what would have cost if not cached)
        avg_llm_cost = 0.003  # Average cost per LLM call
        cache_savings = cache_hits * avg_llm_cost

        return {
            "date": day_start.date().isoformat(),
            "total_cost_usd": round(total_cost, 4),
            "total_tokens": total_tokens,
            "total_events": len(day_events),
            "unique_users": unique_users,
            "cost_per_user": round(total_cost / unique_users, 4) if unique_users > 0 else 0,
            "cache_hits": cache_hits,
            "cache_savings_usd": round(cache_savings, 4),
            "budget_remaining": round(self._daily_budget_usd - total_cost, 2),
            "budget_utilization": round(total_cost / self._daily_budget_usd * 100, 1),
            "breakdown": self._cost_breakdown(day_events),
        }

    def get_user_cost(self, user_id: str, days: int = 30) -> Dict:
        """Get cost attribution for a specific user."""
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
        user_events = [
            e for e in self._events
            if e.user_id == user_id and e.timestamp >= cutoff
        ]

        total_cost = sum(e.cost_usd for e in user_events)
        total_events = len(user_events)

        return {
            "user_id": user_id,
            "period_days": days,
            "total_cost_usd": round(total_cost, 4),
            "total_events": total_events,
            "avg_cost_per_event": round(total_cost / total_events, 6) if total_events > 0 else 0,
            "is_profitable": total_cost < REVENUE["pro_monthly"],  # Assuming pro user
            "profit_margin_usd": round(REVENUE["pro_monthly"] - total_cost, 2),
        }

    def get_model_efficiency(self) -> Dict:
        """Compare cost efficiency across models."""
        model_stats = defaultdict(lambda: {"calls": 0, "cost": 0.0, "tokens": 0})

        for event in self._events:
            if event.event_type.startswith("llm_"):
                m = event.model_or_api
                model_stats[m]["calls"] += 1
                model_stats[m]["cost"] += event.cost_usd
                model_stats[m]["tokens"] += event.tokens_used

        return {
            model: {
                **stats,
                "cost_per_call": round(stats["cost"] / stats["calls"], 5) if stats["calls"] > 0 else 0,
                "cost_per_1k_tokens": round(stats["cost"] / (stats["tokens"] / 1000), 5) if stats["tokens"] > 0 else 0,
            }
            for model, stats in model_stats.items()
        }

    # =========================================================================
    # Alerts
    # =========================================================================

    def set_daily_budget(self, budget_usd: float) -> None:
        """Set the daily spending alert threshold."""
        self._daily_budget_usd = budget_usd

    def _check_budget_alert(self) -> None:
        """Check if daily budget is exceeded (efficient: today's events only)."""
        today = datetime.now(tz=timezone.utc).date()
        daily_cost = sum(e.cost_usd for e in self._events if e.timestamp.date() == today)
        if daily_cost >= self._daily_budget_usd * 0.8:
            # 80% threshold warning
            for callback in self._alert_callbacks:
                callback({
                    "type": "budget_warning",
                    "utilization": daily_cost / self._daily_budget_usd,
                    "cost": daily_cost,
                    "budget": self._daily_budget_usd,
                })

    def _cost_breakdown(self, events: List[CostEvent]) -> Dict:
        """Break down costs by category."""
        breakdown = defaultdict(float)
        for event in events:
            breakdown[event.event_type] += event.cost_usd
        return dict(breakdown)


# Singleton instance
cost_tracker = CostTracker()
