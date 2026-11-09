"""SPEC-43 Gap 4 slice 9: purge in-process personal caches on erase.

Called by POST /api/v1/me/erase after the row erase and (supabase) Auth
delete, and before the caller is denied. Drops, in this process only:

- semantic-cache entries whose identity_scope is the caller,
- cost-tracker events for the caller,
- the caller's Ask budget counter.

Not touched: the error ring (entries carry no user id), the Ask
exact-match cache (public facts, not identity-scoped), the
cached_responses SQL table, and any cross-instance store.

Exceptions from the stores are not caught; the route owns the generic 500.
No supabase import, no logging, no print. ASCII only.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable, Dict, Optional


def _default(module: str, name: str) -> Any:
    # importlib: services.cache_service as a package attribute is the
    # singleton instance, not the module.
    return getattr(importlib.import_module(module), name)


def purge_identity_caches(
    user_id: str,
    *,
    semantic_cache: Optional[Any] = None,
    costs: Optional[Any] = None,
    reset_budget: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Drop the caller's in-process cache state. Returns removal counts."""
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id is required")
    if semantic_cache is None:
        semantic_cache = _default("services.cache_service", "cache_service")
    if costs is None:
        costs = _default("monitoring.cost_tracker", "cost_tracker")
    if reset_budget is None:
        reset_budget = _default("services.ask_service", "reset_ask_budget")
    removed_cache = semantic_cache.clear_identity(user_id)
    removed_costs = costs.clear_user(user_id)
    reset_budget(user_id)
    return {"semantic_cache": removed_cache, "cost_events": removed_costs, "ask_budget": True}
