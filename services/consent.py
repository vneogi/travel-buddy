"""SPEC-43 Gap 7: purpose-based consent for signal ingest (fail closed).

Every signal type maps to one purpose. Necessary trip-operation signals are
always allowed. Optional purposes (personalization, analytics, location,
marketing) are denied until a real grant ledger exists: there is no ledger
this slice, so ``has_consent`` returns False for them.

Callers must reach ``has_consent`` through this module attribute
(``services.consent.has_consent``) so one patch covers ingest and derive.
Debug identity (TB_DEBUG) is not a purpose grant.
"""

from __future__ import annotations

from models.signal_types import SIGNAL_TYPES

PURPOSE_NECESSARY = "necessary_operation"
PURPOSE_ANALYTICS = "analytics"
PURPOSE_PERSONALIZATION = "personalization"
PURPOSE_LOCATION = "location"
PURPOSE_MARKETING = "marketing"

OPTIONAL_PURPOSES = frozenset(
    {PURPOSE_ANALYTICS, PURPOSE_PERSONALIZATION, PURPOSE_LOCATION, PURPOSE_MARKETING}
)

SIGNAL_PURPOSE: dict[str, str] = {
    # Necessary trip operation (always granted)
    "session_start": PURPOSE_NECESSARY,
    "booking_added": PURPOSE_NECESSARY,
    "visited_confirmed": PURPOSE_NECESSARY,
    "node_skipped": PURPOSE_NECESSARY,
    "driver_card_shown": PURPOSE_NECESSARY,
    "name_confirmed": PURPOSE_NECESSARY,
    "prompt_dismissed": PURPOSE_NECESSARY,
    # Personalization (optional)
    "user_loved": PURPOSE_PERSONALIZATION,
    "dish_loved": PURPOSE_PERSONALIZATION,
    "dish_ordered": PURPOSE_PERSONALIZATION,
    "reroute_accepted": PURPOSE_PERSONALIZATION,
    "reroute_rejected": PURPOSE_PERSONALIZATION,
    # Analytics (optional)
    "arrival_delta": PURPOSE_ANALYTICS,
}

_missing = set(SIGNAL_TYPES) - set(SIGNAL_PURPOSE)
if _missing:  # pragma: no cover - import-time drift guard
    raise RuntimeError(f"SIGNAL_PURPOSE missing signal types: {sorted(_missing)}")


class ConsentRequired(Exception):
    """Raised when a signal's purpose has not been granted."""

    def __init__(self, signal_type: str, purpose: str):
        self.signal_type = signal_type
        self.purpose = purpose
        self.reason = f"consent_required: purpose '{purpose}' not granted for '{signal_type}'"
        super().__init__(self.reason)


def purpose_for_signal(signal_type: str) -> str:
    """Purpose for *signal_type*. Unmapped types are optional analytics."""
    return SIGNAL_PURPOSE.get(signal_type, PURPOSE_ANALYTICS)


def has_consent(user_id: str, purpose: str) -> bool:
    """True if *user_id* granted *purpose*. No ledger yet: optional -> False."""
    if purpose == PURPOSE_NECESSARY:
        return True
    return False


def require_consent_for_signal(signal_type: str, user_id: str) -> None:
    """Raise ConsentRequired unless the signal's purpose is granted."""
    purpose = purpose_for_signal(signal_type)
    # Module-global lookup at call time so a patched has_consent applies.
    if not has_consent(user_id, purpose):
        raise ConsentRequired(signal_type, purpose)
