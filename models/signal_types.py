"""Canonical registry of signal types.

SINGLE SOURCE OF TRUTH for: signal type KEYS and VALUE_KIND (what value_json carries).

Adding a type requires:
  1. An entry here (key + value_kind),
  2. A row in a new supabase/migrations/*.sql seeding `signal_type`,
  3. Nothing else — database_service reads this module at startup.

What Python IS authoritative for:
  - The complete set of valid signal type keys
  - value_kind (documents what value_json carries, for downstream consumers)

What Python is NOT authoritative for (SQL is the source):
  - category (explicit_user | behavioral | derived — set only in migrations)
  - decay_policy (none | exp_180d | ... — set only in migrations)
  - enum_values (closed value sets for specific types — set only in migrations)
  - description (human-readable — set only in migrations)

tests/test_signal_types.py asserts keys AND value_kind agree across Python
and migrations, so drift in either direction fails CI.
"""

# Keys must match migrations exactly.
# value_kind must match the value_kind column in the corresponding migration INSERT.
# The SQL value_kind vocabulary (from 0002 comment): numeric | enum | json | boolean
SIGNAL_TYPES: dict[str, str] = {
    # Explicit preference
    "user_loved": "enum",
    # Reroute outcomes — the core ranking-training signal.
    "reroute_accepted": "json",
    "reroute_rejected": "json",
    # Ground truth on whether the plan was followed.
    "visited_confirmed": "boolean",
    "node_skipped": "json",
    # Schedule realism. Derived server-side from visited_confirmed
    # vs. planned start time; never sent by the client.
    "arrival_delta": "numeric",
    # Dish-level signals. Requires entity_type='dish' (migration 0005).
    "dish_loved": "enum",
    "dish_ordered": "boolean",
}

# Closed enum for node_skipped reasons. Client must present a picker,
# not a free-text field. Unanalyzable free-text defeats the purpose.
NODE_SKIPPED_REASONS = frozenset({
    "too_far",
    "too_tired",
    "closed",
    "crowded",
    "not_interested",
    "ran_out_of_time",
    "weather",
})

SERVER_DERIVED_TYPES = frozenset({"arrival_delta"})

# Signal types that require entity_type='dish'. Emitting these with
# entity_type='venue' (or without entity_id) is a schema error.
DISH_SIGNAL_TYPES = frozenset({"dish_loved", "dish_ordered"})


def is_valid(signal_type: str) -> bool:
    """Return True if signal_type is known (client or server-derived)."""
    return signal_type in SIGNAL_TYPES


def client_emittable_types() -> frozenset[str]:
    """Types a client may POST. Server-derived types are rejected at ingest."""
    return frozenset(SIGNAL_TYPES) - SERVER_DERIVED_TYPES
