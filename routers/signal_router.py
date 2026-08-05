"""Travel Buddy — Signal Router (SPEC-01 Part B)

Ingest endpoint for the signal-capture data flywheel. Accepts batches of
client-generated signals, validates type, enforces auth, and upserts
idempotently (client-generated signal_id = dedup key).

Design: batch-first (offline queue in SPEC-02 syncs batches; single signal
is just a batch of 1).
"""

from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from security import get_current_user_id
from services.database_service import db_service

router = APIRouter(prefix="/api/v1", tags=["signals"])


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
    captured_at: datetime = Field(..., description="When the user acted (client clock)")
    trip_id: Optional[str] = None


class SignalBatchRequest(BaseModel):
    """Batch of signals (offline queue syncs batches; single = batch of 1)."""
    signals: List[SignalIn] = Field(..., min_length=1, max_length=100)


class SignalBatchResponse(BaseModel):
    """Result of signal ingestion."""
    accepted: int
    duplicates: int


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
# Endpoints
# ==============================================================================

@router.post(
    "/signals",
    response_model=SignalBatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest a batch of signals",
    description=(
        "Accepts a batch of client-generated signals. Idempotent: re-posting "
        "the same signal_id is a 200 no-op (not a duplicate). Auth required."
    ),
)
async def ingest_signals(
    batch: SignalBatchRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Ingest signals into the data asset.

    - Auth: user_id from verified token (never from request body).
    - Validates signal_type exists (rejects unknown types with 422).
    - Idempotent: ON CONFLICT (signal_id) DO NOTHING.
    - Consent: stub (passes; wired in a later spec).
    """
    # Consent check (stub — passes for now)
    require_consent("behavioral_capture", user_id)

    # Validate all signal types in the batch
    valid_types = db_service.get_valid_signal_types()
    for sig in batch.signals:
        if sig.signal_type not in valid_types:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown signal_type: '{sig.signal_type}'. "
                       f"Valid types: {sorted(valid_types)}",
            )

    # Record signals (idempotent — duplicates are counted, not errors)
    accepted = 0
    duplicates = 0
    for sig in batch.signals:
        was_new = db_service.record_signal(
            user_id=user_id,
            signal_id=sig.signal_id,
            signal_type=sig.signal_type,
            place_ref=sig.place_ref,
            value_text=sig.value_text,
            value_numeric=sig.value_numeric,
            value_json=sig.value_json,
            captured_at=sig.captured_at,
            trip_id=sig.trip_id,
        )
        if was_new:
            accepted += 1
        else:
            duplicates += 1

    return SignalBatchResponse(accepted=accepted, duplicates=duplicates)
