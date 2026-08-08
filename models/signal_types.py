"""Canonical registry of signal types.

SINGLE SOURCE OF TRUTH. Adding a type requires:
  1. an entry here,
  2. a row in a new supabase/migrations/*.sql seeding `signal_type`,
  3. nothing else -- database_service reads this module.

tests/test_signal_types.py asserts (1) and (2) agree, so drift fails CI.
"""

# value_kind documents what `value_json` carries, for downstream consumers.
SIGNAL_TYPES: dict[str, str] = {
    # Explicit preference
    "user_loved": "none",
    # Reroute outcomes -- the core ranking-training signal.
    "reroute_accepted": "replacement_ref",
    "reroute_rejected": "rejected_refs",
    # Ground truth on whether the plan was followed.
    "visited_confirmed": "none",
    "node_skipped": "reason",
    # Schedule realism. Derived server-side from visited_confirmed
    # vs. planned start time; never sent by the client.
    "arrival_delta": "minutes",
}

SERVER_DERIVED_TYPES = frozenset({"arrival_delta"})


def is_valid(signal_type: str) -> bool:
    """Return True if signal_type is known (client or server-derived)."""
    return signal_type in SIGNAL_TYPES


def client_emittable_types() -> frozenset[str]:
    """Types a client may POST. Server-derived types are rejected at ingest."""
    return frozenset(SIGNAL_TYPES) - SERVER_DERIVED_TYPES
