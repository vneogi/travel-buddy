"""Travel Buddy — Signal Router (SPEC-01 + SPEC-02 Part C)

Ingest endpoint for the signal-capture data flywheel. Accepts batches of
client-generated signals, validates type, enforces auth, and upserts
idempotently (client-generated signal_id = dedup key).

Design: batch-first (offline queue in SPEC-02 syncs batches; single signal
is just a batch of 1).

SPEC-02 Part C additions:
- captured_at from client stored VERBATIM (device clock, never overwritten)
- Tolerates captured_at skew: up to 30 days old and 5 minutes future
- Returns itemized rejected[] so client can retire permanently-bad rows
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from security import get_current_user_id
from services.database_service import db_service
from models.signal_types import SERVER_DERIVED_TYPES

router = APIRouter(prefix="/api/v1", tags=["signals"])

# Skew tolerance (SPEC-02 Part C: long offline stretches are normal)
_MAX_AGE = timedelta(days=30)
_MAX_FUTURE = timedelta(minutes=5)


# ==============================================================================
# Request / Response Models
# ==============================================================================

class SignalIn(BaseModel):
    """A single signal from the client.

    signal_id is CLIENT-GENERATED (UUID) — the idempotency key.
    user_id is NEVER accepted from the client (filled from auth token).
    """
    signal_id: str = Field(..., description="Client-generated UUID (idempotency key)")
    signal_type: str = Field(..., description="Signal type key (e.g. 'user_loved')")
    place_ref: str = Field(..., description="Venue ID or name from the itinerary")
    value_text: Optional[str] = None
    value_numeric: Optional[float] = None
    value_json: Optional[dict] = None
    captured_at: datetime = Field(..., description="When the user acted (device clock, stored verbatim)")
    trip_id: Optional[str] = None


class SignalBatchRequest(BaseModel):
    """Batch of signals (offline queue syncs batches; single = batch of 1)."""
    signals: List[SignalIn] = Field(..., min_length=1, max_length=100)


class RejectedSignal(BaseModel):
    """A signal that was permanently rejected (client should not retry)."""
    signal_id: str
    reason: str


class SignalBatchResponse(BaseModel):
    """Result of signal ingestion.

    SPEC-02 Part C: includes itemized rejected[] so the client can mark
    permanently-bad rows as failed_permanent and stop retrying them.
    """
    accepted: int
    duplicates: int
    rejected: List[RejectedSignal] = Field(default_factory=list)


# ==============================================================================
# Consent stub (seam for future consent enforcement — SPEC-01 guiding rule)
# ==============================================================================

def require_consent(scope: str, user_id: str) -> None:
    """Stub: in a future spec, this checks the user's granted consent scopes.

    Currently passes unconditionally. The seam exists so wiring real consent
    enforcement is a one-place change, not a refactor.
    """
    # TODO(SPEC-future): check consent table for user_id + scope
    pass


# ==============================================================================
# Helpers
# ==============================================================================

def _validate_captured_at(captured_at: datetime) -> Optional[str]:
    """Validate captured_at skew tolerance (SPEC-02 Part C).

    Accepts timestamps up to 30 days old and 5 minutes in the future.
    Returns an error reason string if invalid, None if OK.
    """
    now = datetime.now(tz=timezone.utc)
    # Make captured_at tz-aware for comparison if it isn't already
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)

    if captured_at < now - _MAX_AGE:
        return f"captured_at too old (>{_MAX_AGE.days}d): {captured_at.isoformat()}"
    if captured_at > now + _MAX_FUTURE:
        return f"captured_at too far in future (>{int(_MAX_FUTURE.total_seconds())}s): {captured_at.isoformat()}"
    return None


def _compute_provenance(captured_at: datetime) -> dict:
    """Build provenance dict, noting extreme skew if present (SPEC-02 Part C)."""
    now = datetime.now(tz=timezone.utc)
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)

    provenance = {"method": "client_emit"}
    skew_seconds = (now - captured_at).total_seconds()
    # Flag if > 1 hour old (expected but notable for analytics)
    if abs(skew_seconds) > 3600:
        provenance["clock_skew_seconds"] = round(skew_seconds)
    return provenance


# ==============================================================================
# Endpoints
# ==============================================================================


def _build_party_context(trip_id: str, captured_at: datetime) -> Optional[Dict]:
    """Build the party_context dict for stamping onto a signal.

    SPEC-03 design: server-side at ingest, authoritative. If trip or party
    not found, returns None (never fail ingest). The context is frozen at
    ingest time — later party edits don't retroactively change old signals.
    """
    party = db_service.get_trip_party(trip_id)
    if not party:
        return None

    # Make captured_at tz-aware for computation
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)

    context: Dict = {
        "party_type": party.party_type,
        "size": party.size,
        "age_bands": sorted({m.age_band for m in party.members}) if party.members else [],
        "time_of_day": captured_at.strftime("%H:%M"),
    }

    # day_index: days since trip start (if we can look it up)
    trip = db_service.get_trip(trip_id)
    if trip:
        trip_start = trip.created_at
        if trip_start.tzinfo is None:
            trip_start = trip_start.replace(tzinfo=timezone.utc)
        context["day_index"] = (captured_at.date() - trip_start.date()).days

    return context


@router.post(
    "/signals",
    response_model=SignalBatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest a batch of signals",
    description=(
        "Accepts a batch of client-generated signals. Idempotent: re-posting "
        "the same signal_id is a 200 no-op (not a duplicate). Auth required. "
        "Returns itemized rejected[] for permanently-bad signals (client should "
        "stop retrying those)."
    ),
)
async def ingest_signals(
    batch: SignalBatchRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Ingest signals into the data asset.

    - Auth: user_id from verified token (never from request body).
    - Validates signal_type exists (rejects per-item, not whole batch).
    - Validates captured_at skew (30d old / 5min future tolerance).
    - Idempotent: ON CONFLICT (signal_id) DO NOTHING.
    - Consent: stub (passes; wired in a later spec).
    - Returns {accepted, duplicates, rejected} — never 500s the whole batch.
    """
    # Consent check (stub — passes for now)
    require_consent("behavioral_capture", user_id)

    valid_types = db_service.get_valid_signal_types()

    accepted = 0
    duplicates = 0
    rejected: List[RejectedSignal] = []

    for sig in batch.signals:
        # Per-item validation: unknown signal_type
        if sig.signal_type not in valid_types:
            rejected.append(RejectedSignal(
                signal_id=sig.signal_id,
                reason=f"unknown signal_type: '{sig.signal_type}'"
            ))
            continue

        # SPEC-06: server-derived types cannot be submitted by clients
        if sig.signal_type in SERVER_DERIVED_TYPES:
            rejected.append(RejectedSignal(
                signal_id=sig.signal_id,
                reason=f"'{sig.signal_type}' is derived server-side and cannot be submitted"
            ))
            continue

        # Per-item validation: captured_at skew
        skew_error = _validate_captured_at(sig.captured_at)
        if skew_error:
            rejected.append(RejectedSignal(
                signal_id=sig.signal_id,
                reason=skew_error
            ))
            continue

        # Build provenance (notes extreme skew for analytics)
        provenance = _compute_provenance(sig.captured_at)

        # SPEC-03: stamp party_context server-side at ingest.
        # Merged INTO value_json (not overwriting). If trip unknown, omit —
        # never fail ingest due to missing party data.
        value_json = dict(sig.value_json) if sig.value_json else {}
        if sig.trip_id:
            party_context = _build_party_context(sig.trip_id, sig.captured_at)
            if party_context:
                value_json["party_context"] = party_context

        # Record signal (idempotent — duplicates counted, not errors)
        was_new = db_service.record_signal(
            user_id=user_id,
            signal_id=sig.signal_id,
            signal_type=sig.signal_type,
            place_ref=sig.place_ref,
            value_text=sig.value_text,
            value_numeric=sig.value_numeric,
            value_json=value_json if value_json else None,
            captured_at=sig.captured_at,
            trip_id=sig.trip_id,
        )
        if was_new:
            accepted += 1
        else:
            duplicates += 1

    return SignalBatchResponse(
        accepted=accepted,
        duplicates=duplicates,
        rejected=rejected,
    )
